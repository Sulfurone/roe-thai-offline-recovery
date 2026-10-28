"""Thai 0x002A trajectory layout, checked against the original DDE540 reader."""
import math
import struct


def actor_motion(body):
    """Return latest point and acknowledgement word, or None.

    Full DTO: count DWORD, N * 19-byte points, 23-byte common block,
    N * 9-byte extras. Historical tests also use a bare 16-byte prefix;
    that prefix never generates an acknowledgement.
    """
    if len(body) == 16:
        position = struct.unpack_from('>3i', body, 4)
        return (position, None) if all(abs(x) < 2_000_000 for x in position) else None
    if len(body) < 27:
        return None
    count = struct.unpack_from('>I', body)[0]
    if not 1 <= count <= 20 or len(body) != 27 + 28 * count:
        return None
    points = [struct.unpack_from('>3i', body, 4 + 19 * index) for index in range(count)]
    if any(abs(value) >= 2_000_000 for point in points for value in point):
        return None
    common = 4 + 19 * count
    if not all(math.isfinite(x) for x in struct.unpack_from('>3f', body, common + 5)):
        return None
    return points[-1], struct.unpack_from('>I', body, common)[0]


def aircraft_spawn_heading(body, endpoint):
    """Orient config-4 spawn from local +Y toward the horizontal route."""
    if len(body) < 53:
        raise ValueError('Aircraft spawn is truncated')
    name = struct.unpack_from('>I', body, 8)[0]
    start = 12 + name
    if not 1 <= name <= 128 or len(body) < start + 41 or body[start - 1] != 0:
        raise ValueError('Aircraft spawn name/rotation bounds differ')
    if struct.unpack_from('>I', body, start)[0] != 4:
        return body
    origin = struct.unpack_from('>3i', body, start + 12)
    dx, dy = endpoint[0] - origin[0], endpoint[1] - origin[1]
    if dx == dy == 0:
        return body
    yaw = -math.atan2(dx, dy)
    updated = bytearray(body)
    struct.pack_into('>4f', updated, start + 25, 0., 0., math.sin(yaw / 2), math.cos(yaw / 2))
    return bytes(updated)
