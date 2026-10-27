"""Validate selected original SFC blocks and look for aircraft asset markers.

Only a private metadata report is written. Absence of a plaintext marker
does not prove that a hashed resource is missing from the installation.
"""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-libs'))
import lz4.block

folder=ROOT.parent/'32838/SFC'
reports=[]
archives=[folder/name for name in ('All_QSS.sfc','Actors_HELICOPTER.sfc','Avatars_Skin_RemainingFiles.sfc')]
archives.append(ROOT.parent/'32838/Cache/otherbin.sfc')
for path in archives:
    name=path.name
    if path.stat().st_size>256*1024*1024:
        raise ValueError('Archive outside audit size limit')
    blob=path.read_bytes()
    if blob[:8]!=b'SFC\x1a\x02\0\0\0':
        raise ValueError('Unexpected SFC header')
    cursor,count,unpacked=8,0,0
    matches=[]
    while cursor<len(blob):
        if cursor+16>len(blob):raise ValueError('Truncated SFC record')
        key=blob[cursor:cursor+8].hex()
        packed=struct.unpack_from('<I',blob,cursor+8)[0]
        end=cursor+12+packed
        if end+4>len(blob):raise ValueError('Record exceeds archive')
        raw=struct.unpack_from('<I',blob,end)[0]
        if raw>256*1024*1024:raise ValueError('Record outside decoded size limit')
        decoded=b'' if raw==packed==0 else lz4.block.decompress(blob[cursor+12:end],uncompressed_size=raw)
        if len(decoded)!=raw:raise ValueError('Decoded SFC size differs')
        if re.search(rb'c17|helicopter|engine4',decoded,re.I):
            markers=[s.decode('ascii') for s in re.findall(rb'[ -~]{6,}',decoded)
                     if re.search(rb'c17|helicopter|engine4',s,re.I)][:12]
            matches.append(dict(key=key,raw_bytes=raw,markers=markers))
        count+=1
        unpacked+=raw
        cursor=end+4
    row=dict(archive=name,sha256=hashlib.sha256(blob).hexdigest(),records=count,
        validated_unpacked_bytes=unpacked,plaintext_marker_matches=matches)
    reports.append(row)
    print(json.dumps(row),flush=True)
report=dict(archives=reports,scope='Selected archive integrity and markers only; no complete filename-to-key lookup or rendering verification')
out=ROOT/'private/native-roster/aircraft-resource-audit.json'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,indent=2),encoding='utf-8')
