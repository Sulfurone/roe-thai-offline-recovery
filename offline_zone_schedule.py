"""Opt-in local circle pacing; not recovered Thai match rules or outcomes.

Only original 047B state snapshots are sent. No guessed damage, victory,
helicopter, warning-phase semantics or client clock changes are introduced.
"""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import time
from offline_zones import Circle,zone_state,interpolated_circle


@dataclass(frozen=True)
class ZoneStage:
    target:Circle
    wait:int
    shrink:int


@dataclass(frozen=True)
class ZonePlan:
    initial:Circle
    stages:tuple

    def __post_init__(self):
        if (type(self.initial) is not Circle or self.initial.radius<=0
                or type(self.stages) is not tuple or not 1<=len(self.stages)<=20):
            raise ValueError('Local circle plan requires 1..20 stages')
        previous=self.initial;seconds=0
        for stage in self.stages:
            if (type(stage) is not ZoneStage or type(stage.target) is not Circle
                    or any(type(v) is not int or not 1<=v<=3600 for v in (stage.wait,stage.shrink))):
                raise ValueError('Local circle wait/shrink times must be 1..3600 seconds')
            if (stage.target.radius>=previous.radius or
                    math.hypot(stage.target.x-previous.x,stage.target.y-previous.y)+stage.target.radius>previous.radius+.001):
                raise ValueError('A local target circle must shrink inside its predecessor')
            seconds+=stage.wait+stage.shrink;previous=stage.target
        if seconds>43200:raise ValueError('Local circle plan exceeds a twelve-hour session')

    def randomize(self, rng, terrain):
        """Keep stage radii/times and sample nested centers on dry Thai land."""
        last_land_stage = len(self.stages)-1-(self.stages[-1].target.radius==0)
        final_radius = (self.stages[last_land_stage].target if last_land_stage>=0 else self.initial).radius

        def dry(x, y):
            height = terrain.height_at(x,y)
            return height is not None and math.isfinite(height) and height>=6500-1e-6

        for _ in range(64):
            previous = self.initial
            stages = []
            for index,stage in enumerate(self.stages):
                radius = stage.target.radius
                if radius==0:
                    stages.append(ZoneStage(Circle(previous.x,previous.y,0),stage.wait,stage.shrink))
                    continue
                limit = max(0,previous.radius-radius-1)
                for _ in range(32):
                    angle = rng.uniform(0,math.tau)
                    distance = limit*math.sqrt(rng.random())
                    x = round(previous.x+distance*math.cos(angle))
                    y = round(previous.y+distance*math.sin(angle))
                    if not (final_radius<=x<=409600-final_radius and final_radius<=y<=409600-final_radius
                            and dry(x,y)):
                        continue
                    if index==last_land_stage and not all(
                            dry(x+radius*math.cos(i*math.tau/8),y+radius*math.sin(i*math.tau/8)) for i in range(8)):
                        continue
                    previous = Circle(x,y,radius)
                    stages.append(ZoneStage(previous,stage.wait,stage.shrink))
                    break
                else:
                    break
            if len(stages)==len(self.stages):
                return ZonePlan(self.initial,tuple(stages))
        raise ValueError('Could not find nested Thai safe zones with a dry final circle')

    @classmethod
    def read(cls,path):
        path=Path(path)
        if not 0<path.stat().st_size<=16384:raise ValueError('Local circle plan exceeds 16 KiB')
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        def circle(row):
            if type(row) is not dict or set(row)!={'x','y','radius'}:raise ValueError('Unknown circle schema')
            return Circle(**row)
        if (type(data) is not dict or set(data)!={'version','initial','stages'}
                or type(data['version']) is not int or data['version']!=1
                or type(data['stages']) is not list or not 1<=len(data['stages'])<=20):
            raise ValueError('Unknown local circle plan schema')
        stages=[]
        for row in data['stages']:
            if type(row) is not dict or set(row)!={'target','wait','shrink'}:
                raise ValueError('Unknown local circle stage schema')
            stages.append(ZoneStage(circle(row['target']),row['wait'],row['shrink']))
        return cls(circle(data['initial']),tuple(stages))


class ZoneSchedule:
    ARM_DELAY=3.
    PERIOD=1.

    def __init__(self,game,terrain,plan):
        if game is None or not callable(getattr(terrain,'height_at',None)) or type(plan) is not ZonePlan:
            raise ValueError('Local circle pacing requires gameplay, terrain and a validated plan')
        self.game,self.terrain,self.plan=game,terrain,plan
        self.ready_since=self.started=None
        self.next_send=0.
        self.finished=False
        self.last_event=None

    def ready(self,now):
        game=self.game
        if (not game.actor_ready or game.seated or not game.vitals.current
                or game.deployment_phase not in ('ground','landed')
                or game.require_self_position_for_drop and not game.has_fresh_self_position(now)):
            return False
        x,y,z=game.player_position
        ground=self.terrain.height_at(x,y)
        # Terrain interpolation can return 6499.999999999999 for an exact
        # 6500 cm sample. Allow only numerical noise at the dry-land cutoff.
        return ground is not None and math.isfinite(ground) and ground>=6500-1e-6 and -100<=z-ground<=250

    def stage_at(self,now):
        elapsed=max(0,now-self.started);current=self.plan.initial
        for index,stage in enumerate(self.plan.stages):
            if elapsed<stage.wait:return index,current,stage.target,0,elapsed,stage.wait
            if elapsed<stage.wait+stage.shrink:return index,current,stage.target,2,elapsed-stage.wait,stage.shrink
            elapsed-=stage.wait+stage.shrink;current=stage.target
        return len(self.plan.stages),current,current,0,0,1

    def circle_at(self,now):
        """Current local boundary, including after the final snapshot."""
        if self.started is None:return None
        _,current,target,phase,elapsed,total=self.stage_at(now)
        if phase==2:return interpolated_circle(elapsed,total,current,target)
        return current.x,current.y,current.radius

    def countdown(self,now):
        if self.started is None:return None
        index,_,_,phase,elapsed,total=self.stage_at(now)
        if index==len(self.plan.stages):return None
        return phase,math.ceil(total-elapsed)

    def migration_target(self,now):
        if self.started is None:return None
        _,current,target,phase,elapsed,total=self.stage_at(now)
        return target if phase==2 or total-elapsed<=60 else current

    def tick(self,now=None):
        now=time.monotonic() if now is None else now
        self.last_event=None
        if self.finished:return []
        if self.started is None:
            if not self.ready(now):
                self.ready_since=None
                return []
            if self.ready_since is None:self.ready_since=now
            if now-self.ready_since<self.ARM_DELAY:return []
            self.started=now
        if now<self.next_send:return []
        self.next_send=now+self.PERIOD
        index,current,target,phase,offset,total=self.stage_at(now)
        self.finished=index==len(self.plan.stages)
        self.last_event=dict(stage=index,phase=phase,elapsed=offset,total=total,finished=self.finished)
        return [zone_state(phase,offset,total,current,target)]
