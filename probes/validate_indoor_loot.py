"""Check sampled indoor floors using privately owned Thai collision assets.

Only this script ships publicly, not scene data, geometry or the report.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from offline_client_map import ThaiClientMap
from offline_visibility import StaticVisibility
from offline_indoor_loot import IndoorFloors

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--map',type=Path,default=ROOT/'private/client-map/World_EU_KillZone_2048_RemainingFiles')
parser.add_argument('--archives',type=Path,default=ROOT.parent/'32838/SFC')
parser.add_argument('--out',type=Path,default=ROOT/'private/typed-gameplay/indoor-loot-validation.json')
args=parser.parse_args()
started=time.monotonic()
terrain=ThaiClientMap.from_folder(args.map)
visibility=StaticVisibility.from_scene(terrain,args.map/'RIGIDSTATICINPXSCENE.XML',args.archives)
print(json.dumps(dict(event='collision_prepared',seconds=round(time.monotonic()-started,2))),flush=True)
finder=IndoorFloors(visibility)
rows=[]
# Actual multi-storey model labels select the test population; they do not
# supply guessed heights. Floor Z still comes from collision intersections.
from offline_client_map import read_scene
for row in read_scene(args.map/'RIGIDSTATICINPXSCENE.XML','RigidStaticInPxScene').iter('mItems'):
    if not row.get('mID') or not any(tag in row.get('mModelName','').upper() for tag in ('MJ_2FLOOR_','MJ_3FLOOR_')):continue
    house=tuple(float(row.get(k)) for k in ('mBoundingX','mBoundingY','mBoundingRadius','mPosZ'))
    if house not in terrain.houses:continue
    points=finder.candidates(house)
    levels=sorted({p[2] for p in points})
    rows.append(dict(points=len(points),levels=levels,upstairs=bool(levels and levels[-1]-levels[0]>200)))
    print(json.dumps(dict(event='building_checked',number=len(rows),**rows[-1])),flush=True)
    if len(rows)>=12:break
report=dict(passed=any(r['upstairs'] for r in rows),buildings=rows,seconds=round(time.monotonic()-started,2),
    limitation='Source collision support/ceiling evidence only; not original loot nodes or live pickup/room access proof')
args.out.parent.mkdir(parents=True,exist_ok=True)
args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report))
if not report['passed']:raise SystemExit(1)
