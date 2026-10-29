"""Original Thai 047B circle state, without a guessed full match controller.

Native DD32E0/DD3210 encode phase, elapsed float, total seconds DWORD and
two integer-XY/float-radius circles. The original phase-2 consumer blends
the circles using elapsed/total. No epoch timestamp is involved here.
"""
from dataclasses import dataclass
import math
import struct


@dataclass(frozen=True)
class Circle:
    x:int
    y:int
    radius:float

    def __post_init__(self):
        if (type(self.x) is not int or type(self.y) is not int
                or not 0<=self.x<=409600 or not 0<=self.y<=409600
                or type(self.radius) not in (int,float) or not math.isfinite(self.radius)
                or not 0<self.radius<=600000):
            raise ValueError('Circle exceeds the local Thai-map bounds')


def zone_state(phase,elapsed,total,current,target):
    """Build a bounded original DTO; phases/pacing remain caller decisions.

    These numeric bounds are local validation, not recovered server limits.
    Phase 0 initializes the displayed circles; phase 2 carries shrink progress.
    Phase 1's full warning/UI behavior has not yet been verified.
    """
    if (type(phase) is not int or phase not in (0,1,2)
            or type(total) is not int or not 1<=total<=86400
            or type(elapsed) not in (int,float) or not math.isfinite(elapsed)
            or not 0<=elapsed<=total
            or type(current) is not Circle or type(target) is not Circle):
        raise ValueError('Invalid local circle state')
    return 0x047b,struct.pack('>IfIiifiif',phase,float(elapsed),total,
        current.x,current.y,current.radius,target.x,target.y,target.radius)


def interpolated_circle(elapsed,total,current,target):
    """Float tuple matching the independently executed native phase-2 slice."""
    zone_state(2,elapsed,total,current,target)
    fraction=elapsed/total
    return tuple(a+(b-a)*fraction for a,b in zip(
        (current.x,current.y,current.radius),(target.x,target.y,target.radius)))
