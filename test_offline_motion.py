import math
import struct
import unittest

from offline_motion import actor_motion, aircraft_spawn_heading


def move_body(sequence, points):
    body = struct.pack('>I', len(points))
    for point in points:
        body += struct.pack('>3iBBBI', *point, 0, 0, 0, 0)
    body += struct.pack('>IBfffIBB', sequence, 0, 1., 0., 0., 0, 0, 0)
    return body + bytes(9 * len(points))


def plane_body(position=(200, 204800, 75000)):
    name = b'Aircraft\0'
    return (struct.pack('>QI', 0x5000000200101, len(name)) + name +
            struct.pack('>III3iB4f', 4, 0, 100, *position, 0, 0., 0., 0., 1.) + bytes(35))


class MotionTests(unittest.TestCase):
    def test_batched_move_uses_latest_point_and_sequence(self):
        body = move_body(154, [(100, 200, 300), (90000, 80000, 7000)])
        self.assertEqual(actor_motion(body), ((90000, 80000, 7000), 154))
        for sequence in range(100):
            self.assertEqual(actor_motion(move_body(sequence, [(sequence, 2, 3)])),
                             ((sequence, 2, 3), sequence))

    def test_move_rejects_malformed_bounded_packets(self):
        valid = move_body(1, [(1, 2, 3)])
        for body in (valid[:-1], valid + bytes(1), move_body(1, [(2_000_000, 2, 3)]),
                     move_body(1, [(1, 2, 3)] * 21), bytes(27)):
            self.assertIsNone(actor_motion(body))
        self.assertEqual(actor_motion(struct.pack('>I3i', 1, 100, 200, 300)), ((100, 200, 300), None))

    def test_aircraft_spawn_rotation_aligns_model_y_axis_to_route(self):
        source = plane_body((0, 0, 75000))
        offset = 12 + len(b'Aircraft\0') + 25
        for endpoint in ((1000, 0, 75000), (0, 1000, 75000), (-1000, 0, 75000), (0, -1000, 75000)):
            body = aircraft_spawn_heading(source, endpoint)
            qx, qy, qz, qw = struct.unpack_from('>4f', body, offset)
            facing = (-2 * qz * qw, 1 - 2 * qz * qz)
            length = math.hypot(*endpoint[:2])
            self.assertAlmostEqual(facing[0], endpoint[0] / length, places=6)
            self.assertAlmostEqual(facing[1], endpoint[1] / length, places=6)
            self.assertEqual(body[:offset], source[:offset])
            self.assertEqual(body[offset + 16:], source[offset + 16:])


if __name__ == '__main__':
    unittest.main()
