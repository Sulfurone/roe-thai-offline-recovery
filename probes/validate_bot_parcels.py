"""Decode the local death container and every Thai container item variant."""
import json
import struct
import sys
from native_codec_probe import NativeCodec, ROOT

sys.path.insert(0,str(ROOT))
from test_bot_parcels import setup_parcels
from offline_weapons import is_weapon

codec=NativeCodec()
game,bots,ai,parcels=setup_parcels()
packets=parcels.drop(bots.FIRST_UID)
entity=next(iter(parcels.parcels))
contents=parcels.contents(entity)
packets.append(contents)
items=dict(parcels.parcels[entity][1])
parcels.handle(0xbce,struct.pack('>QQ',entity,game.actor_uid))
for slot in items:
    packets.extend(parcels.handle(0x3b63,struct.pack('>IIQBHB3iB',
        entity,slot,game.actor_uid,0,0,1,*game.player_position,0)))
checks=[]
for message,body in packets:
    result=codec.decode_server(message,body)
    if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
    if (message,body)==contents:
        start=codec.ROOT_OBJECT+10
        decoded=bytes(codec.uc.mem_read(start,8+20*len(items)))
        if struct.unpack_from('<II',decoded)!=(entity,len(items)):
            raise ValueError('Native parcel header differs')
        for slot,stack in items.items():
            item=stack.item
            expected=(slot,item.kind if is_weapon(item) else 3,item.template,item.count)
            if struct.unpack_from('<4I',decoded,8+20*(slot-1))!=expected:
                raise ValueError(f'Native parcel slot {slot} differs')
    checks.append(dict(message=hex(message),body_bytes=len(body),decode=result))
report=dict(passed=True,slots=len(items),checks=checks,limitation='Original DTO decode; model and search UI require live confirmation')
(ROOT/'private/typed-gameplay/bot-parcels-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
