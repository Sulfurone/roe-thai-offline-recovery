"""Thai static source primitives where matched, bounds fallback elsewhere."""
import math
from pathlib import Path


class StaticVisibility:
    CELL=10000

    def __init__(self,terrain,bounds,instances=None,assets=None):
        self.terrain=terrain
        self.instances=instances or {}
        self.assets=assets
        self.bounds=tuple(dict.fromkeys(tuple(row) for row in bounds))
        self.grid={}
        if len(self.bounds)>100000:raise ValueError('Too many static bounds')
        for index,(x,y,z,radius) in enumerate(self.bounds):
            if (not all(math.isfinite(v) and abs(v)<2000000 for v in (x,y,z,radius))
                    or not 0<radius<100000):
                raise ValueError('Invalid static collision bound')
            for gx in range(math.floor((x-radius)/self.CELL),math.floor((x+radius)/self.CELL)+1):
                for gy in range(math.floor((y-radius)/self.CELL),math.floor((y+radius)/self.CELL)+1):
                    self.grid.setdefault((gx,gy),[]).append(index)

    @classmethod
    def from_scene(cls,terrain,path,archives=None):
        from offline_client_map import read_scene
        from offline_collision import Instance
        from offline_collision_assets import CollisionAssets
        root=read_scene(Path(path),'RigidStaticInPxScene')
        bounds=[];instances={}
        for row in root.iter('mItems'):
            if not row.get('mID'):continue
            bound=tuple(float(row.get(k)) for k in ('mBoundingX','mBoundingY','mBoundingZ','mBoundingRadius'))
            bounds.append(bound)
            if archives is not None:
                try:
                    instance=Instance(row.get('mModelFullPath',''),
                        tuple(float(row.get('mPos'+axis)) for axis in 'XYZ'),
                        tuple(float(row.get('mRotate'+axis)) for axis in 'XYZ'),float(row.get('mScale')))
                except (ValueError,TypeError):instance=None
                entries=instances.setdefault(bound,[])
                if instance not in entries:entries.append(instance)
        if not bounds:raise ValueError('Static scene has no occlusion bounds')
        assets=CollisionAssets(archives) if archives is not None else None
        if assets is not None:
            assets.prepare(i.path for rows in instances.values() for i in rows if i is not None)
        return cls(terrain,bounds,instances,assets)

    def candidates(self,start,end,padding=0):
        result=set()
        for gx in range(math.floor((min(start[0],end[0])-padding)/self.CELL),
                        math.floor((max(start[0],end[0])+padding)/self.CELL)+1):
            for gy in range(math.floor((min(start[1],end[1])-padding)/self.CELL),
                            math.floor((max(start[1],end[1])+padding)/self.CELL)+1):
                result.update(self.grid.get((gx,gy),()))
        return (self.bounds[i] for i in result)

    @staticmethod
    def distance_to_segment(point,start,end):
        delta=tuple(b-a for a,b in zip(start,end))
        length=sum(v*v for v in delta)
        t=max(0,min(1,sum((p-a)*d for p,a,d in zip(point,start,delta))/length)) if length else 0
        return math.dist(point,tuple(a+t*d for a,d in zip(start,delta)))

    def clear(self,start,end,padding=0):
        return self._clear(start,end,padding,'solid')

    def sight_clear(self,start,end):
        return self._clear(start,end,0,'sight')

    def _clear(self,start,end,padding,mode):
        if (len(start)!=3 or len(end)!=3 or not 0<=padding<=100
                or any(not math.isfinite(v) or abs(v)>=2000000 for v in (*start,*end))
                or math.dist(start,end)>100000):return False
        for bound in self.candidates(start,end,padding):
            x,y,z,radius=bound
            if self.distance_to_segment((x,y,z),start,end)>radius+padding:continue
            if self.assets is None:return False
            entries=self.instances.get(bound)
            if not entries:return False
            for instance in entries:
                if instance is None:return False
                model=self.assets.get(instance.path)
                if model is None:return False
                a,b=instance.local_ray(start,end)
                if model.blocks(a,b,padding/instance.scale,mode):return False
        steps=max(1,math.ceil(math.dist(start,end)/100))
        for i in range(steps+1):
            point=tuple(a+(b-a)*i/steps for a,b in zip(start,end))
            height=self.terrain.height_at(*point[:2])
            if height is None or not math.isfinite(height) or point[2]<=height+5:return False
        return True

    def walk(self,start,end):
        if (len(start)!=3 or len(end)!=3 or any(not math.isfinite(v) or abs(v)>=2000000 for v in (*start,*end))
                or math.dist(start,end)>2500):return None
        distance=math.dist(start[:2],end[:2])
        steps=max(1,math.ceil(distance/50))
        previous=start[2]
        for i in range(steps+1):
            x,y=(a+(b-a)*i/steps for a,b in zip(start[:2],end[:2]))
            height=self.terrain.height_at(x,y)
            if height is None or not math.isfinite(height) or height<6500 or abs(height+5-previous)>50:return None
            a,b=(x,y,height+40),(x,y,height+140)
            if not self.clear(a,b,35):return None
            previous=height+5
        return round(end[0]),round(end[1]),round(previous)
