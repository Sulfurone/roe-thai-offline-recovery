"""Original Thai character projectile collision report (C2S 11E9).

Only directly proven UID, position and serial fields are named. Parsing a
report is not authority to apply damage.
"""
from dataclasses import dataclass
import math
import struct

HIT=struct.Struct('>IQ3iB3f3iB3fB3iBIBB4I')


@dataclass(frozen=True)
class CharacterHit:
    sequence: int
    target_uid: int
    shooter_position: tuple
    muzzle_position: tuple
    target_position: tuple
    impact: tuple
    part: int
    state: tuple
    opaque: tuple

    @property
    def shot_serial(self):
        return self.opaque[3]


def character_hit(body):
    if len(body) not in (HIT.size,HIT.size+8):return None
    r=HIT.unpack_from(body)
    # D6AA10 is a fixed xyz/flag DTO. This sender does not initialize every
    # position flag; do not impose a guessed zero on those transport fields.
    shooter,muzzle,target,impact=tuple(r[2:5]),tuple(r[6:9]),tuple(r[9:12]),tuple(r[13:16])
    if not r[1] or any(not math.isfinite(v) or abs(v)>=2000000 for p in (shooter,muzzle,target,impact) for v in p):
        return None
    # The first float position and the shot serial match the 11D3 muzzle
    # and serial. E71010 supplies the later float position from the collision.
    return CharacterHit(r[0],r[1],shooter,muzzle,target,impact,r[16],tuple(r[17:21]),tuple(r[21:]))
