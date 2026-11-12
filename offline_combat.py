"""Bounded offline bot damage candidate using the Thai life/death messages.

Cross-check native collisions against consumed shots, with a terrain-aware
fallback for loaded bots when the client omits a character collision.
"""
from collections import deque
from dataclasses import dataclass
import math
import struct
import time

from offline_hit_reports import character_hit
from offline_armour import local_region
from offline_weapons import MUZZLE_VELOCITIES,WEAPONS


def death_packet(uid):
    if type(uid) is not int or not 0<uid<2**64:raise ValueError('Invalid death owner')
    return 0x533,struct.pack('>IQ',0,uid)


def hit_feedback(shooter,target,relative,part,damage,killed):
    if any(type(uid) is not int or not 0<uid<2**64 for uid in (shooter,target)):
        raise ValueError('Invalid hit owners')
    if (len(relative)!=3 or any(type(v) is not int or abs(v)>=2000000 for v in relative)
            or type(part) is not int or not 0<=part<=255
            or type(damage) is not int or not 0<=damage<=100000 or type(killed) is not bool):
        raise ValueError('Invalid hit feedback')
    return 0x11eb,struct.pack('>QQ3iBBIB',shooter,target,*relative,0,part,damage,int(killed))


@dataclass
class Shot:
    time: float
    origin: tuple
    aim: tuple
    weapon: int
    serial: int
    fallback: tuple | None = None


