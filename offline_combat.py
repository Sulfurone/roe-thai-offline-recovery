"""Bounded offline bot damage candidate using the Thai life/death messages.

The stock client's collision reports are cross-checked against consumed
shots and known bot positions. Original full damage/armor rules and server
map collision are not recovered; this remains an explicit experimental mode.
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


class BotCombat:
    WINDOW=3.
    DAMAGE=20  # Current original WeaponParams prefix/encoded attribute 4.

    def __init__(self,game,bots):
        self.game,self.bots=game,bots
        self.shots=deque(maxlen=64)
        self.seen={}
        self.last_event=None

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
        self.shots.append(Shot(now,origin,aim,item.template))
        return True

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
        if actor is None or hp is None or not hp.current:return reject('unknown_or_dead_target',h.target_uid)
        p=actor['position']
        if math.dist(h.target_position,p)>250:return reject('target_position',h.target_uid)
        if (math.hypot(h.impact[0]-p[0],h.impact[1]-p[1])>120
                or not -30<=h.impact[2]-p[2]<=220):return reject('impact_outside_target',h.target_uid)
        candidate=None
        for shot in self.shots:
            if math.dist(h.ray_origin,shot.origin)>200:continue
            direction=tuple(b-a for a,b in zip(shot.origin,shot.aim))
            offset=tuple(b-a for a,b in zip(shot.origin,h.impact))
            length=math.sqrt(sum(v*v for v in direction))
            distance=sum(a*b for a,b in zip(direction,offset))/length
            if not 0<=distance<=min(length+200,100000):continue
            lateral=math.sqrt(max(0,sum(v*v for v in offset)-distance*distance))
            if lateral>100:continue
            candidate=shot;break
        if candidate is None:return reject('no_matching_consumed_shot',h.target_uid)
        self.shots.remove(candidate)
        self.seen[h.sequence]=now
        if len(self.seen)>512:del self.seen[next(iter(self.seen))]
        before=hp.current
        replies=self.bots.damage(h.target_uid,self.DAMAGE)
        applied=before-hp.current
        relative=tuple(round(v-p0) for v,p0 in zip(h.impact,p))
        replies.insert(1,hit_feedback(g.actor_uid,h.target_uid,relative,h.part,applied,hp.current==0))
        self.last_event=dict(accepted=True,target_uid=h.target_uid,sequence=h.sequence,
            damage_applied=True,damage=applied,current=hp.current,weapon=candidate.weapon,
            original_damage_formula=False)
        return replies
