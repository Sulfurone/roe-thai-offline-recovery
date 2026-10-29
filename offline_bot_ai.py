"""Experimental local bot perception/chase/short-burst state machine.

Visibility uses conservative static spheres and terrain, not full original
physics/navigation. Aim/cadence/damage are local prototype rules, not recovered
original server AI. This is separate from the passive rendering probe.
"""
from dataclasses import dataclass
import math
import random
import time

from offline_bots import peer_motion
from offline_combat import death_packet,hit_feedback
from offline_peer_messages import peer_equipment,peer_fire
from offline_armour import absorb_bullet,local_region


@dataclass
class Brain:
    uid:int
    created:float
    weapon_uid:int
    magazine:int=30
    reserve:int=120
    phase:str='preparing'
    deadline:float=0
    target:tuple|None=None
    last_seen:float=0
    equipped:bool=False
    last_known:tuple|None=None
    firing:tuple|None=None
    stop_at:float=0
    reload_at:float=0
    sense_at:float=0
    visible:bool=False


class BotAI:
    WARMUP=8.
    EQUIP_DELAY=1.
    AIM_SECONDS=.8
    FIRE_INTERVAL=.9
    RELOAD_SECONDS=3.
    DETECT_DISTANCE=9000
    FIRE_DISTANCE=8000
    WALK_SPEED=220
    DAMAGE=20
    SHOT_SECONDS=.12
    MEMORY_SECONDS=5.
    AIM_ERROR_DEGREES=1.2
    MODES=('target','patrol','combat')

    def __init__(self,game,bots,population,visibility,mode='combat'):
        if mode not in self.MODES:raise ValueError('Unknown bot mode')
        self.game,self.bots,self.population,self.visibility=game,bots,population,visibility
        self.mode=mode
        self.rng=random.Random(getattr(population,'seed',1))
        self.brains={}
        self.previous_tick=None
        self.last_retries=0
        self.events=[]
        bots.external_motion=True
        population.peer_visibility=visibility

    def stop(self,brain):
        if brain.firing is None:return []
        origin,aim=brain.firing
        brain.firing=None
        return [peer_fire(brain.uid,origin,aim,True)]

    def set_mode(self,mode):
        if mode not in self.MODES:raise ValueError('Unknown bot mode')
        if mode==self.mode:return []
        self.mode=mode
        replies=[]
        for brain in self.brains.values():
            replies.extend(self.stop(brain))
            brain.phase='waiting';brain.target=brain.last_known=None
            brain.visible=False;brain.sense_at=0
        return replies

    def patrol(self,uid,now,dt):
        actor=self.bots.actors[uid];brain=self.brains[uid]
        ox,oy,oz=actor['origin'];elapsed=now-brain.created
        return self.walk_towards(uid,(ox+800*math.sin(elapsed*.12),oy+800*(1-math.cos(elapsed*.12)),oz),dt)

    def aim_at(self,origin,target):
        # Sample once per reaction interval, never follow an unseen live target.
        dx,dy=target[0]-origin[0],target[1]-origin[1]
        yaw=math.radians(self.rng.uniform(-self.AIM_ERROR_DEGREES,self.AIM_ERROR_DEGREES))
        return (origin[0]+dx*math.cos(yaw)-dy*math.sin(yaw),
                origin[1]+dx*math.sin(yaw)+dy*math.cos(yaw),target[2])

    def equipment(self,uid):
        brain=self.brains.get(uid)
        return peer_equipment(uid,brain.weapon_uid,magazine=brain.magazine) if brain else None

    def walk_towards(self,uid,destination,seconds):
        actor=self.bots.actors[uid]
        point=actor['position']
        dx,dy=destination[0]-point[0],destination[1]-point[1]
        distance=math.hypot(dx,dy)
        if distance<100:return []
        angle=math.atan2(dy,dx)
        step=min(distance,self.WALK_SPEED*seconds)
        if step<.1:return []
        for adjustment in (0,math.pi/4,-math.pi/4,math.pi/2,-math.pi/2):
            end=(point[0]+step*math.cos(angle+adjustment),point[1]+step*math.sin(angle+adjustment),point[2])
            accepted=self.visibility.walk(point,end)
            if accepted is None:continue
            actor['position']=accepted
            actor['sequence']=(actor['sequence']+1)&0xffffffff
            return [peer_motion(uid,accepted,actor['sequence'])]
        return []

    def damage_player(self,uid,impact):
        g=self.game
        if not g.vitals.current:return []
        region=local_region(impact,g.player_position)
        previous=dict(g.inventory.items) if g.inventory is not None else None
        armour=absorb_bullet(g.inventory,self.DAMAGE,region)
        if armour.absorbed:
            try:g.save_state()
            except (OSError,ValueError):
                g.inventory.items=previous
                raise
        applied=g.vitals.damage(armour.damage)
        if not applied:return []
        replies=([g.inventory.delta([(1,armour.slot)])] if armour.absorbed else [])
        replies.extend([g.vitals.packet(g.actor_uid),hit_feedback(uid,g.actor_uid,
            tuple(round(v-p) for v,p in zip(impact,g.player_position)),2,applied,not g.vitals.current)]
        )
        if not g.vitals.current:
            g.medicine.pending=None
            replies.append(death_packet(g.actor_uid))
        self.events.append(dict(action='player_hit',shooter_uid=uid,damage=applied,
                                local_region=region,armour_absorbed=armour.absorbed,
                                armour_uid=armour.uid,armour_remaining=armour.after,
                                current=g.vitals.current,original_damage_formula=False))
        return replies

    def player_impact(self,origin,aim):
        # Intersect the shot ray with a coarse vertical player body. Moving
        # along the ray is not a dodge; moving clear of it can be. Original
        # pose-dependent capsules, armor and hit parts remain separate work.
        point=self.game.player_position
        delta=tuple(b-a for a,b in zip(origin,aim))
        length=math.sqrt(sum(v*v for v in delta))
        if length<1:return None
        delta=tuple(v*self.FIRE_DISTANCE/length for v in delta)
        xy=delta[0]**2+delta[1]**2
        t=max(0,min(1,sum((point[i]-origin[i])*delta[i] for i in (0,1))/xy)) if xy else 0
        impact=tuple(a+t*d for a,d in zip(origin,delta))
        if (math.dist(impact[:2],point[:2])>55 or not point[2]-20<=impact[2]<=point[2]+180
                or not self.visibility.clear(origin,impact)):return None
        return impact

    def tick(self,now=None):
        now=time.monotonic() if now is None else now
        self.events=[]
        dt=min(.5,max(0,now-self.previous_tick)) if self.previous_tick is not None else 0
        self.previous_tick=now
        g=self.game
        replies=[]
        retry=self.last_retries!=self.bots.retries
        self.last_retries=self.bots.retries
        fresh=(g.actor_ready and not g.seated and g.vitals.current>0 and g.has_fresh_self_position(now))
        # Terrain is not the player's current floor. Upper stories, rooftops
        # and jumping can be several metres above it and remain valid targets.
        # Airborne distance and occlusion are handled by the actual aim ray;
        # seated aircraft/vehicles, dead/unready and stale targets stay paused.
        active=fresh
        for index,(uid,actor) in enumerate(self.bots.actors.items()):
            brain=self.brains.setdefault(uid,Brain(uid,now,0x2000000000100+index))
            if not self.bots.vitals[uid].current:
                replies.extend(self.stop(brain))
                brain.phase='dead'
                continue
            if brain.firing is not None and (now>=brain.stop_at or not active or self.mode!='combat'):
                replies.extend(self.stop(brain))
            if now-brain.created>=self.EQUIP_DELAY and (not brain.equipped or retry):
                replies.append(self.equipment(uid))
                brain.equipped=True
                self.events.append(dict(action='equipped',uid=uid,magazine=brain.magazine,reserve=brain.reserve))
            # Reload progress is independent of whether the target is currently
            # observed; pausing perception must not reset the transfer timer.
            if brain.reload_at and now>=brain.reload_at:
                amount=min(30-brain.magazine,brain.reserve)
                brain.magazine+=amount;brain.reserve-=amount;brain.reload_at=0
                replies.append(self.equipment(uid))
                self.events.append(dict(action='reloaded',uid=uid,magazine=brain.magazine,reserve=brain.reserve))
                brain.phase='search'
            if not active or not g.vitals.current or now-brain.created<self.WARMUP:
                brain.phase='waiting'
                brain.target=None
                brain.visible=False;brain.sense_at=0
                continue
            if self.mode!='combat':
                brain.phase=self.mode
                if self.mode=='patrol':replies.extend(self.patrol(uid,now,dt))
                continue
            if brain.reload_at:
                brain.phase='reload'
                continue
            if not brain.magazine:
                if brain.reserve:
                    brain.phase='reload'
                    brain.reload_at=now+self.RELOAD_SECONDS
                else:brain.phase='empty'
                continue
            point=actor['position']
            origin=(point[0],point[1],point[2]+150)
            # Local torso aim, consistent with the coarse body capsule and
            # armour region. Exact pose-dependent bones remain pending.
            target=(*g.player_position[:2],g.player_position[2]+90)
            distance=math.dist(point,g.player_position)
            sight=getattr(self.visibility,'sight_clear',self.visibility.clear)
            if now>=brain.sense_at:
                brain.sense_at=now+.2
                brain.visible=distance<=self.DETECT_DISTANCE and sight(origin,target)
                if brain.visible:
                    brain.last_seen=now;brain.last_known=target
            visible=brain.visible and distance<=self.DETECT_DISTANCE
            if not visible:
                brain.phase='search'
                brain.target=None
                if brain.last_known is not None and now-brain.last_seen<=self.MEMORY_SECONDS:
                    replies.extend(self.walk_towards(uid,brain.last_known,dt))
                else:
                    brain.last_known=None
                    replies.extend(self.patrol(uid,now,dt))
                continue
            if distance>self.FIRE_DISTANCE:
                brain.phase='chase'
                brain.target=None
                replies.extend(self.walk_towards(uid,brain.last_known,dt))
                continue
            if not brain.equipped:continue
            if brain.phase not in ('aim','cooldown'):
                brain.phase='aim'
                brain.deadline=now+self.AIM_SECONDS
                brain.target=self.aim_at(origin,brain.last_known)
                continue
            if now<brain.deadline:continue
            if brain.phase=='cooldown':
                brain.phase='aim'
                brain.deadline=now+self.AIM_SECONDS
                brain.target=self.aim_at(origin,brain.last_known)
                continue
            aim=brain.target
            if aim is None or math.dist(origin,aim)<1 or distance>self.FIRE_DISTANCE or not self.visibility.clear(origin,aim):
                brain.phase='search'
                continue
            brain.magazine-=1
            replies.append(peer_fire(uid,origin,aim))
            brain.firing=(origin,aim);brain.stop_at=now+self.SHOT_SECONDS
            brain.phase='cooldown'
            brain.deadline=now+self.FIRE_INTERVAL
            # Aim is locked during reaction time: lateral movement can dodge
            # this approximation, rather than granting unavoidable hits.
            impact=self.player_impact(origin,aim)
            hit=impact is not None
            self.events.append(dict(action='bot_fire',uid=uid,magazine=brain.magazine,hit=hit))
            if hit:replies.extend(self.damage_player(uid,impact))
        return replies
