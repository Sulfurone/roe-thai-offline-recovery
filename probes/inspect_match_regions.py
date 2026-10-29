"""Inspect owned Thai map-region masks privately; no mode semantics inferred.

This reads only two named SFC resources. Raw masks and diagnostic reports stay
under private/. A color index alone does not prove danger-zone progression.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sfc_extract import lz4_block
from offline_collision_assets import sfc_path_key

paths={}
for kind in ('BASEAREA','MAPZONE'):
    name='BASE' if kind=='BASEAREA' else 'MAPZONE'
    resource=f'DATA/WORLD/EU_KILLZONE_2048/AREAINDEX/{kind}/AREAINDEXFILE_{name}.DDS'
    paths[sfc_path_key(resource)]=resource
archive=ROOT.parent/'32838/SFC/World_EU_KillZone_2048_RemainingFiles.sfc'
if not 8<=archive.stat().st_size<=256*1024*1024:raise ValueError('Archive exceeds local scan bounds')
data=archive.read_bytes()
if data[:8]!=b'SFC\x1a\x02\0\0\0':raise ValueError('Unknown SFC version')
folder=ROOT/'private/match-regions'
folder.mkdir(parents=True,exist_ok=True)
cursor=8;found={}
while cursor<len(data):
    if cursor+16>len(data):raise ValueError('Truncated SFC record')
    key=data[cursor:cursor+8]
    packed=struct.unpack_from('<I',data,cursor+8)[0]
    end=cursor+12+packed
    if end+4>len(data):raise ValueError('SFC record exceeds archive')
    if key in paths:
        size=struct.unpack_from('<I',data,end)[0]
        if not 128<=size<=32*1024*1024:raise ValueError('Mask exceeds local extraction bounds')
        raw=lz4_block(data[cursor+12:end],size)
        name=paths[key].rsplit('/',1)[-1]
        (folder/name).write_bytes(raw)
        found[key]=dict(resource=paths[key],key=key.hex(),bytes=len(raw),
                        sha256=hashlib.sha256(raw).hexdigest())
    cursor=end+4
if set(found)!=set(paths):raise ValueError(f'Missing masks: {len(found)}/{len(paths)}')
for key,row in found.items():
    path=folder/row['resource'].rsplit('/',1)[-1]
    raw=path.read_bytes()
    if raw[:4]!=b'DDS ' or struct.unpack_from('<I',raw,4)[0]!=124:raise ValueError('Unknown DDS header')
    height,width,pitch=struct.unpack_from('<III',raw,12)
    if not 1<=width<=2048 or not 1<=height<=2048 or width*height>4194304:
        raise ValueError('Mask pixel count exceeds bound')
    if (pitch!=4*width or len(raw)!=128+pitch*height or
            struct.unpack_from('<8I',raw,76)!=(32,65,0,32,0xff0000,0xff00,0xff,0xff000000)):
        raise ValueError('Only the verified uncompressed A8R8G8B8 mask is supported')
    counts=Counter((raw[p+2],raw[p+1],raw[p],raw[p+3]) for p in range(128,len(raw),4))
    row.update(size=(width,height),format='A8R8G8B8',colors=len(counts),
               most_common=[dict(rgba=color,pixels=count) for color,count in counts.most_common(24)])
report=dict(archive=archive.name,masks=list(found.values()),
    limitation='Private owned-resource inspection only; color IDs, coordinate orientation, gameplay activation and original match rules are not inferred')
(folder/'inspection.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report))
