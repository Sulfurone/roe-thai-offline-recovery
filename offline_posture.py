"""Sparse crouch/prone speed calibration for the original Thai client.

Posture enum: stand=0, crouch=1, prone=2 (107EE40 registration).
106FB20 uses rows 1/2 of 28FB4E0 for the latter two postures. These
offline tuning values are not claimed to be recovered live-server defaults.
"""
import struct

CROUCH_CM_PER_SECOND=280
PRONE_CM_PER_SECOND=120


def posture_speed_delta():
    # Preserve standing, auxiliary movement parameters and downward limit46.
    values={**{i:CROUCH_CM_PER_SECOND for i in range(17,22)},
            **{i:PRONE_CM_PER_SECOND for i in range(24,28)}}
    return struct.pack('>H',len(values))+b''.join(
        struct.pack('>BII',index,value,value) for index,value in sorted(values.items()))
