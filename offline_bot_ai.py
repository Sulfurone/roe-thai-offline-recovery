"""Experimental local bot perception/chase/short-burst state machine.

Visibility uses conservative static spheres and terrain, not full original
physics/navigation. Aim/cadence/damage are local prototype rules, not recovered
original server AI. This is separate from the passive rendering probe.
"""
from dataclasses import dataclass
import math
import random
import time

from offline_bots import PEER_TICK_MS,peer_clock,peer_locomotion
from offline_combat import death_packet,hit_feedback
from offline_peer_messages import peer_equipment,peer_facing,peer_fire
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
    contact_at:float=0
    equipped:bool=False
    last_known:tuple|None=None
    firing:tuple|None=None
    stop_at:float=0
    reload_at:float=0
    sense_at:float=0
    visible:bool=False
    patrol_waypoint:int=0
    search_step:int=-1
    search_heading:float=0
    contact_phase:str='search'
    heard_at:float=-math.inf
    activation:int=0
    peer_retry:int=0
    facing_at:float=0


class BotAI:
    WARMUP=8.
    EQUIP_DELAY=1.
    AIM_SECONDS=.8
    FIRE_INTERVAL=.9
    MAX_SIMULTANEOUS_SHOOTERS=2
    RELOAD_SECONDS=3.
    DETECT_DISTANCE=9000
    FIRE_DISTANCE=8000
    WALK_SPEED=220
    RUN_SPEED=500
    RUN_DISTANCE=600
    ARRIVAL_DISTANCE=100
    PATROL_RADIUS=1200
    PATROL_WAYPOINTS=8
    DAMAGE=20
    SHOT_SECONDS=.12
    MEMORY_SECONDS=12.
    SEARCH_RADIUS=425
    SEARCH_ANGLES=(0, math.pi/2, -math.pi/2, math.pi)
    HEAR_DISTANCE=6500
    HEAR_SECONDS=2.
    AIM_ERROR_DEGREES=1.2
    MODES=('target','patrol','combat')

    def __init__(self,game,bots,population,visibility,mode='combat'):
        if mode not in self.MODES:raise ValueError('Unknown bot mode')
        self.game,self.bots,self.population,self.visibility=game,bots,population,visibility
        self.mode=mode
        self.rng=random.Random(getattr(population,'seed',1))
        self.brains={}
        self.previous_tick=None
        self.motion_epoch=None
        self.next_clock=0
        self.last_retries=0
        self.events=[]
        self.last_shot=None
        bots.external_motion=True
        bots.motion_tick=self.motion_tick
        population.peer_visibility=visibility

    def motion_tick(self,now):
        if self.motion_epoch is None:self.motion_epoch=now
        return 1+max(0,math.floor((now-self.motion_epoch)*1000/PEER_TICK_MS+1e-8))

    def sync_motion_clock(self,now):
        if now<self.next_clock:return None
        self.next_clock=now+5
        return peer_clock(self.motion_tick(now))

    def stop_walking(self,uid,*,crouch=False):
        actor=self.bots.actors.get(uid)
        if actor is None:return []
        walking=actor.pop('walking',False)
        if walking or actor.get('crouched',False)!=crouch:
            actor['crouched']=crouch
            actor['sequence']=(actor['sequence']+1)&0xffffffff
            point=actor['position']
            tick=self.motion_tick(self.previous_tick)
            return [peer_locomotion(uid,point,point,actor['sequence'],0,actor.get('heading',0),
                                    tick,tick+1,action=2 if crouch else 1)]
        return []

    def stop(self,brain):
        replies=self.stop_walking(brain.uid)
        if brain.firing is None:return replies
        origin,aim=brain.firing
        brain.firing=None
        return replies+[peer_fire(brain.uid,origin,aim,True)]

    def set_mode(self,mode):
        if mode not in self.MODES:raise ValueError('Unknown bot mode')
        if mode==self.mode:return []
        self.mode=mode
        self.last_shot=None
        replies=[]
        for brain in self.brains.values():
            if self.bots.visible(brain.uid):replies.extend(self.stop(brain))
            brain.phase='waiting';brain.target=brain.last_known=None
            brain.search_step=-1
            brain.visible=False;brain.sense_at=0
        return replies

    def patrol(self,uid,dt):
        actor=self.bots.actors[uid];brain=self.brains[uid]
        origin=actor['origin']
        start=actor['position']
        radius=self.PATROL_RADIUS
        if self.bots.streamed:radius+=200*(uid%5)

        def waypoint():
            angle=math.tau*brain.patrol_waypoint/self.PATROL_WAYPOINTS
            return (origin[0]+radius*math.cos(angle),origin[1]+radius*math.sin(angle),origin[2])

        destination=waypoint()
        if math.dist(start[:2],destination[:2])<self.ARRIVAL_DISTANCE:
            brain.patrol_waypoint=(brain.patrol_waypoint+1)%self.PATROL_WAYPOINTS
            destination=waypoint()
        running=(brain.patrol_waypoint+uid)%2==0 and math.dist(start[:2],destination[:2])>=self.RUN_DISTANCE
        replies=self.walk_towards(uid,destination,dt,speed=self.RUN_SPEED if running else self.WALK_SPEED)
        brain.phase='patrol_run' if running and actor['position']!=start else 'patrol'
        if dt>=.05 and actor['position']==start:
            # Try the next destination when collision blocks every step.
            brain.patrol_waypoint=(brain.patrol_waypoint+1)%self.PATROL_WAYPOINTS
        return replies

    def aim_at(self,origin,target):
        # Sample once per reaction interval, never follow an unseen live target.
        dx,dy=target[0]-origin[0],target[1]-origin[1]
        yaw=math.radians(self.rng.uniform(-self.AIM_ERROR_DEGREES,self.AIM_ERROR_DEGREES))
        return (origin[0]+dx*math.cos(yaw)-dy*math.sin(yaw),
                origin[1]+dx*math.sin(yaw)+dy*math.cos(yaw),target[2])

    def equipment(self,uid):
        brain=self.brains.get(uid)
        return (peer_equipment(uid,brain.weapon_uid,magazine=brain.magazine,clothing=self.bots.outfits.get(uid,()))
                if brain else None)

    def face_target(self,brain,target,now):
        actor=self.bots.actors[brain.uid]
        x,y,z=actor['position']
        dx,dy,dz=target[0]-x,target[1]-y,target[2]-z-150
        heading=math.atan2(dy,dx)
        length=math.hypot(dx,dy,dz)
        replies=self.stop_walking(brain.uid)
        actor['heading']=heading
        brain.facing_at=now+.1
        return replies+[peer_facing(brain.uid,heading,dz/length if length else 0)]

    def walk_towards(self,uid,destination,seconds,*,speed=None):
        actor=self.bots.actors[uid]
        point=actor['position']
        dx,dy=destination[0]-point[0],destination[1]-point[1]
        distance=math.hypot(dx,dy)
        if distance<self.ARRIVAL_DISTANCE:
            return self.stop_walking(uid)
        angle=math.atan2(dy,dx)
        speed=self.WALK_SPEED if speed is None else speed
        step=min(distance,speed*seconds)
        if step<.1:return []
        side=actor.get('detour',1 if not self.bots.streamed or uid%2 else -1)
        for adjustment in (0,side*math.pi/4,-side*math.pi/4,side*math.pi/2,-side*math.pi/2):
            end=(point[0]+step*math.cos(angle+adjustment),point[1]+step*math.sin(angle+adjustment),point[2])
            accepted=self.visibility.walk(point,end)
            if accepted is None or accepted==point:continue
            replies=self.stop_walking(uid) if actor.get('crouched') else []
            tick=self.motion_tick(self.previous_tick)
            first=actor.get('motion_end',tick) if actor.get('walking') else tick
            last=max(first+1,tick+1)
            actor['position']=accepted
            actor['sequence']=(actor['sequence']+1)&0xffffffff
            heading=math.atan2(accepted[1]-point[1],accepted[0]-point[0])
            actor['walking']=True
            actor['motion_end']=last
            actor['heading']=heading
            if adjustment:actor['detour']=1 if adjustment>0 else -1
            return replies+[peer_locomotion(uid,point,accepted,actor['sequence'],speed,heading,first,last,
                                           running=speed==self.RUN_SPEED)]
        return self.stop_walking(uid)

    def search(self,uid,brain,dt):
        actor=self.bots.actors[uid]
        start=actor['position']
        anchor=brain.last_known
        if brain.search_step<0:
            distance=math.dist(start[:2],anchor[:2])
            if distance>=self.ARRIVAL_DISTANCE:
                speed=self.RUN_SPEED if distance>=self.RUN_DISTANCE else self.WALK_SPEED
                replies=self.walk_towards(uid,anchor,dt,speed=speed)
                if dt>=.05 and actor['position']==start:
                    brain.search_step=0
                    brain.search_heading=math.atan2(anchor[1]-start[1],anchor[0]-start[0])
                return replies
            brain.search_step=0
            brain.search_heading=actor.get('heading',0)

        # Sweep distinct points around the remembered location, then return
        # to patrol. The current position of a hidden player is never used.
        side=1 if uid%2 else -1
        while brain.search_step<len(self.SEARCH_ANGLES):
            heading=brain.search_heading+side*self.SEARCH_ANGLES[brain.search_step]
            point=(anchor[0]+self.SEARCH_RADIUS*math.cos(heading),
                   anchor[1]+self.SEARCH_RADIUS*math.sin(heading),anchor[2])
            if math.dist(start[:2],point[:2])<self.ARRIVAL_DISTANCE:
                brain.search_step+=1
                continue
            replies=self.walk_towards(uid,point,dt)
            if dt>=.05 and actor['position']==start:
                brain.search_step+=1
            return replies
        brain.last_known=None
        return self.patrol(uid,dt)

    def hear_shot(self,origin,now=None):
        if self.mode=='combat':
            self.last_shot=(time.monotonic() if now is None else now,origin)

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
        zone=self.bots.zones.migration_target(now) if self.bots.zones is not None else None
        for uid,actor in self.bots.active_actors():
            brain=self.brains.setdefault(uid,Brain(uid,now,0x2000000000100+uid-self.bots.FIRST_UID))
            activation=actor.get('activation',0)
            if activation!=brain.activation:
                brain.activation=activation
                brain.created=now
                brain.equipped=brain.visible=False
                brain.firing=brain.target=brain.last_known=None
                brain.search_step=-1
                brain.heard_at=now
                brain.phase='preparing'
                brain.sense_at=0
            if not self.bots.vitals[uid].current:
                replies.extend(self.stop(brain))
                brain.phase='dead'
                continue
            if brain.firing is not None and (now>=brain.stop_at or not active or self.mode!='combat'):
                replies.extend(self.stop(brain))
            refresh=actor.get('retry',0)!=brain.peer_retry if self.bots.streamed else retry
            if now-brain.created>=self.EQUIP_DELAY and (not brain.equipped or refresh):
                replies.append(self.equipment(uid))
                brain.equipped=True
                brain.peer_retry=actor.get('retry',0)
                self.events.append(dict(action='equipped',uid=uid,magazine=brain.magazine,reserve=brain.reserve))
            # Reload progress is independent of whether the target is currently
            # observed; pausing perception must not reset the transfer timer.
            if brain.reload_at and now>=brain.reload_at:
                amount=min(30-brain.magazine,brain.reserve)
                brain.magazine+=amount;brain.reserve-=amount;brain.reload_at=0
                replies.append(self.equipment(uid))
                self.events.append(dict(action='reloaded',uid=uid,magazine=brain.magazine,reserve=brain.reserve))
                brain.phase='search'
                replies.extend(self.stop_walking(uid))
            if not active or not g.vitals.current or now-brain.created<self.WARMUP:
                replies.extend(self.stop_walking(uid))
                brain.phase='waiting'
                brain.target=None
                brain.visible=False;brain.sense_at=0
                continue
            if self.mode!='combat':
                brain.phase=self.mode
                if self.mode=='patrol':replies.extend(self.patrol(uid,dt))
                continue
            if brain.reload_at:
                brain.phase='reload'
                continue
            if not brain.magazine:
                if brain.reserve:
                    brain.phase='reload'
                    brain.reload_at=now+self.RELOAD_SECONDS
                    if self.bots.streamed:replies.extend(self.stop_walking(uid,crouch=True))
                else:brain.phase='empty'
                continue
            point=actor['position']
            if zone is not None and math.hypot(point[0]-zone.x,point[1]-zone.y)>zone.radius:
                brain.phase='zone_run'
                brain.target=None
                replies.extend(self.walk_towards(uid,(zone.x,zone.y,point[2]),dt,speed=self.RUN_SPEED))
                continue
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
                    brain.search_step=-1
                    brain.contact_phase='search'
                    brain.contact_at=now;brain.last_known=target
            visible=brain.visible and distance<=self.DETECT_DISTANCE
            if not visible:
                brain.target=None
                if now-brain.contact_at>self.MEMORY_SECONDS:
                    brain.last_known=None
                if brain.last_known is None and self.last_shot is not None:
                    fired_at,noise=self.last_shot
                    if (fired_at>brain.heard_at and 0<=now-fired_at<=self.HEAR_SECONDS
                            and math.dist(point,noise)<=self.HEAR_DISTANCE):
                        brain.heard_at=brain.contact_at=fired_at
                        brain.last_known=noise
                        brain.contact_phase='investigate'
                        brain.search_step=-1
                if brain.last_known is not None:
                    brain.phase=brain.contact_phase
                    replies.extend(self.search(uid,brain,dt))
                else:
                    replies.extend(self.patrol(uid,dt))
                continue
            if distance>self.FIRE_DISTANCE:
                brain.phase='chase'
                brain.target=None
                replies.extend(self.walk_towards(uid,brain.last_known,dt,speed=self.RUN_SPEED))
                continue
            if (self.bots.streamed and brain.phase=='cooldown' and now<brain.deadline
                    and brain.firing is None and distance>900):
                angle=math.atan2(target[1]-point[1],target[0]-point[0])
                angle+=math.pi/2 if uid%2 else -math.pi/2
                side=(point[0]+250*math.cos(angle),point[1]+250*math.sin(angle),point[2])
                replies.extend(self.walk_towards(uid,side,dt))
                continue
            if not brain.equipped:
                replies.extend(self.stop_walking(uid))
                continue
            if brain.phase not in ('aim','cooldown'):
                brain.phase='aim'
                brain.deadline=now+self.AIM_SECONDS+(.08*(uid%5) if self.bots.streamed else 0)
                brain.target=self.aim_at(origin,brain.last_known)
                replies.extend(self.face_target(brain,brain.target,now))
                continue
            if now<brain.deadline:
                if brain.target is not None and (brain.phase=='aim' and now>=brain.facing_at or actor.get('walking')):
                    replies.extend(self.face_target(brain,brain.target,now))
                continue
            if brain.phase=='cooldown':
                brain.phase='aim'
                brain.deadline=now+self.AIM_SECONDS
                brain.target=self.aim_at(origin,brain.last_known)
                replies.extend(self.face_target(brain,brain.target,now))
                continue
            aim=brain.target
            if aim is None or math.dist(origin,aim)<1 or distance>self.FIRE_DISTANCE or not self.visibility.clear(origin,aim):
                brain.phase='search'
                continue
            if self.bots.streamed and sum(other.firing is not None and now<other.stop_at
                                          for other in self.brains.values())>=self.MAX_SIMULTANEOUS_SHOOTERS:
                brain.deadline=now+.12
                continue
            brain.magazine-=1
            replies.extend(self.face_target(brain,aim,now))
            replies.append(peer_fire(uid,origin,aim))
            brain.firing=(origin,aim);brain.stop_at=now+self.SHOT_SECONDS
            brain.phase='cooldown'
            brain.deadline=now+self.FIRE_INTERVAL+(.3 if self.bots.streamed else 0)
            # Aim is locked during reaction time: lateral movement can dodge
            # this approximation, rather than granting unavoidable hits.
            impact=self.player_impact(origin,aim)
            hit=impact is not None
            self.events.append(dict(action='bot_fire',uid=uid,magazine=brain.magazine,hit=hit))
            if hit:replies.extend(self.damage_player(uid,impact))
        return replies
