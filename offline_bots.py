"""Thai peer roster and bounded client interest management.

Patrol messages use the original trajectory DTO. Terrain checks provide
only ground height and slope; they do not navigate buildings or map props.
"""
from collections import deque
import math
import struct
import time

from offline_gameplay import TYPED_ACTOR_UID
from offline_vitals import Vitals
POSITION_MARKER = struct.pack('>3i',123456,234567,34567)


def peer_motion(uid, point, sequence):
    # Thai 0x27 has a 36-byte body. The remote controller accepts mode 3
    # and queues subtype 0 for interpolation.
    return 0x27, struct.pack('>Q3iBBBffIB', uid, *point, 0, 3, 0, 0., 0., sequence, 0)


def peer_locomotion(uid, start, end, sequence, speed, heading):
    # The native interpolator reads the base point and a relative keyframe.
    # Forward intent is separate from the keyframe action, which is an event.
    intent = int(speed > 0)
    first_tick = (sequence - intent) & 0xffffffff
    displacement = (b-a for a,b in zip(start,end))
    body = struct.pack('>QH3iBBIB', uid, round(speed), *start, 0, 0, first_tick, 1)
    # The offline client's world tick duration is zero. A 50 ms keyframe
    # offset gives the animation queue a playback interval even in that
    # state. The native action reader ignores 50, outside its 1..34 range.
    keyframe_ms = 50 if intent else 0
    body += struct.pack('>3hBBI', *displacement, 0, keyframe_ms, sequence)
    azimuth = round((heading / math.pi + 1) * 65535 / 2)
    body += struct.pack('>bHHI', intent, azimuth, 32768, sequence)
    return 0x25, body


