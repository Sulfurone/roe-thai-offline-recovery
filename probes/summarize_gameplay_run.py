"""Summarize actual client reports without treating sent replies as acceptance."""
import argparse
import collections
import json
import struct
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('folder',type=Path)
a=p.parse_args()
blob=(a.folder/'1-application.bin').read_bytes()
position=0
counts=collections.Counter()
reports=[]
while position+4<=len(blob):
    length=struct.unpack_from('>I',blob,position)[0]
    if length<26 or position+length>len(blob):
        break
    packet=blob[position:position+length]
    message=struct.unpack_from('>H',packet,4)[0]
    body=packet[26:]
    counts[message]+=1
    row={'offset':position,'message':hex(message),'body_bytes':len(body)}
    position+=length
    if message==0x2a and len(body)>=16:
        row['position']=struct.unpack_from('>3i',body,4)
    elif message==0x6549 and len(body)>=25:
        row['uid']=hex(struct.unpack_from('>Q',body)[0])
        row['position']=struct.unpack_from('>3i',body,13)
    elif message==0x3b63 and len(body) in (33,41):
        values=struct.unpack('>IIQBHB3iB',body[:33])
        row['entity_id'],row['ground_slot']=values[:2]
        row['destination_owner']=hex(values[2])
        row['destination_container'],row['destination_slot'],row['automatic']=values[3:6]
        row['camera_position']=values[6:9]
        row['body_hex']=body.hex()
    elif message in (0x49c,0x49e,0x11d3,0x11ec,0x6541,0x6543,0x6547,0x6572,0x6566,0x3e80):
        row['body_hex']=body.hex()
    else:
        continue
    reports.append(row)
events=[]
for line in (a.folder/'server.jsonl').read_text(encoding='utf-8').splitlines():
    try:
        row=json.loads(line)
    except json.JSONDecodeError:
        continue
    if row['event'].startswith(('gameplay_','scene_loaded_','player_ready_')):
        events.append(row)
result={'folder':str(a.folder),'parsed_bytes':position,'captured_bytes':len(blob),
        'counts':{hex(k):v for k,v in counts.most_common()},
        'client_reports':reports,'server_events':events}
(a.folder/'gameplay-evidence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
