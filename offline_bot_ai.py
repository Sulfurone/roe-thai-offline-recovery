"""Experimental local bot perception/chase/short-burst state machine.

Visibility uses conservative static spheres and terrain, not full original
physics/navigation. Aim/cadence/damage are local prototype rules, not recovered
original server AI. This is separate from the passive rendering probe.
"""
from dataclasses import dataclass
import math
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

    def __init__(self,game,bots,population,visibility):
        self.game,self.bots,self.population,self.visibility=game,bots,population,visibility
        self.brains={}
        self.previous_tick=None
        self.last_retries=0
        self.events=[]
        bots.external_motion=True
        population.peer_visibility=visibility

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
                brain.phase='dead'
                continue
            if now-brain.created>=self.EQUIP_DELAY and (not brain.equipped or retry):
                replies.append(self.equipment(uid))
                brain.equipped=True
                self.events.append(dict(action='equipped',uid=uid,magazine=brain.magazine,reserve=brain.reserve))
            if not active or not g.vitals.current or now-brain.created<self.WARMUP:
                brain.phase='waiting'
                brain.target=None
                continue
            if brain.phase=='reload':
                if now<brain.deadline:continue
                amount=min(30-brain.magazine,brain.reserve)
                brain.magazine+=amount
                brain.reserve-=amount
                replies.append(self.equipment(uid))
                self.events.append(dict(action='reloaded',uid=uid,magazine=brain.magazine,reserve=brain.reserve))
                brain.phase='search'
            if not brain.magazine:
                if brain.reserve:
                    brain.phase='reload'
                    brain.deadline=now+self.RELOAD_SECONDS
                else:brain.phase='empty'
                continue
            point=actor['position']
            origin=(point[0],point[1],point[2]+150)
            # Local torso aim, consistent with the coarse body capsule and
            # armour region. Exact pose-dependent bones remain pending.
            target=(*g.player_position[:2],g.player_position[2]+90)
            distance=math.dist(point,g.player_position)
            sight=getattr(self.visibility,'sight_clear',self.visibility.clear)
            visible=distance<=self.DETECT_DISTANCE and sight(origin,target)
            if not visible:
                brain.phase='search'
                if brain.target is not None and now-brain.last_seen<=5:
                    replies.extend(self.walk_towards(uid,brain.target,dt))
                else:
                    ox,oy,oz=actor['origin']
                    elapsed=now-brain.created
                    replies.extend(self.walk_towards(uid,(ox+800*math.sin(elapsed*.12),oy+800*(1-math.cos(elapsed*.12)),oz),dt))
                continue
            brain.last_seen=now
            if distance>self.FIRE_DISTANCE:
                brain.phase='chase'
                brain.target=target
                replies.extend(self.walk_towards(uid,target,dt))
                continue
            if not brain.equipped:continue
            if brain.phase not in ('aim','cooldown'):
                brain.phase='aim'
                brain.deadline=now+self.AIM_SECONDS
                brain.target=target
                continue
            if now<brain.deadline:continue
            if brain.phase=='cooldown':
                brain.phase='aim'
                brain.deadline=now+self.AIM_SECONDS
                brain.target=target
                continue
            aim=brain.target
            if distance>self.FIRE_DISTANCE or not self.visibility.clear(origin,aim):
                brain.phase='search'
                continue
            brain.magazine-=1
            replies.extend((peer_fire(uid,origin,aim),peer_fire(uid,origin,aim,True)))
            brain.phase='cooldown'
            brain.deadline=now+self.FIRE_INTERVAL
            # Aim is locked during reaction time: lateral movement can dodge
            # this approximation, rather than granting unavoidable hits.
            impact=self.player_impact(origin,aim)
            hit=impact is not None
            self.events.append(dict(action='bot_fire',uid=uid,magazine=brain.magazine,hit=hit))
            if hit:replies.extend(self.damage_player(uid,impact))
        return replies
