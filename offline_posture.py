"""Sparse crouch/prone/standing speed calibration for the original Thai client.

Posture enum: stand=0, crouch=1, prone=2 (107EE40 registration).
106FB20 uses rows 1/2 of 28FB4E0 for the latter two postures. These
offline tuning values are not claimed to be recovered live-server defaults.

Standing backward speed
-----------------------
Standing used to be left alone on the assumption that its 5.6 m/s baseline was
uniform. Running 106FB20 against a property block seeded by the stock delta
shows it is not: every standing direction resolves to (560, 560, 120), so
backward movement is under a quarter of forward. The slow component is fed by
attributes 15 and 16, which the stock delta seeds to 120.

Raising both to 560 makes all three standing directions report (560, 560, 560)
while crouch, prone, the auxiliary limits (33/38/53) and the 6000 fall limit
stay exactly as they were. See MOVEMENT_POSTURES.md for the measurements.
"""
import struct

CROUCH_CM_PER_SECOND=280
PRONE_CM_PER_SECOND=120

# Standing components that resolve to the backward speed; stock seeds 120.
STAND_ATTRIBUTES=(15,16)
STAND_CM_PER_SECOND=560

# Crouch/prone rows and auxiliary limits that are slow by design.
PRESERVED_SLOW_ATTRIBUTES=(22,23,28,29,33,38,53)


def posture_speed_delta():
    # Crouch, prone and the corrected standing backward components. The
    # auxiliary movement parameters and downward limit46 stay untouched.
    values={**{i:CROUCH_CM_PER_SECOND for i in range(17,22)},
            **{i:PRONE_CM_PER_SECOND for i in range(24,28)},
            **{i:STAND_CM_PER_SECOND for i in STAND_ATTRIBUTES}}
    # Never silently exceed a value that is slow on purpose: if a future edit
    # overlaps a preserved attribute this raises instead of writing it wrong.
    for index in PRESERVED_SLOW_ATTRIBUTES:
        if values.get(index,0)>=STAND_CM_PER_SECOND:
            raise RuntimeError(
                f'Posture calibration would speed up protected attribute {index}')
    return struct.pack('>H',len(values))+b''.join(
        struct.pack('>BII',index,value,value) for index,value in sorted(values.items()))
