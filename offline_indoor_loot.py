"""Find covered, standing-height loot surfaces in owner-supplied buildings.

This samples collision solids, not recovered original loot nodes. A roof
without a ceiling is excluded; no fixed floor-height offset is invented.
"""
import math
import time
from offline_collision import euler_xyz,rotate,dot,sub,bounds_entry


def vertical_interval(instance,shape,x,y,bottom,top):
    if not shape.planes or {'physxThrough','mWalkThrough'} & shape.flags:return None
    start,end=instance.local_ray((x,y,top),(x,y,bottom))
    if bounds_entry(start,end,shape.lower,shape.upper) is None:return None
    direction=sub(end,start)
    enter,leave=0.,1.;normal=None
    for n,d in shape.planes:
        gap=d-dot(n,start);speed=dot(n,direction)
        if abs(speed)<1e-10:
            if gap < -1e-7:return None
        elif speed<0:
            value=gap/speed
            if value>enter:enter=value;normal=n
        else:leave=min(leave,gap/speed)
        if enter>leave+1e-9:return None
    if normal is None or not 0<=enter<=leave<=1:return None
    world_normal=rotate(euler_xyz(instance.angles),normal)
    return top+(bottom-top)*leave,top+(bottom-top)*enter,world_normal[2]


class IndoorFloors:
    def __init__(self,visibility,background=False):
        self.visibility=visibility
        self.cache={}
        self.jobs={}
        self.failures={}
        self.executor=None
        self.cooperative=background
        if background:
            from concurrent.futures import ThreadPoolExecutor
            self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='indoor-floors')

    def close(self):
        if self.executor is not None:self.executor.shutdown(wait=False,cancel_futures=True)

    def candidates(self,house):
        if house in self.cache:return self.cache[house]
        x,y,radius,base=house
        visibility=self.visibility
        solids=[]
        for bound in visibility.candidates((x-radius,y-radius,base),(x+radius,y+radius,base+1800)):
            if math.hypot(bound[0]-x,bound[1]-y)>radius+bound[3]:continue
            for instance in visibility.instances.get(bound,()):
                if instance is None:continue
                model=visibility.assets.get(instance.path)
                if model is not None:solids.extend((instance,s) for s in model.shapes)
        def intervals(px,py):
            hits=[]
            for index,(instance,shape) in enumerate(solids):
                if self.cooperative and index%128==127:time.sleep(0)
                hit=vertical_interval(instance,shape,px,py,base-300,base+2200)
                if hit is not None:hits.append(hit)
            return hits
        result=[]
        # 9x9 world-space samples. Covers rotated buildings via their world
        # bounds; ceiling and footprint tests reject the surrounding yard.
        for ix in range(-4,5):
            for iy in range(-4,5):
                px,py=x+ix*radius/5,y+iy*radius/5
                hits=intervals(px,py)
                for _,floor,nz in hits:
                    if nz<.85 or not base-150<=floor<=base+1600:continue
                    if any(lo<floor+190 and hi>floor+3 for lo,hi,_ in hits):continue
                    if not any(floor+190<=lo<=floor+650 for lo,_,_ in hits):continue
                    # A small item cluster must fit on a continuous surface,
                    # with headroom on each side, away from stairs/wall edges.
                    good=True
                    for dx,dy in ((65,0),(-65,0),(0,65),(0,-65)):
                        nearby=intervals(px+dx,py+dy)
                        if (not any(abs(hi-floor)<=12 and n>=.85 for _,hi,n in nearby)
                                or any(lo<floor+190 and hi>floor+15 for lo,hi,_ in nearby)):
                            good=False;break
                    if good:result.append((round(px),round(py),round(floor)+10))
        result=tuple(dict.fromkeys(result))
        if len(self.cache)>=128:self.cache.pop(next(iter(self.cache)))
        self.cache[house]=result
        return result

    def ready_buildings(self,position,houses):
        ordered=sorted(houses,key=lambda h:math.hypot(h[0]-position[0],h[1]-position[1]))
        # Retire finished jobs, including houses the player has passed, so
        # exploration cannot permanently fill the bounded queue.
        for house,job in list(self.jobs.items()):
            if math.hypot(house[0]-position[0],house[1]-position[1])>35000 and job.cancel():
                del self.jobs[house]
                continue
            if job.done():
                try:job.result()
                except Exception as error:
                    self.failures[house]=type(error).__name__
                    if len(self.failures)>128:self.failures.pop(next(iter(self.failures)))
                del self.jobs[house]
        ready=[]
        for house in ordered[:12]:
            if math.hypot(house[0]-position[0],house[1]-position[1])>35000:continue
            points=self.cache.get(house)
            if points is None:
                if self.executor is None:points=self.candidates(house)
                elif house not in self.jobs and house not in self.failures and len(self.jobs)<24:
                    self.jobs[house]=self.executor.submit(self.candidates,house)
            if points:ready.append((house,points))
        return ready

    def nearby(self,position,houses):
        return [p for _,points in self.ready_buildings(position,houses) for p in points]
