"""Inspect private QSHM/road mask/door data without modifying the client."""
import argparse
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--sample', type=float, nargs=3, action='append', default=[])
args = p.parse_args()
folder = ROOT/'private/client-map/World_EU_KillZone_2048_RemainingFiles'
tiles = {}
for path in folder.glob('TERRAINHEIGHTTILE_*.QSHM'):
    x, y = map(int, path.stem.rsplit('_', 2)[1:])
    raw = path.read_bytes()
    if struct.unpack_from('<II', raw, 4) != (257, 257) or len(raw) != 132110:
        raise ValueError('Unknown QSHM grid format')
    tiles[x, y] = raw
print('tiles', len(tiles))

def height(x, y, swaptiles=False, swapsamples=False):
    column, row = x/200, y/200
    i, j = int(column)//256, int(row)//256
    u, v = round(column-i*256), round(row-j*256)
    raw = tiles[(j, i) if swaptiles else (i, j)]
    at = u*257+v if swapsamples else v*257+u
    return struct.unpack_from('<H', raw, 12+at*2)[0]*1.83108

for tile_order in (False, True):
    for sample_order in (False, True):
        for mirror_x in (False, True):
            print('mapping', tile_order, sample_order, mirror_x,
                  [round(height(409600-x if mirror_x else x, y, tile_order, sample_order))
                   for x, y, z in args.sample])
text = (folder/'ENTITYSTATUSINPXSCENE.XML').read_text(encoding='utf-8-sig')
root = ET.fromstring(re.sub(r'\s+\[XlsProp\]="[^"]*"', '', text))
rows = list(root.iter('mTable'))
print('scene objects', len(rows), 'sample', rows[0].attrib)
doors = [row for row in rows if row.find('mSwitcherStatus') is not None]
if args.sample:
    x, y, _ = args.sample[-1]
    near = sorted(doors, key=lambda row: (float(row.get('mPosX'))-x)**2 + (float(row.get('mPosY'))-y)**2)[:3]
    print('near door metadata', [(row.attrib, row.find('mSwitcherStatus').attrib) for row in near])
road = (folder/'ROADMASK.DDS').read_bytes()
print('road header', struct.unpack_from('<7I', road, 4), road[76:128].hex())
print('road sample bytes', list(road[128:160]))
print('road channel histograms', [Counter(road[128+index::4]).most_common(6) for index in range(4)])
static_text = (folder/'RIGIDSTATICINPXSCENE.XML').read_text(encoding='utf-8-sig')
static_root = ET.fromstring(re.sub(r'\s+\[XlsProp\]="[^"]*"', '', static_text))
static_rows = list(static_root.iter('mTable'))
print('static rows', len(static_rows), 'samples', [row.attrib for row in static_rows[:3]])
print('static root', static_root.tag, static_root.attrib,
      [(child.tag, child.attrib, (child.text or '')[:160]) for child in list(static_root)[:3]])
if len(static_rows) > 1:
    print('static first row children', [(child.tag, child.attrib, (child.text or '')[:160]) for child in static_rows[1]][:8])
try:
    from PIL import Image
    image = Image.open(folder/'ROADMASK.DDS')
    image.thumbnail((768,768))
    image.save(folder.parent/'roadmask-preview.png')
    print('road preview saved privately')
except ImportError:
    pass
