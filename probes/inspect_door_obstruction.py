"""Resolve retained whole-scene door failures to individual owned primitives.

Read-only offline diagnosis. Does not erase/skip geometry or alter the client.
"""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from offline_collision import Instance
from offline_collision_assets import CollisionAssets,sfc_path_key
from offline_client_map import read_scene

failed=json.loads((ROOT/'private/typed-gameplay/dynamic-door-full-scene-validation.json').read_text(encoding='utf8'))
scene=read_scene(ROOT/'private/client-map/World_EU_KillZone_2048_RemainingFiles/RIGIDSTATICINPXSCENE.XML','RigidStaticInPxScene')
rows=[r for r in scene.iter('mItems') if r.get('mID')]
assets=CollisionAssets(ROOT.parent/'32838/SFC');reports=[]
for case in failed['unresolved']:
    blockers=[]
    for candidate in case['static_blockers']:
        path=candidate.get('path')
        if not path:continue
        row=next(r for r in rows if r.get('mModelFullPath','').casefold()==path.casefold()
            and tuple(float(r.get('mPos'+k)) for k in 'XYZ')==tuple(candidate['position']))
        instance=Instance(path,tuple(float(row.get('mPos'+k)) for k in 'XYZ'),
            tuple(float(row.get('mRotate'+k)) for k in 'XYZ'),float(row.get('mScale')))
        model=assets.get(path)
        if model is None:continue
        local=instance.local_ray(case['last_start'],case['last_end'])
        hit=[i for i,s in enumerate(model.shapes) if s.blocks(*local)]
        resource=assets.indexed_model(sfc_path_key(path))
        index=0
        for actor in resource.findall('./PhysCollectionDesc/mActors/mActors'):
            for kind in ('mBoxes','mConvexes','mSpheres','mCapsules'):
                for shape in actor.findall(kind+'/'+kind):
                    if index in hit:
                        param=shape.find('mParam')
                        blockers.append(dict(scene_id=row.get('mID'),model=path,shape_index=index,
                            kind=kind,name=param.get('mName'),material=param.get('mMaterial'),
                            actor=actor.get('mName'),local_ray=local,
                            bounds=[model.shapes[index].lower,model.shapes[index].upper]))
                    index+=1
    reports.append(dict(door=case['entity'],blockers=blockers))
report=dict(reports=reports,limitation='Own source primitive/ray diagnosis; no native scene oracle or proof that this is an original map defect')
(ROOT/'private/typed-gameplay/door-obstruction-detail.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
