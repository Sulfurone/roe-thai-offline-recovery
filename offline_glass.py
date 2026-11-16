"""Thai single-pane scene destruction and hit-state broadcast."""
import math
from pathlib import Path
import struct

from offline_client_map import read_scene


def read_glass(path):
    root=read_scene(Path(path),'EntityStatusInPxScene')
    glass={}
    for row in root.iter('mTable'):
        name=row.get('mEntityFullName','').rsplit('.',1)[-1].lower()
        destruct=row.find('mDestructStatus')
        if 'glass' not in name or destruct is None or destruct.get('mType')!='EStatus_IRREVERSIBLE':
            continue
        parts=destruct.findall('mPartStatus/mPartStatus')
        if len(parts)!=1 or parts[0].get('mDamageThreshold')!='1' or parts[0].get('mPartStatus')!='1':
            continue
        position=tuple(float(row.get('mPos'+axis)) for axis in 'XYZ')
        if all(math.isfinite(value) for value in position):
            glass[int(row.get('mID'))]=position
    return glass


class GlassState:
    def __init__(self,panes):
        self.panes=panes
        self.broken=set()

    def handle(self,body,actor_uid):
        if len(body) not in (88,96):
            return []
        entity,parts,damage,size=struct.unpack_from('>4I',body)
        position=self.panes.get(entity)
        if (position is None or entity in self.broken or parts!=1 or not 0<damage<=1000000 or size!=72):
            return []
        context=body[16:88]
        actor,part,x,y,z=struct.unpack_from('<QI3f',context)
        if actor!=actor_uid or part!=0 or not all(math.isfinite(value) for value in (x,y,z)):
            return []
        if math.dist(position,(x,y,z))>650:
            return []
        self.broken.add(entity)
        return [(0x6f56,struct.pack('>6I',1,entity,0,1,0,size)+context)]
