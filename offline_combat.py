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
from offline_weapons import WEAPONS


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
    REPORT_GRACE=.25
    PROJECTILE_SPEED=30000  # local fallback timing, centimetres per second
    DAMAGE=200  # Local balance on the 1000-point health scale.

    def __init__(self,game,bots,visibility=None):
        self.game,self.bots=game,bots
        self.visibility=visibility
        self.shots=deque(maxlen=64)
        self.seen={}
        self.last_event=None

    def ray_hit(self,origin,aim):
        """Nearest loaded bot body intersected by the reported muzzle ray."""
        direction=tuple(b-a for a,b in zip(origin,aim))
        length=math.hypot(*direction)
        unit=tuple(value/length for value in direction)
        closest=self.MAX_RANGE
        hit=None
        for uid,actor in self.bots.active_actors():
            if not self.bots.vitals[uid].current:continue
            foot=actor['position']
            for height in (45,90,135):
                center=(foot[0]-origin[0],foot[1]-origin[1],foot[2]+height-origin[2])
                projection=sum(a*b for a,b in zip(center,unit))
                radial_sq=sum(v*v for v in center)-projection**2
                radius=45
                if radial_sq>radius**2:continue
                half=math.sqrt(radius**2-radial_sq)
                entry=max(0,projection-half)
                if projection+half<=0 or entry>=closest:continue
                closest=entry
                impact=tuple(a+entry*b for a,b in zip(origin,unit))
                hit=(uid,foot,impact,closest,actor.get('activation',0))
        if hit is not None and self.visibility.clear(origin,hit[2]):
            return hit
        return None

    def record_shot(self,body,previous_magazine,now=None):
        now=time.monotonic() if now is None else now
        g=self.game
        # Observe after the gameplay handler: only a genuinely consumed round
        # authorizes a collision. Stop, empty, malformed and fake shots do not.
        if (not g.actor_ready or g.seated or not g.vitals.current
                or previous_magazine<=0 or g.magazine!=previous_magazine-1
                or len(body) not in (29,37) or body[28]!=0):return False
        item=g.inventory.items.get((1,g.selected_slot)) if g.inventory else None
        if item is None or item.template not in WEAPONS or 10401<=item.template<=10403:
            return False  # Shotgun pellet identities/spread are separate work.
        coords=struct.unpack_from('>6f',body)
        if any(not math.isfinite(v) or abs(v)>=2000000 for v in coords):return False
        origin,aim=tuple(coords[:3]),tuple(coords[3:])
        if math.dist(origin,g.player_position)>500 or math.dist(origin,aim)<1:return False
        serial=struct.unpack_from('>I',body,24)[0]
        hit=self.ray_hit(origin,aim) if self.visibility is not None else None
        self.shots.append(Shot(now,origin,aim,item.template,serial,hit))
        return True

    def tick(self,now=None):
        """Give the native report priority, then resolve only confirmed rays."""
        now=time.monotonic() if now is None else now
        self.last_event=None
        self.shots=deque((s for s in self.shots if 0<=now-s.time<=self.WINDOW),maxlen=64)
        if not self.game.vitals.current or self.game.seated:return []
        for shot in self.shots:
            if shot.fallback is None:continue
            uid,foot,impact,distance,activation=shot.fallback
            if now-shot.time<self.REPORT_GRACE+distance/self.PROJECTILE_SPEED:continue
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
        if math.dist(p,actor['position'])>250:return reject('target_position',h.target_uid)
        if (math.hypot(h.impact[0]-p[0],h.impact[1]-p[1])>120
                or not -30<=h.impact[2]-p[2]<=220):return reject('impact_outside_target',h.target_uid)
        candidate=next((shot for shot in reversed(self.shots) if shot.serial==h.shot_serial
                        and math.dist(h.muzzle_position,shot.origin)<=2),None)
        if candidate is None:return reject('no_matching_consumed_shot',h.target_uid)
        if math.dist(h.shooter_position,candidate.origin)>500:
            return reject('shooter_position',h.target_uid)
        direction=tuple(b-a for a,b in zip(candidate.origin,candidate.aim))
        offset=tuple(b-a for a,b in zip(candidate.origin,h.impact))
        distance=sum(a*b for a,b in zip(direction,offset))/math.hypot(*direction)
        lateral=math.sqrt(max(0,sum(v*v for v in offset)-distance*distance))
        if not 0<=distance<=self.MAX_RANGE or lateral>100:
            return reject('shot_trajectory',h.target_uid)
        self.seen[h.sequence]=now
        if len(self.seen)>512:del self.seen[next(iter(self.seen))]
        return self.apply_hit(candidate,h.target_uid,p,h.impact,h.part,source='client_collision',sequence=h.sequence)

    def apply_hit(self,shot,uid,foot,impact,part,*,source,sequence=None):
        self.shots.remove(shot)
        hp=self.bots.vitals[uid]
        before=hp.current
        replies=self.bots.damage(uid,self.DAMAGE)
        applied=before-hp.current
        relative=tuple(round(v-p0) for v,p0 in zip(impact,foot))
        replies.insert(1,hit_feedback(self.game.actor_uid,uid,relative,part,applied,hp.current==0))
        self.last_event=dict(accepted=True,target_uid=uid,sequence=sequence,source=source,
            damage_applied=True,damage=applied,current=hp.current,weapon=shot.weapon,shot_serial=shot.serial,
            distance_m=round(math.dist(shot.origin,impact)/100,2),original_damage_formula=False)
        return replies
