"""Read selected small gameplay resources from the original Thai VFS."""
import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('pattern')
args = p.parse_args()
manifest = json.loads((ROOT/'extracted/thai_vfs0/vfs-manifest.json').read_text(encoding='utf-8'))
entries = [e for e in manifest['entries'] if e.get('name') and e['offset'] and re.search(args.pattern, e['name'], re.I)]
if not entries or len(entries)>16 or sum(e['size'] for e in entries)>32*1024*1024:
    raise ValueError('Selection must contain 1..16 small files, total <=32 MiB')
folder = ROOT/'private/gameplay-catalog'
folder.mkdir(exist_ok=True)
reports = []
with Path(manifest['source']).open('rb') as source:
    for e in entries:
        if not 0<e['size']<=8*1024*1024 or not 0<e['compressed']<=8*1024*1024:
            raise ValueError('Resource exceeds extraction bound')
        source.seek(e['offset'])
        if source.read(16)[:4]!=b'data':
            raise ValueError('Missing VFS data marker')
        payload = source.read(e['compressed'])
        if len(payload)!=e['compressed']:
            raise ValueError('Truncated original resource')
        if not e['flags']&1 and e['size']==e['compressed']:
            raw = payload
        else:
            if payload[:1]==b'\x78':
                chunks = [(payload,e['size'])]
            else:
                count = (e['size']+0x3fffff)//0x400000
                sizes = struct.unpack_from('<'+'I'*count,payload)
                if sum(sizes)+4*count!=len(payload):
                    raise ValueError('Invalid VFS compressed chunk table')
                cursor = 4*count
                chunks = []
                for i,size in enumerate(sizes):
                    chunks.append((payload[cursor:cursor+size],min(0x400000,e['size']-i*0x400000)))
                    cursor += size
            decoded = []
            for data,expected in chunks:
                decoder = zlib.decompressobj()
                part = decoder.decompress(data,expected+1)
                if len(part)!=expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                    raise ValueError('Compressed resource failed exact validation')
                decoded.append(part)
            raw = b''.join(decoded)
        if len(raw)!=e['size']:
            raise ValueError('Decoded resource size mismatch')
        destination = folder/f"{e['index']}-{PureWindowsPath(e['name']).name}"
        destination.write_bytes(raw)
        reports.append(dict(name=e['name'],path=str(destination),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
(folder/'extraction.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
print(json.dumps(reports,indent=2))
