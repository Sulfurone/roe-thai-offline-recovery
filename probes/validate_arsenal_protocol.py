"""Validate 20 firearm and six ammunition variants with original Thai codecs."""
import collections
import json
from pathlib import Path
import struct
import sys
from native_codec_probe import NativeCodec

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from offline_gameplay import OfflineGameplay,TYPED_ACTOR_UID
from offline_weapons import WEAPONS,AMMUNITION
from test_ground_loot import request,drop

c=NativeCodec()
game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,arsenal_enabled=True,actor_uid=TYPED_ACTOR_UID)
counts=collections.Counter()
variants=set()

def check(name,replies):
    for message,payload in replies:
        decoded=c.decode_server(message,payload)
        if decoded['code'] or decoded['consumed']!=len(payload)+10:
            raise ValueError(f'{name} {message:#x}: {decoded}')
        if message==0x821:
            native=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,0x20a))
            code,repacked=c.pack_type(0xdca9f0,native)
            if code or repacked!=payload:raise ValueError(f'{name} native spawn writer differs')
        if message==0x3b64:
            native=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,21))
            if native[8] not in (1,2,3):raise ValueError('Unexpected pickup union kind')
            variants.add(native[8])
        counts[message]+=1

def pick(template):
    stack=next(x for x in game.ground_loot.stacks.values() if x.item.template==template)
    check('movement',game.handle(0x2a,struct.pack('>I3i',1,*stack.position)))
    replies=game.handle(0x3b63,request(stack.entity))
    if not replies or replies[0][0]!=0x3e82:raise ValueError(f'Cannot pick {template}')
    check('pickup',replies)

check('initial entities',game.handle(0x2a,struct.pack('>I3i',1,325800,271700,6488)))
for template in sorted(AMMUNITION):pick(template)
check('drop initial',game.handle(0x3e80,drop(0,container=1,slot=1)))
for template,spec in sorted(WEAPONS.items()):
    pick(template)
    slot=spec.slots[0]
    check('whole inventory',[(0x5fb,game.inventory.full_body())])
    check('select',game.handle(0x49e,struct.pack('>I',slot)))
    check('reload',game.handle(0x49c,struct.pack('>I',slot)))
    if game.magazine>spec.capacity:raise ValueError('Incorrect magazine capacity')
    if game.magazine:
        check('shot',game.handle(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,1,0)))
    check('drop weapon',game.handle(0x3e80,drop(0,container=1,slot=slot)))
if variants!={1,2,3}:raise ValueError('Missing original pickup union variants')
report={'firearms_checked':len(WEAPONS),'ammunition_checked':len(AMMUNITION),
        'pickup_union_kinds':sorted(variants),'decoded_messages':{hex(k):v for k,v in counts.items()},
        'total_decoded':sum(counts.values()),'spawn_repacked_by_original_writer':counts[0x821],
        'limitation':'Native codec execution and synthetic single-player interaction; no live rendering or real key input'}
path=ROOT/'private/typed-gameplay/arsenal-codec-validation.json'
path.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
