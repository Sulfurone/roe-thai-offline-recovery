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


def actor_actions(body):
    """Actions carried by complete 2A trajectory points, or None if invalid.

    Original medicine cancel 1303C20 -> movement action 20 -> 12CE3A0
    writes the first point's action byte; the second point can be zero.
    Neither the preceding position flag nor the final common flags are it.
    """
    if len(body)==16 or actor_motion(body) is None:return None
    count=struct.unpack_from('>I',body)[0]
    return tuple(body[4+19*index+13] for index in range(count))


def random_aircraft_route(rng, terrain):
    """Choose a directed edge-to-edge Thai route with a dry jump corridor."""
    edge, center = 200, 204800
    far = center * 2 - edge
    for _ in range(64):
        angle = rng.uniform(0, math.tau)
        dx, dy = math.cos(angle), math.sin(angle)
        offset = rng.uniform(-75000, 75000)
        x, y = center - dy * offset, center + dx * offset
        intersections = [((low - axis) / delta, (high - axis) / delta)
                         for axis, delta, low, high in ((x,dx,edge,far),(y,dy,edge,far)) if abs(delta)>1e-9]
        first = max(min(pair) for pair in intersections)
        last = min(max(pair) for pair in intersections)
        start = round(x + dx * first), round(y + dy * first), 75000
        end = round(x + dx * last), round(y + dy * last), 75000
        dry = 0
        last_jump = None
        for i in range(2,19):
            fraction = i / 20
            px, py = (a + (b-a) * fraction for a,b in zip(start[:2],end[:2]))
            ground = terrain.height_at(px,py)
            if ground is None or not ground >= 6500-1e-6:
                continue
            dry += 1
            if fraction >= .5 and all(
                    (height := terrain.height_at(px+ox,py+oy)) is not None and height >= 6500-1e-6
                    for ox,oy in ((-7500,0),(7500,0),(0,-7500),(0,7500))):
                last_jump = fraction
        if dry >= 6 and last_jump is not None:
            return start, end, last_jump
    raise ValueError('Could not find a cross-map aircraft route over dry Thai terrain')


def aircraft_spawn_heading(body, endpoint, *, origin=None):
    """Place and orient config-4 spawn from local +Y along the route."""
    if len(body) < 53:
        raise ValueError('Aircraft spawn is truncated')
    name = struct.unpack_from('>I', body, 8)[0]
    start = 12 + name
    if not 1 <= name <= 128 or len(body) < start + 41 or body[start - 1] != 0:
        raise ValueError('Aircraft spawn name/rotation bounds differ')
    if struct.unpack_from('>I', body, start)[0] != 4:
        return body
    if origin is None:
        origin = struct.unpack_from('>3i', body, start + 12)
    dx, dy = endpoint[0] - origin[0], endpoint[1] - origin[1]
    if dx == dy == 0:
        return body
    yaw = -math.atan2(dx, dy)
    updated = bytearray(body)
    struct.pack_into('>3i', updated, start + 12, *origin)
    struct.pack_into('>4f', updated, start + 25, 0., 0., math.sin(yaw / 2), math.cos(yaw / 2))
    return bytes(updated)
