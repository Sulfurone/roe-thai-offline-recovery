"""Own Thai door rotations and source primitives, without live scene physics."""
import json
import argparse
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from offline_collision_assets import CollisionAssets
from offline_collision import rotate,euler_xyz
from offline_dynamic_doors import DynamicDoors,read_doors
from offline_visibility import StaticVisibility
from offline_client_map import ClientHeightfield

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--full-scene',action='store_true')
args=parser.parse_args()
doors=read_doors(ROOT/'private/client-map/World_EU_KillZone_2048_RemainingFiles/ENTITYSTATUSINPXSCENE.XML')
if args.full_scene:
    folder=ROOT/'private/client-map/World_EU_KillZone_2048_RemainingFiles'
    scene=StaticVisibility.from_scene(ClientHeightfield.from_folder(folder),folder/'RIGIDSTATICINPXSCENE.XML',ROOT.parent/'32838/SFC')
    assets=scene.assets;summary=assets.summary;geometry=scene.doors
    blocked=lambda a,b:not scene.clear(a,b)
else:
    assets=CollisionAssets(ROOT.parent/'32838/SFC')
    summary=assets.prepare(d.instance.path for d in doors)
    geometry=DynamicDoors(doors,assets)
    blocked=geometry.blocks
geometry.states={}
if len(geometry.items)!=2374 or geometry.fallback:raise ValueError('Original door resource coverage differs')
controls=[];unresolved=[]
for path in sorted({d.instance.path for d in doors}):
    door=next(d for d in doors if d.instance.path==path)
    model=assets.get(path)
    def world(p):
        return tuple(a+b for a,b in zip(door.instance.position,rotate(euler_xyz(door.instance.angles),tuple(v*door.instance.scale for v in p))))
    found=None
    for shape in model.shapes:
        centre=tuple((a+b)/2 for a,b in zip(shape.lower,shape.upper))
        axis=min(range(2),key=lambda i:shape.upper[i]-shape.lower[i])
        a=list(centre);b=list(centre);a[axis]-=50;b[axis]+=50
        a,b=world(a),world(b)
        geometry.states[door.entity]=0
        closed=blocked(a,b)
        geometry.states[door.entity]=1
        opened=blocked(a,b)
        geometry.states[door.entity]=0
        reclosed=blocked(a,b)
        if closed and not opened and reclosed:
            found=dict(entity=door.entity,model=path,closed=True,opened=False,reclosed=True,start=a,end=b);break
    if found is None:
        details=[]
        if args.full_scene:
            # Retain a failed complete-scene control, rather than relaxing
            # collision to make the isolated-door assertion pass.
            for bound in scene.candidates(a,b):
                if scene.distance_to_segment(bound[:3],a,b)>bound[3]:continue
                for item in scene.instances.get(bound,()):
                    if item is None:details.append(dict(fallback=True));continue
                    resource=assets.get(item.path)
                    local=item.local_ray(a,b)
                    if resource is None or resource.blocks(*local):details.append(dict(path=item.path,position=item.position,fallback=resource is None))
        unresolved.append(dict(entity=door.entity,model=path,last_start=a,last_end=b,static_blockers=details))
    else:controls.append(found)
report=dict(passed=not unresolved,full_scene=args.full_scene,catalogue_doors=len(doors),prepared=summary,controls=controls,unresolved=unresolved,
    limitation='Own model/metadata ray controls; door animation pivot, destructive parts and native scene physics remain unverified')
(ROOT/'private/typed-gameplay'/('dynamic-door-full-scene-validation.json' if args.full_scene else 'dynamic-door-validation.json')).write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
if unresolved:raise SystemExit(1)