class BotCombat:
    WINDOW=3.
    MAX_RANGE=100000  # centimetres; the 11D3 aim point encodes direction
    SHOTGUN_RANGE=30000
    PELLET_SLOPE=math.tan(math.radians(3))
    REPORT_GRACE=.25
    GRAVITY=981.  # local ballistic approximation, centimetres per second squared
    POSITION_WINDOW=.25
    DAMAGE=200  # Local balance on the 1000-point health scale.

    def __init__(self,game,bots,visibility=None):
        self.game,self.bots=game,bots
        self.visibility=visibility
        self.shots=deque(maxlen=64)
        self.seen={}
        self.last_event=None
        self.recent_positions={}
        self.shot_check=None

    def record_positions(self,now):
        current={}
        for uid,actor in self.bots.active_actors():
            if not self.bots.vitals[uid].current:continue
            activation=actor.get('activation',0)
            positions=self.recent_positions.get(uid)
            if positions is None:positions=deque(maxlen=8)
            while positions and (now-positions[0][0]>self.POSITION_WINDOW or positions[0][1]!=activation):
                positions.popleft()
            foot=actor['position']
            if positions and positions[-1][2]==foot:
                positions[-1]=(now,activation,foot)
            else:
                positions.append((now,activation,foot))
            current[uid]=positions
        self.recent_positions=current

    def ray_hit(self,shot,now):
        """Intersect the muzzle trajectory with current or recently displayed bodies."""
        origin=shot.origin
        direction=tuple(b-a for a,b in zip(origin,shot.aim))
        length=math.hypot(*direction)
        unit=tuple(value/length for value in direction)
        speed=MUZZLE_VELOCITIES[shot.weapon]
        drop=self.GRAVITY/(2*speed**2)
        closest=self.SHOTGUN_RANGE if self.is_shotgun(shot) else self.MAX_RANGE
        hit=None
        for uid,actor in self.bots.active_actors():
            if not self.bots.vitals[uid].current:continue
            activation=actor.get('activation',0)
            foot=actor['position']
            feet={foot}
            feet.update(position for at,revision,position in self.recent_positions.get(uid,())
                        if 0<=now-at<=self.POSITION_WINDOW and revision==activation)
            for point in feet:
                for height in (45,90,135):
                    center=(point[0]-origin[0],point[1]-origin[1],point[2]+height-origin[2])
                    projection=sum(a*b for a,b in zip(center,unit))
                    adjusted=(*center[:2],center[2]+drop*projection**2)
                    projection=sum(a*b for a,b in zip(adjusted,unit))
                    radial_sq=sum(v*v for v in adjusted)-projection**2
                    if radial_sq>45**2:continue
                    half=math.sqrt(45**2-radial_sq)
                    entry=max(0,projection-half)
                    if projection+half<=0 or entry>=closest:continue
                    closest=entry
                    hit=(uid,point,entry,activation)
        if hit is None:return None,'no_body_intersection'

        uid,foot,distance,activation=hit
        # Follow the curved path for cover checks, including hills and doors.
        steps=max(1,math.ceil(distance/2000))
        previous=origin
        for step in range(1,steps+1):
            along=distance*step/steps
            point=(origin[0]+along*unit[0],origin[1]+along*unit[1],
                   origin[2]+along*unit[2]-drop*along**2)
            if not self.visibility.clear(previous,point):return None,'blocked'
            previous=point
        return (uid,foot,previous,distance,activation),'awaiting_collision'

    @staticmethod
    def is_shotgun(shot):
        return WEAPONS[shot.weapon].ammunition==30004

    def record_shot(self,body,previous_magazine,now=None):
        now=time.monotonic() if now is None else now
        g=self.game
        self.shot_check=None
        # Observe after the gameplay handler: only a genuinely consumed round
        # authorizes a collision. Stop, empty, malformed and fake shots do not.
        if (not g.actor_ready or g.seated or not g.vitals.current
                or previous_magazine<=0 or g.magazine!=previous_magazine-1
                or len(body) not in (29,37) or body[28]!=0):return False
        item=g.inventory.items.get((1,g.selected_slot)) if g.inventory else None
        if item is None or item.template not in WEAPONS:return False
        coords=struct.unpack_from('>6f',body)
        if any(not math.isfinite(v) or abs(v)>=2000000 for v in coords):return False
        origin,aim=tuple(coords[:3]),tuple(coords[3:])
        if math.dist(origin,g.player_position)>500 or math.dist(origin,aim)<1:return False
        serial=struct.unpack_from('>I',body,24)[0]
        shot=Shot(now,origin,aim,item.template,serial)
        if self.visibility is not None:
            shot.fallback,reason=self.ray_hit(shot,now)
            self.shot_check=dict(shot_serial=serial,weapon=item.template,result=reason,
                                 distance_m=round(shot.fallback[3]/100,2) if shot.fallback else None)
        self.shots.append(shot)
        return True

    def tick(self,now=None):
        """Give the native report priority, then resolve only confirmed rays."""
        now=time.monotonic() if now is None else now
        self.last_event=None
        if self.visibility is not None:self.record_positions(now)
        self.shots=deque((s for s in self.shots if 0<=now-s.time<=self.WINDOW),maxlen=64)
        if not self.game.vitals.current or self.game.seated:return []
        for shot in self.shots:
            if shot.fallback is None:continue
            uid,foot,impact,distance,activation=shot.fallback
            if now-shot.time<self.REPORT_GRACE+distance/MUZZLE_VELOCITIES[shot.weapon]:continue
            shot.fallback=None
            actor=self.bots.actors.get(uid)
            if (actor is None or not self.bots.visible(uid) or not self.bots.vitals[uid].current
                    or actor.get('activation',0)!=activation):continue
            return self.apply_hit(shot,uid,foot,impact,2,source='local_ray')
        return []

    def handle(self,body,now=None):
        now=time.monotonic() if now is None else now
        self.last_event=None
        self.shots=deque((s for s in self.shots if 0<=now-s.time<=self.WINDOW),maxlen=64)
        self.seen={seq:t for seq,t in self.seen.items() if 0<=now-t<=120}
        def reject(reason,uid=None):
            self.last_event=dict(accepted=False,reason=reason,target_uid=uid,damage_applied=False)
            return []
        h=character_hit(body)
        if h is None:return reject('invalid_report')
        g=self.game
        if not g.actor_ready or g.seated or not g.vitals.current:return reject('player_not_active',h.target_uid)
        if h.sequence in self.seen:return reject('duplicate',h.target_uid)
        actor=self.bots.actors.get(h.target_uid)
        hp=self.bots.vitals.get(h.target_uid)
        if actor is None or hp is None or not hp.current or not self.bots.visible(h.target_uid):
            return reject('unknown_or_dead_target',h.target_uid)
        p=h.target_position
        if math.dist(p,actor['position'])>250 and not any(
                0<=now-at<=self.POSITION_WINDOW and revision==actor.get('activation',0)
                and math.dist(p,position)<=250 for at,revision,position in self.recent_positions.get(h.target_uid,())):
            return reject('target_position',h.target_uid)
        if (math.hypot(h.impact[0]-p[0],h.impact[1]-p[1])>120
                or not -30<=h.impact[2]-p[2]<=220):return reject('impact_outside_target',h.target_uid)
        candidate=next((shot for shot in reversed(self.shots) if shot.serial==h.shot_serial
                        and math.dist(h.muzzle_position,shot.origin)<=2),None)
        if candidate is None:return reject('no_matching_consumed_shot',h.target_uid)
        if math.dist(h.shooter_position,candidate.origin)>500:
            return reject('shooter_position',h.target_uid)
        direction=tuple(b-a for a,b in zip(candidate.origin,candidate.aim))
        offset=tuple(b-a for a,b in zip(candidate.origin,h.impact))
        length=math.hypot(*direction)
        distance=sum(a*b for a,b in zip(direction,offset))/length
        drop=.5*self.GRAVITY*(distance/MUZZLE_VELOCITIES[candidate.weapon])**2
        lateral=math.hypot(*(v-a*distance/length for v,a in zip(offset,direction)))
        corrected=math.hypot(*(v-a*distance/length for v,a in zip((*offset[:2],offset[2]+drop),direction)))
        # All native pellet reports from a shell share the shot serial. The
        # first valid hit consumes that shell once, without multiplying damage.
        shotgun=self.is_shotgun(candidate)
        limit=self.SHOTGUN_RANGE if shotgun else self.MAX_RANGE
        tolerance=100+distance*self.PELLET_SLOPE if shotgun else 100
        if not 0<=distance<=limit or min(lateral,corrected)>tolerance:
            return reject('shot_trajectory',h.target_uid)
        self.seen[h.sequence]=now
        if len(self.seen)>512:del self.seen[next(iter(self.seen))]
        return self.apply_hit(candidate,h.target_uid,p,h.impact,h.part,source='client_collision',sequence=h.sequence)

    def apply_hit(self,shot,uid,foot,impact,part,*,source,sequence=None):
        self.shots.remove(shot)
        hp=self.bots.vitals[uid]
        before=hp.current
        replies=self.bots.damage(uid,self.DAMAGE,killer=self.game.actor_uid,weapon=shot.weapon,
                                 headshot=local_region(impact,foot)=='head')
        applied=before-hp.current
        relative=tuple(round(v-p0) for v,p0 in zip(impact,foot))
        replies.insert(1,hit_feedback(self.game.actor_uid,uid,relative,part,applied,hp.current==0))
        self.last_event=dict(accepted=True,target_uid=uid,sequence=sequence,source=source,
            damage_applied=True,damage=applied,current=hp.current,weapon=shot.weapon,shot_serial=shot.serial,
            distance_m=round(math.dist(shot.origin,impact)/100,2),original_damage_formula=False)
        return replies
