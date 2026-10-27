"""Original Thai codec validation for dynamically generated ground loot."""
import json
import struct
import sys
from pathlib import Path
from native_codec_probe import NativeCodec,OUT

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from offline_gameplay import OfflineGameplay,TYPED_ACTOR_UID
from test_ground_loot import request,drop

c=NativeCodec()
game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,actor_uid=TYPED_ACTOR_UID)
report=[]
for name,message,body in [
    ('spawn',0x2a,struct.pack('>I3i',1,325800,271700,6488)),
    ('pickup',0x3b63,request()),('drop',0x3e80,drop()),
    ('repickup',0x3b63,request(0x400002)),('duplicate',0x3b63,request(0x400002))]:
    replies=game.handle(message,body)
    for reply,payload in replies:
        result=c.decode_server(reply,payload)
        if result['code'] or result['consumed']!=len(payload)+10:
            raise ValueError(f'{name} {reply:#x}: {result}')
        report.append(dict(operation=name,message=hex(reply),body_bytes=len(payload),**result))
    if name=='spawn':
        native=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,0x20a))
        if struct.unpack_from('<I',native,0x6d)[0]!=1 or native[0x7d]!=2:
            raise ValueError('Not an original single-item entity')
        if struct.unpack_from('<3I',native,0x7e)!=(30001,60,0x400001):
            raise ValueError('Original item template/count/entity fields differ')
assert game.reserve==180 and not game.ground_loot.stacks
# Exercise a partly loaded original M4A1, not a fresh replacement gun.
game.magazine=28
for name,message,body in [
    ('weapon-drop',0x3e80,drop(1,container=1,slot=1)),
    ('weapon-pickup',0x3b63,request(0x400003,container=1,destination=2,automatic=0))]:
    for reply,payload in game.handle(message,body):
        result=c.decode_server(reply,payload)
        if result['code'] or result['consumed']!=len(payload)+10:
            raise ValueError(f'{name} {reply:#x}: {result}')
        if reply==0x821:
            native=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,0x20a))
            if struct.unpack_from('<3I',native,0x7e)!=(10201,1,0x400003):
                raise ValueError('Original single-weapon entity fields differ')
            code,repacked=c.pack_type(0xdca9f0,native)
            if code or repacked!=payload:
                raise ValueError('Original weapon entity writer produces different bytes')
        if reply==0x3b64:
            native=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,21))
            if native[8]!=1 or struct.unpack_from('<3I',native,9)!=(10201,1,0):
                raise ValueError('Original weapon pickup notice union differs')
        report.append(dict(operation=name,message=hex(reply),body_bytes=len(payload),**result))
assert game.magazine==28 and game.inventory.weapon_slot()==2 and not game.ground_loot.stacks
path=OUT.parent/'typed-gameplay/ground-loot-dynamic-validation.json'
path.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
