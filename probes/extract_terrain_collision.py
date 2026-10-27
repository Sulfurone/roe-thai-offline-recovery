"""Extract only the Thai map's verified zlib chunks, without modifying game files."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT/'extracted/thai_vfs0/vfs-manifest.json').read_text())
entry, = [e for e in manifest['entries']
          if e['name'].endswith('EU_KILLZONE_2048\\KILLZONE_001\\RIGIDTERRAIN.REPX')]
if entry['flags'] != 0x40000001 or not 0 < entry['size'] < 128*1024*1024:
    raise ValueError('Unexpected terrain entry format or size')
chunk_size = 0x400000  # Local references/dzs_qq.bms chunk layout.
count = (entry['size']+chunk_size-1)//chunk_size
with Path(manifest['source']).open('rb') as source:
    source.seek(entry['offset'])
    header = source.read(16)
    if header[:4] != b'data':
        raise ValueError('Terrain data marker changed')
    sizes = struct.unpack('<'+'I'*count,source.read(count*4))
    if sum(sizes)+count*4 != entry['compressed']:
        raise ValueError('Chunk table does not match indexed compressed size')
    chunks = []
    for i,n in enumerate(sizes):
        if not 0 < n <= chunk_size:
            raise ValueError('Compressed chunk exceeds extraction bound')
        data = source.read(n)
        decoder = zlib.decompressobj()
        expected = min(chunk_size,entry['size']-i*chunk_size)
        raw = decoder.decompress(data,expected+1)
        if len(raw)!=expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('Chunk failed exact zlib/size validation')
        chunks.append(raw)
raw = b''.join(chunks)
folder = ROOT/'private/terrain-collision'
folder.mkdir(exist_ok=True)
destination = folder/'RigidTerrain.repx'
destination.write_bytes(raw)
report = {'source':entry['name'],'chunks':count,'bytes':len(raw),
          'sha256':hashlib.sha256(raw).hexdigest(),'path':str(destination)}
(folder/'extraction.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
print(raw[:1800].decode('utf-8',errors='replace'))
