import math
import struct
import unittest
from offline_hit_reports import HIT,character_hit


def hit_body():
    return HIT.pack(37,0x1000000001100,325800,271700,6600,0,1.,0.,0.,
                    326000,271700,6500,0,326000.,271700.,6600.,2,11,12,13,14,91,2,1,10201,5,125,9)


class HitReportTests(unittest.TestCase):
    def test_proven_fields_and_opaque_tail_stay_distinct(self):
        self.assertEqual(HIT.size,98)
        h=character_hit(hit_body())
        self.assertEqual((h.sequence,h.target_uid),(37,0x1000000001100))
        self.assertEqual(h.ray_origin,(325800,271700,6600))
        self.assertEqual(h.impact,(326000.,271700.,6600.))
        self.assertEqual(h.target_position,(326000,271700,6500))
        self.assertEqual(h.ray_direction,(1.,0.,0.))
        self.assertEqual(h.part,2)
        self.assertEqual(h.state,(11,12,13,14))
        self.assertEqual(h.opaque,(91,2,1,10201,5,125,9))
        self.assertEqual(character_hit(hit_body()+b'\xff'*8),h)

    def test_truncated_invalid_uid_and_nonfinite_positions_are_not_hits(self):
        b=hit_body()
        for candidate in (b[:-1],b+b'\0',b+bytes(9),b[:4]+bytes(8)+b[12:]):
            self.assertIsNone(character_hit(candidate))
        for offset in (25,50,54,58):
            for value in (math.nan,math.inf,-math.inf,2000000.):
                bad=bytearray(b);struct.pack_into('>f',bad,offset,value)
                self.assertIsNone(character_hit(bad))


if __name__=='__main__':unittest.main()