class BotRoster:
    MAX_COUNT = 63
    ACTIVE_LIMIT = 8
    ENTER_RANGE = 16000
    LEAVE_RANGE = 21000
    CORPSE_SECONDS = 20
    FIRST_UID = TYPED_ACTOR_UID + 0x1000

    def __init__(self, profile, count=1):
        if type(count) is not int or not 1 <= count <= self.MAX_COUNT:
            raise ValueError('Local roster supports 1..63 peers')
        if not 24 <= len(profile) <= 8192 or struct.unpack_from('>II', profile) != (3,1):
            raise ValueError('Regenerate original-codec-validated Thai appearance + runtime profile (mode 3)')
        name_size = struct.unpack_from('>I', profile, 16)[0]
        if not 2 <= name_size <= 128 or len(profile) < 20 + name_size or profile[19 + name_size] != 0:
            raise ValueError('Invalid peer name field')
        if profile.count(POSITION_MARKER) != 1:
            raise ValueError('Regenerate the peer profile with its validated spawn-position marker')
        self.position_offset = profile.index(POSITION_MARKER)
        self.name_size = name_size
        self.profile, self.count = bytes(profile), count
        self.streamed = count > 4
        self.actors = {}
        self.vitals = {self.FIRST_UID+i:Vitals() for i in range(count)} if self.streamed else {}
        self.active = set()
        self.placement_anchors = None
        self.next_tick = 0
        self.started = None
        self.retries = 0
        self.external_motion=False
        self.death_parcel = None
        self.death_notice = None
        self.zones = None
        self.encounter_at = None
        self.encounter_position = None

    def visible(self,uid):
        return uid in (self.active if self.streamed else self.actors)

    def active_actors(self):
        if self.streamed:
            return ((uid,self.actors[uid]) for uid in sorted(self.active))
        return self.actors.items()

    @classmethod
    def name_for(cls,uid):
        return f'AI-{uid-cls.FIRST_UID+1}'

    def profile_for(self, uid):
        profile = bytearray(self.profile)
        struct.pack_into('>Q', profile, 8, uid)
        struct.pack_into('>3i',profile,self.position_offset,*self.actors[uid]['position'])
        name=(self.name_for(uid)+'\0').encode('ascii')
        struct.pack_into('>I',profile,16,len(name))
        profile[20:20+self.name_size] = name
        return bytes(profile)

    def announce(self,uid):
        actor=self.actors[uid]
        return [(0x565,struct.pack('>B3iBQ',1,*actor['position'],0,uid)),
                (0xbe7,self.profile_for(uid)),self.vitals[uid].packet(uid),
                peer_motion(uid,actor['position'],actor['sequence'])]

    def move_unseen(self,population,position,rng,now):
        """Reposition only surviving participants who have never loaded in view."""
        reserve=[actor for uid,actor in self.actors.items() if self.vitals[uid].current
                 and not actor.get('activation')
                 and math.dist(actor['position'][:2],position[:2])>self.LEAVE_RANGE]
        if not reserve:return
        target=self.zones.migration_target(now) if self.zones is not None else None
        if target is not None:
            outside=next((actor for actor in reserve if math.hypot(actor['position'][0]-target.x,
                          actor['position'][1]-target.y)>target.radius),None)
            if outside is not None:
                angle=rng.uniform(0,math.tau)
                radius=target.radius*rng.uniform(.35,.8)
                anchor=(target.x+round(radius*math.cos(angle)),target.y+round(radius*math.sin(angle)),position[2])
                spot=population.choose_spot(anchor,rng,peer=True,accept=lambda p:
                    math.hypot(p[0]-target.x,p[1]-target.y)<target.radius and
                    math.dist(p[:2],position[:2])>=7000)
                if spot is not None:outside.update(position=spot,origin=spot)
        if now<self.encounter_at:return
        self.encounter_at=now+15
        near=sum(self.vitals[uid].current>0 and math.dist(actor['position'][:2],position[:2])<=self.ENTER_RANGE
                 for uid,actor in self.actors.items())
        if near>=2:return
        current=self.zones.circle_at(now) if self.zones is not None else None
        if current and math.hypot(position[0]-current[0],position[1]-current[1])>current[2]:return
        angle=rng.uniform(0,math.tau)
        anchor=(position[0]+round(9500*math.cos(angle)),position[1]+round(9500*math.sin(angle)),position[2])
        spot=population.choose_spot(anchor,rng,peer=True,accept=lambda p:
            6500<=math.dist(p[:2],position[:2])<=13000 and
            (not current or math.hypot(p[0]-current[0],p[1]-current[1])<current[2]))
        if spot is not None:
            reserve[-1].update(position=spot,origin=spot)
            self.encounter_at=now+55

    def stream(self,population,position,rng,now):
        if self.placement_anchors is None:
            # Three early encounters, then groups of three spread over the map.
            width=getattr(population.terrain,'width',409600)
            sectors=[(round(width*x/8),round(width*y/8),position[2])
                     for x in range(1,8) for y in range(1,8)
                     if math.dist((width*x/8,width*y/8),position[:2])>24000]
            rng.shuffle(sectors)
            self.placement_anchors=[position]*min(3,self.count)
            self.placement_anchors.extend(sectors[i//3%len(sectors)] if sectors else position
                                          for i in range(self.count-len(self.placement_anchors)))
            self.pending_placements=deque(range(self.count))
            self.encounter_at=now+90
        for _ in range(min(3,len(self.pending_placements))):
            index=self.pending_placements.popleft()
            uid=self.FIRST_UID+index
            anchor=self.placement_anchors[index]
            spot=population.choose_spot(anchor,rng,peer=True)
            if spot is None:
                # Move failed sectors to the end. A later visit can provide
                # walkable ground while preserving the original participant.
                width=getattr(population.terrain,'width',409600)
                self.placement_anchors[index]=(rng.randrange(1,8)*width//8,
                                               rng.randrange(1,8)*width//8,position[2])
                self.pending_placements.append(index)
                continue
            if not hasattr(population.terrain,'spawn_spot'):
                spot=(*spot[:2],spot[2]-25)
            self.actors[uid]=dict(origin=spot,position=spot,sequence=1,created=now,retry=3)

        self.move_unseen(population,position,rng,now)
        distances={uid:math.dist(actor['position'][:2],position[:2]) for uid,actor in self.actors.items()}
        removed=sorted(uid for uid in self.active if distances[uid]>self.LEAVE_RANGE
                       or now>=self.actors[uid].get('retire_at',math.inf))
        replies=[]
        if removed:
            self.active.difference_update(removed)
            for uid in removed:
                self.actors[uid].pop('walking',None)
            # Native interest removal takes a short count and a UID list.
            replies.append((0x605,struct.pack('>H',len(removed))+b''.join(struct.pack('>Q',uid) for uid in removed)))
        nearby=sorted((dist,uid) for uid,dist in distances.items()
                      if uid not in self.active and self.vitals[uid].current and dist<=self.ENTER_RANGE)
        for _,uid in nearby[:min(3,self.ACTIVE_LIMIT-len(self.active))]:
            self.active.add(uid)
            actor=self.actors[uid]
            actor.update(created=now,retry=0)
            actor['activation']=actor.get('activation',0)+1
            replies.extend(self.announce(uid))
        return replies

    def life_packets(self,uid):
        from offline_combat import death_packet
        hp=self.vitals[uid]
        return [hp.packet(uid)]+([death_packet(uid)] if not hp.current else [])

    def damage(self,uid,amount,*,killer=None):
        hp=self.vitals.get(uid)
        if hp is None or not hp.current:return []
        if not hp.damage(amount):return []
        if not hp.current and self.death_notice is not None:self.death_notice(uid,killer)
        if self.streamed and uid not in self.active:return []
        replies = self.life_packets(uid)
        if not hp.current:
            if self.streamed:self.actors[uid]['retire_at']=time.monotonic()+self.CORPSE_SECONDS
            if self.death_parcel is not None:replies.extend(self.death_parcel(uid))
        return replies

    def spawn(self, population, position, rng):
        if self.streamed:
            return self.stream(population,position,rng,time.monotonic())
        if len(self.actors)>=self.count:
            return []
        replies = []
        created=time.monotonic()
        for index in range(self.count):
            uid = self.FIRST_UID + index
            if uid in self.actors:continue
            spot = population.choose_spot(position, rng, peer=True)
            if spot is None:
                continue
            if not hasattr(population.terrain, 'spawn_spot'):
                spot = (spot[0], spot[1], spot[2] - 25)
            self.actors[uid] = dict(origin=spot, position=spot, sequence=1,created=created,retry=0)
            self.vitals[uid] = Vitals()
            replies.extend(self.announce(uid))
        if replies and self.started is None:self.started=created
        return replies

    def tick(self, population, now=None):
        now = time.monotonic() if now is None else now
        if not self.actors or now < self.next_tick:
            return []
        self.next_tick = now + .5
        replies = []
        retried=False
        for uid, actor in self.active_actors():
            elapsed=max(0,now-actor.get('created',self.started))
            attempt=actor.get('retry',0)
            retry=attempt<3 and elapsed>=(1,3,6)[attempt]
            if retry:
                actor['retry']=attempt+1
                retried=True
                replies.extend(((0x565,struct.pack('>B3iBQ',1,*actor['position'],0,uid)),
                                (0xbe7,self.profile_for(uid))))
                replies.extend(self.life_packets(uid))
            if not self.vitals[uid].current:
                continue
            if self.external_motion:
                continue
            x, y, _ = actor['origin']
            # A small terrain-screened patrol, not original navigation/AI.
            angle = elapsed * .15
            px, py = round(x + 1200 * math.sin(angle)), round(y + 1200 * (1 - math.cos(angle)))
            if hasattr(population.terrain,'peer_walkable') and population.terrain.peer_walkable(px,py) is None:
                continue
            height = population.surface(px, py)
            if height is None or abs(height + 5 - actor['position'][2]) > 200:
                continue
            actor['position'] = (px, py, height + 5)
            actor['sequence'] = (actor['sequence'] + 1) & 0xffffffff
            replies.append(peer_motion(uid, actor['position'], actor['sequence']))
        if retried:self.retries+=1
        return replies

    def handle(self, message, body):
        if message != 0xbe6 or len(body) < 8:
            return None
        mode, count = struct.unpack_from('>II', body)
        if mode not in (1,2,3) or not 0 <= count <= 8 or len(body) != 8 + 8 * count:
            return []
        replies = []
        for index in range(count):
            uid = struct.unpack_from('>Q', body, 8 + index * 8)[0]
            if self.visible(uid):
                replies.extend(((0xbe7, self.profile_for(uid)),))
                replies.extend(self.life_packets(uid))
        return replies
