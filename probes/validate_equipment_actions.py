"""Original Thai item unions, part request and armour durability, offline.

Uses only the owner's private diagnostic image and tables. Factory allocation
is replaced with an emulator buffer; no renderer or live process is executed.
"""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP

sys.path.insert(0,str(ROOT))
from offline_inventory import OfflineInventory,Item
from offline_items import EXTRA_ITEMS
from offline_attachments import PART_TYPES,PART_INDICES
from test_equipment_actions import part_request

rows=json.loads((ROOT/'private/gameplay-catalog/original-item-defaults.json').read_text(encoding='utf8'))
items={r['dwStringID']:r for table in rows['tables'] for r in table['rows']}
for template,types in PART_TYPES.items():
    if (tuple(items[template]['WeaponPartTypeCanUseArray'])!=types
            or tuple(items[template]['WeaponPartIndexCanUseArray'])!=PART_INDICES[template]):
        raise ValueError(f'Original weapon part matrix differs: {template}')
for template,spec in EXTRA_ITEMS.items():
    if items[template]['nDurableValue']!=spec.durability:
        raise ValueError(f'Original durability differs: {template}')

c=NativeCodec()
requests=[]
factory=[]
object_address=0x10a00000


def capture_factory(uc,a,s,user):
    ret,template,quantity=struct.unpack('<3I',uc.mem_read(uc.reg_read(UC_X86_REG_ESP),12))
    factory.append((template,quantity))
    uc.mem_write(object_address,bytes(0x100))
    uc.mem_write(object_address+0x40,struct.pack('<I',object_address+0x80))
    uc.reg_write(UC_X86_REG_EAX,object_address)
    uc.reg_write(UC_X86_REG_EIP,ret)
    uc.reg_write(UC_X86_REG_ESP,uc.reg_read(UC_X86_REG_ESP)+4)


c.uc.hook_add(UC_HOOK_CODE,capture_factory,begin=0xfe8740,end=0xfe8740)


def check(message,body):
    result=c.decode_server(message,body)
    if result['code'] or result['consumed']!=result['bytes']:
        raise ValueError(f'Incomplete original decode {message:#x}: {result}')
    requests.append(message)


iv=OfflineInventory()
gun=iv.items[1,1]
for template in (40303,40305):
    part=Item(4,template,iv.next_uid,1)
    iv.next_uid+=1
    iv.items[2,1]=part
    request=part_request(part.uid,2,1,gun.uid,3,2)
    check(0x3e80,request)
    dto=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,0x50b))
    if (dto[0]!=6 or struct.unpack_from('<Q',dto,1)[0]!=part.uid
            or struct.unpack_from('<Q',dto,12)[0]!=gun.uid
            or dto[20]!=3 or struct.unpack_from('<H',dto,21)[0]!=2 or dto[0x50a]!=1):
        raise ValueError('Original attachment request fields differ')
    for packet in iv.handle(request):check(*packet)
    check(*iv.delta([(1,1)]))
    native=bytes(c.uc.mem_read(c.ROOT_OBJECT+14,0x142))
    if (struct.unpack_from('<I',native,0xbe)[0]!=2
            or struct.unpack_from('<3I',native,0xc2)!=(2,template,0)):
        raise ValueError('Selected scope does not reach the original bounded attachment rows')
    code,wire=c.pack_type(0xd6b670,native)
    if code or wire!=iv.items[1,1].wire():
        raise ValueError('Original item writer does not reproduce installed gun')
for packet in iv.handle(part_request(gun.uid,3,2,0,2,2)):check(*packet)
if iv.items[1,1].parts or iv.items[2,2].template!=40305:
    raise ValueError('Detaching did not conserve the part')

durability=[]
for template,spec in EXTRA_ITEMS.items():
    if spec.kind not in (7,20):continue
    quantity=5 if spec.kind==7 else 1
    item=Item(spec.kind,template,0x110000+template,quantity)
    iv.items={(2,0):item}
    check(*iv.delta([(2,0)]))
    native=bytes(c.uc.mem_read(c.ROOT_OBJECT+14,0x142))
    code,wire=c.pack_type(0xd6b670,native)
    if code or wire!=item.wire():raise ValueError('Original new-item writer differs')
    c.uc.mem_write(c.OBJECT,native)
    c.invoke(0xfe87b0,0,[c.OBJECT])
    if factory[-1]!=(template,quantity):raise ValueError('Original item factory quantity differs')
    if spec.kind==20:
        value=c.invoke(0x1ad7c20,object_address,[])
        if value!=spec.durability:raise ValueError('Original durability getter differs')
        durability.append((template,value))

report=dict(passed=True,messages=len(requests),weapon_matrices=len(PART_TYPES),
    durability=durability,limitation='Synthetic factory allocation; no rendering, healing, damage or weapon-stat proof')
(ROOT/'private/typed-gameplay/equipment-actions-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
