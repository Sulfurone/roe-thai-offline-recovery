"""Small experimental Thai peer roster; default bodies, no combat AI.

Patrol messages use the original trajectory DTO. Terrain checks provide
only ground height and slope; they do not navigate buildings or map props.
"""
import math
import struct
import time

from offline_gameplay import TYPED_ACTOR_UID
from offline_vitals import Vitals
POSITION_MARKER = struct.pack('>3i',123456,234567,34567)


def peer_motion(uid, point, sequence):
    # Thai 27 consumes exactly 36 bytes. 2B is a different, 12-byte DTO;
    # attaching a client trajectory to it silently leaves unread bytes.
    return 0x27, struct.pack('>Q3iBBBffIB', uid, *point, 0, 0, 0, 0., 0., sequence, 0)


class BotRoster:
    def __init__(self, profile, count=1):
        if type(count) is not int or not 1 <= count <= 4:
            raise ValueError('Experimental roster supports 1..4 peers')
        if not 24 <= len(profile) <= 8192 or struct.unpack_from('>II', profile) != (3,1):
            raise ValueError('Regenerate original-codec-validated Thai appearance + runtime profile (mode 3)')
        name_size = struct.unpack_from('>I', profile, 16)[0]
        if not 2 <= name_size <= 128 or len(profile) < 20 + name_size or profile[19 + name_size] != 0:
            raise ValueError('Invalid peer name field')
        if profile.count(POSITION_MARKER) != 1:
            raise ValueError('Regenerate the peer profile with its validated spawn-position marker')
        self.position_offset = profile.index(POSITION_MARKER)
        self.profile, self.count = bytes(profile), count
        self.actors = {}
        self.vitals = {}
        self.next_tick = 0
        self.started = None
        self.retries = 0

    def profile_for(self, uid):
        profile = bytearray(self.profile)
        struct.pack_into('>Q', profile, 8, uid)
        struct.pack_into('>3i',profile,self.position_offset,*self.actors[uid]['position'])
        size = struct.unpack_from('>I', profile, 16)[0]
        if profile[20:20 + size] == b'OfflineBot1\0':
            profile[20 + size - 2] = ord('1') + uid - (TYPED_ACTOR_UID + 0x1000)
        return bytes(profile)

    def spawn(self, population, position, rng):
        if self.actors:
            return []
        replies = []
        for index in range(self.count):
            spot = population.choose_spot(position, rng, peer=True)
            if spot is None:
                continue
            if not hasattr(population.terrain, 'spawn_spot'):
                spot = (spot[0], spot[1], spot[2] - 25)
            uid = TYPED_ACTOR_UID + 0x1000 + index
            self.actors[uid] = dict(origin=spot, position=spot, sequence=1)
            self.vitals[uid] = Vitals()
            replies.extend(((0x565, struct.pack('>B3iBQ', 1, *spot, 0, uid)),
                            (0xbe7, self.profile_for(uid)),self.vitals[uid].packet(uid),peer_motion(uid, spot, 1)))
        self.started = time.monotonic()
        return replies

    def tick(self, population, now=None):
        now = time.monotonic() if now is None else now
        if not self.actors or now < self.next_tick:
            return []
        self.next_tick = now + .5
        elapsed = max(0, now - self.started)
        replies = []
        retry = self.retries < 3 and elapsed >= (1,3,6)[self.retries]
        if retry:
            self.retries += 1
        for uid, actor in self.actors.items():
            if retry:
                replies.extend(((0x565,struct.pack('>B3iBQ',1,*actor['position'],0,uid)),
                                (0xbe7,self.profile_for(uid)),self.vitals[uid].packet(uid)))
            if not self.vitals[uid].current:
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
            if uid in self.actors:
                replies.extend(((0xbe7, self.profile_for(uid)),self.vitals[uid].packet(uid)))
        return replies
