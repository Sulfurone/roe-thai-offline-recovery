"""Extract only own-client height tiles/road mask/scene catalogues privately.

Uses verified SFC v2 indexing and name hashing. No original file is changed;
archive variants remain separate for comparison against actual walking data.
"""
import json
from pathlib import Path
import struct
import sys
import argparse
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sfc_extract import lz4_block
from vfs_extract import Archive

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--client',type=Path,default=ROOT.parent/'32838')
args = parser.parse_args()
client = args.client
names = [name for name in Archive(client/'data_bas_4.vfs').names if name]
selected = [name for name in names if 'EU_KILLZONE_2048' in name and
            ('TERRAINHEIGHTTILE_' in name or name.endswith(('ROADMASK.DDS', 'HEIGHTMAPEXPORT.RAW',
             'ENTITYSTATUSINPXSCENE.XML', 'ENTITYIDMAPPING.XML', 'RIGIDSTATICINPXSCENE.XML')))]

def name_key(name):
    value = 0x2e31f418d34d0915
    for byte in name.replace('/', '\\').upper().encode('ascii'):
        value = (value*67 + byte) & (2**64-1)
    return value.to_bytes(8, 'little')

wanted = {name_key(name): name for name in selected}
archives = [client/'SFC/World_EU_KillZone_2048_RemainingFiles.sfc',
            client/'data_org_dyn.sfc', client/'data_dyn.sfc']
output = ROOT/'private/client-map'
output.mkdir(exist_ok=True)
report = []
for archive in archives:
    if not archive.exists():
        continue
    if archive.stat().st_size > 512*1024*1024:
        raise ValueError('Archive exceeds bounded local scan')
    data, cursor, found = archive.read_bytes(), 8, []
    if data[:8] != b'SFC\x1a\x02\0\0\0':
        raise ValueError('Unexpected SFC format')
    while cursor + 16 <= len(data):
        key = data[cursor:cursor+8]
        packed = struct.unpack_from('<I', data, cursor+8)[0]
        end = cursor+12+packed
        if end+4 > len(data):
            raise ValueError('SFC record boundary exceeds archive')
        if key in wanted:
            size = struct.unpack_from('<I', data, end)[0]
            if size > 128*1024*1024:
                raise ValueError('Map resource exceeds extraction bound')
            raw = b'' if not size else lz4_block(data[cursor+12:end], size)
            folder = output/archive.stem
            folder.mkdir(exist_ok=True)
            filename = wanted[key].rsplit('\\', 1)[-1]
            (folder/filename).write_bytes(raw)
            found.append(dict(name=wanted[key], bytes=len(raw), header=raw[:40].hex()))
        cursor = end+4
    report.append(dict(archive=archive.name, found=found))
    print(json.dumps(dict(archive=archive.name, found=len(found),
                         samples=[x for x in found if 'TERRAINHEIGHTTILE_0_0' in x['name'] or
                                  x['name'].endswith(('ROADMASK.DDS','ENTITYSTATUSINPXSCENE.XML'))])),flush=True)
(output/'extraction.json').write_text(json.dumps(report,indent=2))
