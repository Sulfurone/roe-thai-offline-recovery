"""Execute original Thai target lookup and pickup sender in isolation.

The entity manager hash, selected-nearby entry, RTTI checks, entity accessors,
request construction and wire codec execute original instructions. Resource
position/UID getters, UI accessors and the network sink use synthetic data.
This is not evidence of live keyboard input or rendered ground loot.
"""
import json
import struct
import sys
from pathlib import Path
from native_codec_probe import NativeCodec,OUT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_EDX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from offline_gameplay import OfflineGameplay
from extract_ground_entity_defaults import extract

c=NativeCodec()
manager,entities,entity,controller=0x10800000,0x10801000,0x10802000,0x10803000
buckets,node,nearby,component_vt,position=0x10805000,0x10806000,0x10807000,0x10808000,0x10809000
uid_getter,position_getter=0x109f0000,0x109f0020
selection,camera=0x1080a000,0x1080b000
configuration,entity_table=0x1080d000,0x1080e000
entity_uid=0x400001
automatic=1
sent=[]
ui_wait=[]
for address,value in ((0x2eedb58,manager),(manager+0x74,entities),
        (entities+0x14,buckets),(entities+0x18,16),(buckets+4,node),
        (node,entity_uid),(node+8,entity),(entity,0x25b35f8),
        (entity+0x10,component_vt),(component_vt+0x54,uid_getter),
        (component_vt+0x6c,position_getter),(entity+0x340,0xffffffff),
        (entity+0x34c,30001),(entity+0x350,60),(entity+0x498,1),
        (entity+0x4b0,1),(manager+0x184,entity_table),
        (entity_table+0x40,configuration),(entity_table+0x44,configuration+0x134),
        (configuration,30001),
        (entity+0x4c8,entity_uid),(entities+0x60,nearby),(entities+0x64,nearby+0x28),
        (entities+0x150,entity_uid),(nearby,entity_uid),(nearby+0xc,1),
        (selection+8,2),(selection+0xc,7),(0x2eed5b0,0x1080c000)):
    c.uc.mem_write(address,struct.pack('<I',value))
c.uc.mem_write(position,struct.pack('<3f',325950.,271700.,6501.))
c.uc.mem_write(camera+0x38,struct.pack('<3f',325800.,271700.,6638.))
original=extract(ROOT/'extracted/tablebin/731ced6c9309b681.bin')
ammo_row=next(row for row in original['rows'] if row['id']==30001)
c.uc.mem_write(configuration+0x5c,bytes([ammo_row['collectable']]))
c.uc.mem_write(configuration+0x98,struct.pack('<II',ammo_row['max_op_distance'],ammo_row['min_op_distance']))

def stub(uc,address,size,user):
    stack=uc.reg_read(UC_X86_REG_ESP)
    ret=c.read32(stack)
    consumed=0
    result=0
    high=0
    if address==uid_getter:result=entity_uid
    elif address==position_getter:result=position
    elif address==0x12bb6c0:result=automatic
    elif address==0xb6a2f0:result=selection
    elif address==0xf61480:
        result=0x100
        high=0x10000
    elif address==0x535000:result=camera
    elif address==0x661dc0:consumed=20
    elif address==0x12bb6d0:
        consumed=4
        ui_wait.append(c.read32(stack+4))
    elif address==0xe99a90:consumed=12
    elif address==0xea4610:
        message,pointer,length=struct.unpack('<3I',uc.mem_read(stack+4,12))
        if message!=0x3b63 or length!=33:
            raise ValueError('Unexpected original pickup sink message/length')
        sent.append(bytes(uc.mem_read(pointer,length)))
        consumed=12
    else:raise ValueError(f'Unknown dependency {address:#x}')
    uc.reg_write(UC_X86_REG_EAX,result)
    uc.reg_write(UC_X86_REG_EDX,high)
    uc.reg_write(UC_X86_REG_ESP,stack+4+consumed)
    uc.reg_write(UC_X86_REG_EIP,ret)

for address in (uid_getter,position_getter,0x12bb6c0,0xb6a2f0,0xf61480,
                0x535000,0x661dc0,0x12bb6d0,0xe99a90,0xea4610):
    if address in (uid_getter,position_getter):
        c.external_hooks.add(address)
        c.uc.mem_write(address,b'\xc3')
    c.uc.hook_add(UC_HOOK_CODE,stub,begin=address,end=address)

assert c.invoke(0x1322440,0,[entity_uid,0])==1
c.uc.mem_write(entity+0x4a5,b'\x01')
assert c.invoke(0x1322440,0,[entity_uid,0])==0
c.uc.mem_write(entity+0x4a5,b'\x00')
assert c.invoke(0x106eaf0,entity,[])&255==1
c.uc.mem_write(configuration+0x5c,b'\x00')
assert c.invoke(0x106eaf0,entity,[])&255==0
c.uc.mem_write(configuration+0x5c,bytes([ammo_row['collectable']]))

def run(selected,in_use,auto):
    global automatic
    automatic=auto
    c.uc.mem_write(entities+0x150,struct.pack('<I',selected))
    c.uc.mem_write(entity+0x340,struct.pack('<I',in_use))
    before=len(sent)
    c.invoke(0xe9c7a0,controller,[1,0xffffffff])
    return sent[before:]

assert run(0x400009,0xffffffff,1)==[]
assert run(entity_uid,1,1)==[]
report={'original_entry':'0xE9C7A0','original_entity_lookup':'0x11305B0 -> 0x10F9B10',
        'original_pickup':'0xE9B910 -> 0x128BCC0','missing_target_sends_nothing':True,
        'in_use_entity_sends_nothing':True,'original_disabled_flag_gate':True,
        'original_collectable_config_gate':True,'original_max_op_distance_cm':ammo_row['max_op_distance'],
        'cases':[]}
for auto in (1,0):
    captured=run(entity_uid,0xffffffff,auto)
    if len(captured)!=1:raise ValueError('Original selected single-item pickup did not send exactly once')
    native=captured[0]
    code,body=c.pack_type(0xdee4a0,native)
    check=c.decode_server(0x3b63,body)
    if code or check['code'] or check['consumed']!=len(body)+10:
        raise ValueError('Original pickup request codec did not consume complete body')
    values=struct.unpack('>IIQBHB3iB',body)
    if values[0:2]!=(entity_uid,0) or values[5]!=auto or values[6:9]!=(325800,271700,6638):
        raise ValueError(f'Unexpected native pickup identity/slot/camera: {values}')
    if auto==0 and values[2:5]!=(0x0001000000000100,2,7):
        raise ValueError('Original explicit destination fields differ')
    game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,actor_uid=0x0001000000000100)
    game.handle(0x2a,struct.pack('>I3i',1,325800,271700,6488))
    replies=game.handle(0x3b63,body)
    if game.reserve!=180 or game.ground_loot.stacks or [m for m,_ in replies]!=[0x3e82,0x82b,0x3b64]:
        raise ValueError('Server does not accept original pickup request')
    report['cases'].append({'automatic':auto,'wire_body_hex':body.hex(),
                            'native_bytes':len(native),'wire_bytes':len(body),
                            'server_reserve':game.reserve,**check})
report['ui_wait_flags']=ui_wait
report['limitation']='Synthetic model/UI accessors and message sink; no live input, proximity or graphics proof'
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'native-ground-pickup-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
