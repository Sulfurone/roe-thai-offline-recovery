"""State-aware local door primitives from the owned Thai entity catalogue.

Only exact building-model resource keys are accepted after a bounded name
mapping. This is a local collision candidate, not original animation/physics.
"""
from dataclasses import dataclass
import math
from pathlib import Path
import re

from offline_client_map import read_scene
from offline_collision import Instance


@dataclass(frozen=True)
class Door:
    entity:int
    instance:Instance
    rotations:tuple
    initial:int


def read_doors(path):
    root=read_scene(Path(path),'EntityStatusInPxScene')
    result=[];seen=set()
    for row in root.iter('mTable'):
        switch=row.find('mSwitcherStatus')
        if switch is None or switch.get('mType')!='EStatus_REVERSIBLE' or switch.get('mSwitcherType')!='ESwitcher_DOOR':continue
        name=row.get('mEntityFullName','').rsplit('.',1)[-1]
        match=re.fullmatch(r'([a-z0-9_]*door[a-z0-9_]*)_mesh[0-9a-f]+',name,re.I)
        if not match:continue  # Glass/destructible objects need their own state mapping.
        model='Data/Scene/general/building/'+match[1]+'_collision.xml'
        values=switch.find('mDoorRelativeZRotation')
        if values is None:continue
        rotations=tuple(float(c.get('v')) for c in values.findall('mDoorRelativeZRotation'))
        if (values.get('ArrayCount')!='3' or len(rotations)!=3
                or any(not math.isfinite(v) or abs(v)>math.tau for v in rotations)):continue
        entity=int(row.get('mID'));initial=int(switch.get('mStatus'))
        if not 0<entity<2**24 or initial not in (0,1,2) or entity in seen:raise ValueError('Door catalogue identity differs')
        seen.add(entity)
        instance=Instance(model,tuple(float(row.get('mPos'+a)) for a in 'XYZ'),
                          tuple(float(row.get('mRotate'+a)) for a in 'XYZ'),float(row.get('mScale')))
        result.append(Door(entity,instance,rotations,initial))
        if len(result)>4096:raise ValueError('Door catalogue exceeds bound')
    return result


class DynamicDoors:
    CELL=1000

    def __init__(self,doors,assets):
        self.assets=assets;self.states=None;self.items=[];self.grid={};self.fallback=0
        for door in doors:
            model=assets.get(door.instance.path)
            if model is None:self.fallback+=1;continue
            radius=door.instance.scale*math.sqrt(sum(max(abs(a),abs(b))**2 for a,b in zip(model.root.lower,model.root.upper)))
            if not 0<radius<5000:self.fallback+=1;continue
            index=len(self.items);self.items.append((door,model))
            x,y,_=door.instance.position
            for gx in range(math.floor((x-radius)/self.CELL),math.floor((x+radius)/self.CELL)+1):
                for gy in range(math.floor((y-radius)/self.CELL),math.floor((y+radius)/self.CELL)+1):
                    self.grid.setdefault((gx,gy),set()).add(index)

    def blocks(self,start,end,padding=0,mode='solid'):
        candidates=set()
        for gx in range(math.floor((min(start[0],end[0])-padding)/self.CELL),math.floor((max(start[0],end[0])+padding)/self.CELL)+1):
            for gy in range(math.floor((min(start[1],end[1])-padding)/self.CELL),math.floor((max(start[1],end[1])+padding)/self.CELL)+1):
                candidates.update(self.grid.get((gx,gy),()))
        for index in candidates:
            door,model=self.items[index]
            state=self.states.get(door.entity,door.initial) if self.states is not None else door.initial
            if state not in (0,1,2):state=door.initial
            angles=(*door.instance.angles[:2],door.instance.angles[2]+door.rotations[state])
            instance=Instance(door.instance.path,door.instance.position,angles,door.instance.scale)
            a,b=instance.local_ray(start,end)
            if model.blocks(a,b,padding/instance.scale,mode):return True
        return False
