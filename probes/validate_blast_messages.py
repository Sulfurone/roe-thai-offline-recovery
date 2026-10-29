"""Feed completed local frag damage into original Thai HP/death consumers.

Reuses explicit synthetic lookup/FSM/UI boundaries from the combat probe.
No game renderer, original grenade physics or original damage formula runs.
"""
import json
import runpy
from native_codec_probe import ROOT

namespace=runpy.run_path(str(ROOT/'probes/validate_combat_messages.py'))
c,props,context=(namespace[name] for name in ('c','props','context'))
for address in (0x13a8100,0x13a8110):
    namespace['hook'](address,lambda:namespace['done']())

from test_blast import setup,release

checks=[]
for distance,expected in ((500,331),(0,0)):
    game,bots,blast=setup(())
    game.actor_uid=namespace['own']
    c.uc.mem_write(props+0x7ec,b'\xdb')
    c.uc.mem_write(props+0x178,b'\xda')
    c.uc.mem_write(context+0x85,b'\0')
    mid,body=game.vitals.packet(game.actor_uid)
    decoded=c.decode_server(mid,body)
    if decoded['code'] or decoded['consumed']!=decoded['bytes']:raise ValueError(decoded)
    c.invoke(0x127b320,0,[c.ROOT_OBJECT+6])
    point=(game.player_position[0]+distance,*game.player_position[1:])
    event,_,_=release(game,point)
    packets=blast.complete(event,100)
    for mid,body in packets:
        decoded=c.decode_server(mid,body)
        if decoded['code'] or decoded['consumed']!=decoded['bytes']:raise ValueError(decoded)
        c.invoke(0x127b320 if mid==0x1069 else 0x127b230,0,[c.ROOT_OBJECT+6])
    actual=c.invoke(0x139fa40,0,[])
    death=c.uc.mem_read(props+0x178,1)[0]
    if actual!=expected or death!=(0xdc if expected==0 else 0xda):
        raise ValueError(f'Original blast HP/death differs: {actual}/{death:#x}')
    checks.append(dict(distance=distance,current=actual,death_tag=hex(death),
                       messages=[hex(mid) for mid,body in packets]))
report=dict(passed=True,checks=checks,limitation=__doc__.strip())
(ROOT/'private/typed-gameplay/blast-message-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
