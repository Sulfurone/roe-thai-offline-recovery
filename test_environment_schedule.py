import struct
import unittest

from offline_environment import EnvironmentSchedule


class EnvironmentScheduleTests(unittest.TestCase):
    def test_arms_only_on_valid_current_map_position(self):
        schedule=EnvironmentSchedule(12,delay=1)
        self.assertFalse(schedule.observe(0x0dcd,bytes(16),now=10))
        self.assertFalse(schedule.observe(0x002a,bytes(15),now=10))
        invalid=struct.pack('>I3i',1,2_000_000,0,0)
        self.assertFalse(schedule.observe(0x002a,invalid,now=10))
        valid=struct.pack('>I3i',1,100,200,300)
        self.assertTrue(schedule.observe(0x002a,valid,now=10))
        self.assertEqual(schedule.armed_at,11)
        self.assertEqual(schedule.position_reports,1)

    def test_delivers_clock_once_after_delay(self):
        schedule=EnvironmentSchedule(12,delay=1.5)
        body=struct.pack('>I3i',1,100,200,300)
        schedule.observe(0x002a,body,now=20)
        self.assertIsNone(schedule.take(now=21.49,timestamp=1000))
        message,payload=schedule.take(now=21.5,timestamp=1000)
        self.assertEqual(message,0x4816)
        self.assertEqual(payload,struct.pack('>II',12,1000))
        self.assertIsNone(schedule.take(now=30,timestamp=1001))

    def test_rejects_unsafe_delay(self):
        for delay in (-.1,30.1):
            with self.assertRaises(ValueError):
                EnvironmentSchedule(12,delay)


if __name__=='__main__':
    unittest.main()
