"""Conservative Thai scene bounds/height screening, not mesh collision."""
import math
from pathlib import Path


class StaticVisibility:
    CELL=10000

    def __init__(self,terrain,bounds):
        self.terrain=terrain
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
    def from_scene(cls,terrain,path):
        from offline_client_map import read_scene
        root=read_scene(Path(path),'RigidStaticInPxScene')
        bounds=[]
        for row in root.iter('mItems'):
            if not row.get('mID'):continue
            bounds.append(tuple(float(row.get(k)) for k in ('mBoundingX','mBoundingY','mBoundingZ','mBoundingRadius')))
        if not bounds:raise ValueError('Static scene has no occlusion bounds')
        return cls(terrain,bounds)

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
        if (len(start)!=3 or len(end)!=3 or not 0<=padding<=100
                or any(not math.isfinite(v) or abs(v)>=2000000 for v in (*start,*end))
                or math.dist(start,end)>100000):return False
        if any(self.distance_to_segment((x,y,z),start,end)<=radius+padding
               for x,y,z,radius in self.candidates(start,end,padding)):return False
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
