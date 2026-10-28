"""Original Thai character projectile collision report (C2S 11E9).

Only directly proven UID/position/serial fields are named. The trailer is
opaque pending recovery; parsing a report is not authority to apply damage.
"""
from dataclasses import dataclass
import math
import struct

HIT=struct.Struct('>IQ3iB3f3iB3fB3iBIBB4I')


@dataclass(frozen=True)
class CharacterHit:
    sequence: int
    target_uid: int
    ray_origin: tuple
    ray_direction: tuple
    target_position: tuple
    impact: tuple
    part: int
    state: tuple
    opaque: tuple


def character_hit(body):
    if len(body) not in (HIT.size,HIT.size+8):return None
    r=HIT.unpack_from(body)
    # D6AA10 is a fixed xyz/flag DTO. This sender does not initialize every
    # position flag; do not impose a guessed zero on those transport fields.
    points=(tuple(r[2:5]),tuple(r[9:12]),tuple(r[13:16]))
    direction=tuple(r[6:9])
    if not r[1] or any(not math.isfinite(v) or abs(v)>=2000000 for p in points+(direction,) for v in p):
        return None
    # E71010 passes its shot record first, and the raycast collision result
    # third. The integer position is the ray origin, the float position is
    # the impact; the neighbouring vector belongs to the shot, not a normal.
    return CharacterHit(r[0],r[1],points[0],direction,points[1],points[2],r[16],tuple(r[17:21]),tuple(r[21:]))
