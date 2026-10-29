import math
import struct
import unittest
from offline_zones import Circle,zone_state,interpolated_circle


class ZoneTests(unittest.TestCase):
    def test_native_verified_phase_zero_and_shrinking_snapshots(self):
        current=Circle(200000,190000,150000.)
        target=Circle(215000,180000,90000.)
        self.assertEqual(zone_state(0,0,120,current,target),
            (0x47b,struct.pack('>IfIiifiif',0,0.,120,200000,190000,150000.,215000,180000,90000.)))
        for elapsed,expected in ((0,(200000.,190000.,150000.)),
                                  (30,(203750.,187500.,135000.)),
                                  (60,(207500.,185000.,120000.)),
                                  (120,(215000.,180000.,90000.))):
            self.assertEqual(interpolated_circle(elapsed,120,current,target),expected)
            mid,wire=zone_state(2,elapsed,120,current,target)
            self.assertEqual(mid,0x47b)
            self.assertEqual(len(wire),36)
            self.assertEqual(struct.unpack('>IfI',wire[:12]),(2,float(elapsed),120))

    def test_invalid_geometry_and_time_are_rejected_before_serializing(self):
        for values in ((-1,0,100),(0,409601,100),(True,0,100),(0,0,0),
                       (0,0,-10),(0,0,float('nan')),(0,0,float('inf')),(0,0,600001)):
            with self.assertRaises(ValueError):Circle(*values)
        current=Circle(200000,190000,150000)
        target=Circle(215000,180000,90000)
        for phase,elapsed,total in ((3,0,120),(True,0,120),(0,-1,120),(2,121,120),
                                    (2,0,0),(2,0,True),(2,math.inf,120),(2,0,86401)):
            with self.assertRaises(ValueError):zone_state(phase,elapsed,total,current,target)
        with self.assertRaises(ValueError):zone_state(2,0,120,(0,0,1),target)


if __name__=='__main__':unittest.main()
