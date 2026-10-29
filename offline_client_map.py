"""Own-client Thai QSHM height, road mask and residential entrance placement.

Resources are loaded privately. No terrain, textures or scene tables ship
with this module. Collision sampling supplies covered upper-floor candidates when available.
Entrance-side fallback remains a first-floor approximation; neither is a
recovery of original authored loot nodes or complete building navigation.
"""
import math
from pathlib import Path
import re
import struct
import time
import xml.etree.ElementTree as ET

HEIGHT_SCALE = 120000 / 65535
HOUSE_MODEL = re.compile(r'(?:MJ_[123]FLOOR_\d+(?:_\d+)?[A-Z]?|(?:DK|MJ|FM|RM)_BUILDING_\d+[A-Z]?)_COLLISION.XML', re.I)


class ClientHeightfield:
    def __init__(self, tiles, side=8):
        self.tiles, self.side = tiles, side
        self.width = side * 51200

    @classmethod
    def from_folder(cls, folder):
        tiles = {}
        for x in range(8):
            for y in range(8):
                path = Path(folder)/f'TERRAINHEIGHTTILE_{x}_{y}.QSHM'
                raw = path.read_bytes()
                if len(raw) != 132110 or struct.unpack_from('<III', raw) != (0xff000001, 257, 257):
                    raise ValueError('Unknown Thai QSHM tile format')
                tiles[x, y] = raw
        return cls(tiles)

    def height_at(self, x, y):
        if not all(math.isfinite(v) and 0 <= v <= self.width for v in (x, y)):
            return None
        column, row = x/200, y/200
        tx, ty = min(int(column)//256, self.side-1), min(int(row)//256, self.side-1)
        u, v = column-tx*256, row-ty*256
        c, r = min(int(u), 255), min(int(v), 255)
        u, v = u-c, v-r
        raw = self.tiles[tx, ty]
        def sample(dr, dc):
            return struct.unpack_from('<H', raw, 12+2*((r+dr)*257+c+dc))[0]
        return ((1-u)*(1-v)*sample(0,0)+u*(1-v)*sample(0,1)+
                (1-u)*v*sample(1,0)+u*v*sample(1,1))*HEIGHT_SCALE


def read_scene(path, suffix):
    path = Path(path)
    if not 0 < path.stat().st_size <= 64*1024*1024:
        raise ValueError('Scene catalogue exceeds verified bounds')
    text = path.read_text(encoding='utf-8-sig').replace(' [XlsProp]=', ' _xls=')
    root = ET.fromstring(text)
    if not root.get('ObjName', '').lower().endswith('eu_killzone_2048.clienttable.'+suffix.lower()):
        raise ValueError('Scene catalogue is not the Thai target map')
    return root


class ThaiClientMap:
    def __init__(self, heightfield, road, houses, doors):
        self.heightfield, self.road = heightfield, road
        self.houses, self.doors = houses, doors
        self.width = heightfield.width
        self.road_cache = {}
        self.road_jobs = {}
        self.road_failures = {}
        self.road_executor = None
        self.indoor_floors = None
        self.house_grid = {}
        for house in houses:
            self.house_grid.setdefault((int(house[0])//10000,int(house[1])//10000),[]).append(house)

    def near_houses(self, x, y):
        gx,gy = int(x)//10000,int(y)//10000
        return [house for dx in (-1,0,1) for dy in (-1,0,1)
                for house in self.house_grid.get((gx+dx,gy+dy),())]

    @classmethod
    def from_folder(cls, folder):
        folder = Path(folder)
        heightfield = ClientHeightfield.from_folder(folder)
        road = (folder/'ROADMASK.DDS').read_bytes()
        if (len(road) != 128+2048*2048*4 or road[:4] != b'DDS ' or
                struct.unpack_from('<II', road, 12) != (2048,2048) or
                struct.unpack_from('<4I', road, 92) != (0xff0000,0xff00,0xff,0xff000000)):
            raise ValueError('Need verified 2048 BGRA Thai road mask')
        static = read_scene(folder/'RIGIDSTATICINPXSCENE.XML', 'RigidStaticInPxScene')
        houses = []
        for row in static.iter('mItems'):
            if not row.get('mID') or not HOUSE_MODEL.fullmatch(row.get('mModelName','')):
                continue
            values = tuple(float(row.get(k)) for k in ('mBoundingX','mBoundingY','mBoundingRadius','mPosZ'))
            if all(math.isfinite(v) for v in values) and 400 <= values[2] <= 5000:
                houses.append(values)
        instance = cls(heightfield,road[128:],houses,[])
        scene = read_scene(folder/'ENTITYSTATUSINPXSCENE.XML', 'EntityStatusInPxScene')
        doors = []
        for row in scene.iter('mTable'):
            switch = row.find('mSwitcherStatus')
            if switch is None or switch.get('mType') != 'EStatus_REVERSIBLE' or switch.get('mSwitcherType') != 'ESwitcher_DOOR':
                continue
            x,y,z = (float(row.get(k)) for k in ('mPosX','mPosY','mPosZ'))
            nearby = [house for house in instance.near_houses(x,y) if math.hypot(x-house[0],y-house[1]) <= house[2]+100
                      and abs(z-house[3]) <= 400]
            if not nearby:
                continue
            house = min(nearby, key=lambda h: math.hypot(x-h[0],y-h[1]))
            dx,dy = house[0]-x, house[1]-y
            length = math.hypot(dx,dy)
            if length < 100 or not 6500 <= z <= 60000:
                continue
            doors.append((x,y,z,dx/length,dy/length,max(120,min(450,length*1.2))))
        if not houses or not doors:
            raise ValueError('No residential first-floor entrance candidates')
        instance.doors = doors
        return instance

    def height_at(self, x, y):
        return self.heightfield.height_at(x,y)

    def is_road(self, x, y):
        if not 0 <= x < 409600 or not 0 <= y < 409600:
            return False
        return self.road[(int(y)//200*2048+int(x)//200)*4+3] >= 128

    def clear_ground(self, x, y):
        heights = [self.height_at(x+dx,y+dy) for dx,dy in ((0,0),(200,0),(-200,0),(0,200),(0,-200))]
        if any(v is None or not math.isfinite(v) or v < 6500 for v in heights):
            return None
        return heights[0] if max(heights)-min(heights) <= 160 else None

    def roadside(self, position):
        key = int(position[0])//20000, int(position[1])//20000
        if key in self.road_cache:
            return self.road_cache[key]
        if self.road_executor is not None:
            # Retire finished work even when the player has left its region.
            # Only this thread publishes caches; workers read immutable map data.
            for pending, job in list(self.road_jobs.items()):
                if job.done():
                    try:self._cache_road(pending,job.result())
                    except Exception as error:
                        self.road_failures[pending]=type(error).__name__
                        if len(self.road_failures)>32:self.road_failures.pop(next(iter(self.road_failures)))
                    del self.road_jobs[pending]
            if key in self.road_cache:return self.road_cache[key]
            if key not in self.road_jobs and key not in self.road_failures and len(self.road_jobs)<4:
                self.road_jobs[key]=self.road_executor.submit(self._roadside_candidates,key)
            return []
        return self._cache_road(key,self._roadside_candidates(key))

    def enable_background_roads(self):
        if self.road_executor is None:
            from concurrent.futures import ThreadPoolExecutor
            self.road_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='road-placement')

    def close(self):
        if self.road_executor is not None:self.road_executor.shutdown(wait=False,cancel_futures=True)

    def _cache_road(self,key,result):
        if len(self.road_cache)>=32:self.road_cache.pop(next(iter(self.road_cache)))
        self.road_cache[key]=result
        return result

    def _roadside_candidates(self,key):
        cx,cy = key[0]*20000+10000,key[1]*20000+10000
        candidates = set()
        for row in range(max(4,(cy-45000)//200),min(2044,(cy+45000)//200),2):
            if self.road_executor is not None and row%16==0:time.sleep(0)
            for col in range(max(4,(cx-45000)//200),min(2044,(cx+45000)//200),2):
                x,y = col*200+100,row*200+100
                if not self.is_road(x,y):
                    continue
                for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    for step in range(1,9):
                        if not self.is_road(x+dx*step*200,y+dy*step*200):
                            px,py = x+dx*(step+1)*200,y+dy*(step+1)*200
                            if self.is_road(px,py):
                                break
                            height = self.clear_ground(px,py)
                            if height is not None and not any(math.hypot(px-h[0],py-h[1]) < h[2]+200 for h in self.near_houses(px,py)):
                                candidates.add((px,py,round(height)+100))
                            break
        return sorted(candidates)

    def spawn_spot(self, position, rng, kind, occupied):
        x,y,_ = position
        if kind == 'loot':
            if self.indoor_floors is not None:
                floors=self.indoor_floors.nearby(position,self.houses)
                rng.shuffle(floors)
                for spot in floors:
                    if all(math.hypot(spot[0]-a,spot[1]-b)>=150 for a,b in occupied):
                        return spot
            choices = sorted(self.doors,key=lambda p:math.hypot(p[0]-x,p[1]-y))[:32]
            rng.shuffle(choices)
            for door in choices:
                px,py,z,dx,dy=door[:5]
                if math.hypot(px-x,py-y) > 35000:
                    continue
                inward = rng.uniform(90,door[5] if len(door)>5 else 220)
                side = rng.uniform(-60,60)
                spot = (round(px+dx*inward-dy*side),round(py+dy*inward+dx*side),round(z)+10)
                if all(math.hypot(spot[0]-a,spot[1]-b) >= 120 for a,b in occupied):
                    return spot
            return None
        if kind == 'peer':
            # The verified ground-entry point sits beside low coastal terrain:
            # its original 8..25 m search has no dry candidates. Widen only
            # after nearer searches fail, retaining the same ground checks.
            for low,high in ((800,2500),(2500,6000),(6000,9000),(9000,12000)):
                for _ in range(64):
                    angle,distance = rng.uniform(0,math.tau),rng.uniform(low,high)
                    px,py = round(x+distance*math.cos(angle)),round(y+distance*math.sin(angle))
                    height = self.peer_walkable(px,py)
                    if height is not None and all(math.hypot(px-a,py-b) >= 300 for a,b in occupied):
                        return px,py,round(height)+5
            return None
        candidates = [p for p in self.roadside(position) if
                      (600 if kind == 'peer' else 2000) <= math.hypot(p[0]-x,p[1]-y) <= 35000
                      and all(math.hypot(p[0]-a,p[1]-b) >= 600 for a,b in occupied)]
        candidates.sort(key=lambda p:math.hypot(p[0]-x,p[1]-y))
        if not candidates:
            return None
        spot = rng.choice(candidates[:12 if kind == 'peer' else 48])
        return (spot[0],spot[1],spot[2]-95) if kind == 'peer' else spot

    def peer_walkable(self, x, y):
        if any(math.hypot(x-h[0],y-h[1]) < h[2]+100 for h in self.near_houses(x,y)):
            return None
        return self.clear_ground(x,y)
