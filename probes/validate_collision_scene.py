"""Own Thai source primitives and world queries, without launching the client."""
import json
import math
import random
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from offline_client_map import ClientHeightfield,read_scene,HOUSE_MODEL
from offline_collision import Instance,rotate,euler_xyz
from offline_collision_assets import CollisionAssets
from offline_visibility import StaticVisibility

folder=ROOT/'private/client-map/World_EU_KillZone_2048_RemainingFiles'
terrain=ClientHeightfield.from_folder(folder)
scene=folder/'RIGIDSTATICINPXSCENE.XML'
assets=ROOT.parent/'32838/SFC'
visibility=StaticVisibility.from_scene(terrain,scene,assets)
rows=[r for r in read_scene(scene,'RigidStaticInPxScene').iter('mItems')
      if r.get('mID') and HOUSE_MODEL.fullmatch(r.get('mModelName',''))]
rows.sort(key=lambda r:math.hypot(float(r.get('mPosX'))-325800,float(r.get('mPosY'))-271700))
checked=[];control=None;rng=random.Random(8029)
started=time.monotonic()
for row in rows:
    path=row.get('mModelFullPath')
    if path in {r['path'] for r in checked}:continue
    model=visibility.assets.get(path)
    checked.append(dict(path=path,shapes=len(model.shapes) if model else None,
                        failure=visibility.assets.failures.get(path.casefold())))
    if model is not None and control is None:
        instance=Instance(path,tuple(float(row.get('mPos'+a)) for a in 'XYZ'),
            tuple(float(row.get('mRotate'+a)) for a in 'XYZ'),float(row.get('mScale')))
        def world(p):return tuple(a+b for a,b in zip(instance.position,rotate(euler_xyz(instance.angles),tuple(v*instance.scale for v in p))))
        bound=tuple(float(row.get(k)) for k in ('mBoundingX','mBoundingY','mBoundingZ','mBoundingRadius'))
        for _ in range(500):
            p=tuple(rng.uniform(a,b) for a,b in zip(model.root.lower,model.root.upper))
            q=(p[0]+100,p[1],p[2])
            if model.blocks(p,q):continue
            a,b=world(p),world(q)
            if visibility.distance_to_segment(bound[:3],a,b)>bound[3]:continue
            if not visibility.clear(a,b):continue
            shape=model.shapes[0];centre=tuple((x+y)/2 for x,y in zip(shape.lower,shape.upper))
            wall_a,wall_b=world((centre[0]-100,*centre[1:])),world((centre[0]+100,*centre[1:]))
            if visibility.clear(wall_a,wall_b):continue
            control=dict(scene_id=row.get('mID'),inside_clear=True,wall_blocked=True,
                         start=a,end=b,wall_start=wall_a,wall_end=wall_b)
            break
    if len(checked)>=8 and control is not None:break
    if len(checked)>=16:break
if control is None:raise ValueError('No actual-map room gap plus wall control found')
timings=[]
for _ in range(100):
    before=time.perf_counter()
    if not visibility.clear(control['start'],control['end']):raise ValueError('Gap control changed')
    if visibility.clear(control['wall_start'],control['wall_end']):raise ValueError('Wall control changed')
    timings.append(time.perf_counter()-before)
report=dict(passed=True,checked=checked,control=control,seconds=time.monotonic()-started,
    prepared=visibility.assets.summary,query_pairs=100,
    average_pair_ms=sum(timings)*1000/len(timings),maximum_pair_ms=max(timings)*1000,
    limitation='Own source geometry and static metadata queries; no native scene collision, dynamic doors or visual acceptance')
output=ROOT/'private/typed-gameplay/collision-scene-validation.json'
output.write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
