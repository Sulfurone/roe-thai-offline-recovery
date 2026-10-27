"""Reconstruct this local inventory self-test from recorded request order.

Creates a new checkpoint only; never overwrites an existing profile.
The simulated inventory stages come from the recorded server events.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from offline_gameplay import OfflineGameplay

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('folder',type=Path)
p.add_argument('destination',type=Path)
a=p.parse_args()
if a.destination.exists():
    raise ValueError('Destination profile already exists; preserve it')
blob=(a.folder/'1-application.bin').read_bytes()
packets=[]
offset=0
while offset+26<=len(blob):
    size=struct.unpack_from('>I',blob,offset)[0]
    if size<26 or offset+size>len(blob):
        raise ValueError('Incomplete capture')
    packet=blob[offset:offset+size]
    packets.append((struct.unpack_from('>H',packet,4)[0],packet[26:]))
    offset+=size
if offset!=len(blob):
    raise ValueError('Trailing partial capture')
game=OfflineGameplay(inventory_enabled=True)
stages=set()
index=0
last_response=None
moves=[(2,0,2,5,30),(1,1,1,2,1),(1,2,1,1,1)]
for line in (a.folder/'server.jsonl').read_text(encoding='utf-8').splitlines():
    row=json.loads(line)
    if row['event']=='application_message':
        message,body=packets[index]
        if row['message_id']!=message or row['bytes']!=26+len(body):
            raise ValueError('Application log/capture order differs')
        game.handle(message,body)
        index+=1
    elif row['event']=='gameplay_timer_response_sent' and row.get('diagnostic')=='inventory self-test':
        stage=row['inventory_stage']
        if stage not in (1,2,3):
            raise ValueError('Unknown automatic inventory stage')
        if stage not in stages:
            game.handle(0x3e80,struct.pack('>BBHBHHB',1,*moves[stage-1],1))
            stages.add(stage)
    elif row['event']=='gameplay_response_sent':
        last_response=row
if index!=len(packets) or stages!={1,2,3} or last_response is None:
    raise ValueError('Not a complete supported inventory self-test')
if (game.magazine,game.reserve)!=(last_response['magazine'],last_response['reserve']):
    raise ValueError('Reconstructed ammunition differs from the live service')
payload=game.state_payload()
game.inventory.restore(json.loads(payload))
a.destination.parent.mkdir(parents=True,exist_ok=True)
with a.destination.open('x',encoding='utf-8') as target:
    target.write(payload)
evidence={'source':str(a.folder),'destination':str(a.destination),
          'application_count':index,'automatic_stages':sorted(stages),
          'magazine':game.magazine,'reserve':game.reserve,
          'selected_slot':game.selected_slot,'items':len(game.inventory.items)}
(a.folder/'inventory-checkpoint-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
print(json.dumps(evidence,indent=2))
