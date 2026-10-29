"""Own-table facts and original Thai codecs for extended loot/land vehicles.

No renderer or throw/attachment-use proof. All generated material is private.
"""
import json
import struct
import sys
from pathlib import Path
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP,UC_X86_REG_EIP

sys.path.insert(0,str(ROOT))
from offline_items import EXTRA_ITEMS,SPAWNABLE_EXTRA_ITEMS
from offline_vehicles import LAND_VEHICLES
from control_actions import ControlSession
from test_control_panel import ready_game

catalog=ROOT/'private/gameplay-catalog'
item_data=json.loads((catalog/'original-item-defaults.json').read_text(encoding='utf8'))
items={r['dwStringID']:r for t in item_data['tables'] for r in t['rows']}
entity_data=json.loads((catalog/'ground-entity-defaults.json').read_text(encoding='utf8'))
entities={r['id']:r for t in entity_data['tables'] for r in t['rows']}
vehicles={r['id']:r for r in json.loads((catalog/'vehicle-defaults.json').read_text(encoding='utf8'))}
codec=NativeCodec()
game=ready_game()
control=ControlSession(game,(ROOT/'private/typed-gameplay/vehicle-jeep-near.bin').read_bytes())
messages=0
factory_arguments=[]

def factory(uc,address,size,user):
    values=struct.unpack('<10I',uc.mem_read(uc.reg_read(UC_X86_REG_ESP),40))
    factory_arguments.append((values[4],values[7]))
    uc.reg_write(UC_X86_REG_EIP,codec.RETURN)

codec.uc.hook_add(UC_HOOK_CODE,factory,begin=0x10999d0,end=0x10999d0)

def check(packets):
    global messages
    for message,body in packets:
        result=codec.decode_server(message,body)
        if result['code'] or result['consumed']!=result['bytes']:
            raise ValueError(f'Incomplete original decode {message:#x}: {result}')
        messages+=1

for template,spec in EXTRA_ITEMS.items():
    row=items[template]
    if (row['mCategory']!=spec.kind or (row['nPackMax'] or 1)!=spec.max_stack
            or row['szPositionArray']!=([spec.slot] if spec.slot else [])
            or row['WeaponPartType']!=spec.part_type or row['WeaponPartIndex']!=spec.part_index
            or row['nExtWeight']!=spec.extra_weight or row['nDurableValue']!=spec.durability
            or not entities[template]['collectable']):
        raise ValueError(f'Extra catalogue differs from original table: {template}')
    if template not in SPAWNABLE_EXTRA_ITEMS:continue
    packets,_=control.execute(dict(action='item',template=template))
    check(packets)
    stack=list(game.ground_loot.stacks.values())[-1]
    request=struct.pack('>IIQBHB3iB',stack.entity,0,0,0,0,1,*game.player_position,0)
    check(game.handle(0x3b63,request))
for config,spec in LAND_VEHICLES.items():
    row=vehicles[config]
    if (row['initial_hp']!=spec.hp or len(row['seats'])!=spec.seats
            or row['geton_distance']!=spec.geton_distance or row['initial_oil'] or row['max_oil']):
        raise ValueError(f'Land vehicle facts differ: {config}')
    packets,_=control.execute(dict(action='vehicle',config=config))
    check(packets)
    result=codec.decode_server(*packets[0])
    native=bytes(codec.uc.mem_read(codec.ROOT_OBJECT+10,0xa0))
    if struct.unpack_from('<I',native,0x88)[0]!=config or struct.unpack_from('<I',native,0x90)[0]!=spec.hp:
        raise ValueError('Vehicle ID/health did not survive native decode')
    dto=bytes(codec.uc.mem_read(codec.ROOT_OBJECT+10,0x1259))
    codec.uc.mem_write(codec.OBJECT,struct.pack('<I',0x654b)+dto+bytes(64))
    codec.invoke(0x1289610,0,[codec.OBJECT])
    if factory_arguments[-1]!=(config,spec.hp):
        raise ValueError('Native factory does not receive selected vehicle config/health')
control.client_boarding=True
car=list(control.vehicles.values())[-1]
request=struct.pack('>QI',car.vehicle_uid,1)
car.vehicle_ready=False
denied=control.handle(0x6541,request)
check(denied)
codec.decode_server(*denied[0])
if struct.unpack('<I',codec.uc.mem_read(codec.ROOT_OBJECT+10+28,4))[0]!=1:
    raise ValueError('Boarding error does not reach the original callback gate')
car.vehicle_ready=True
check(control.handle(0x6541,request))
if not game.seated or control.active_vehicle!=car.vehicle_uid:
    raise ValueError('Loaded local-client boarding did not advance the owning session')
report=dict(items=len(EXTRA_ITEMS),vehicles=len(LAND_VEHICLES),messages=messages,passed=True,
            vehicle_factory_arguments=factory_arguments,
            limitation='Original table/codec verification only; new visuals, throwing, attachments and driving unverified')
(ROOT/'private/typed-gameplay/extra-loot-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
