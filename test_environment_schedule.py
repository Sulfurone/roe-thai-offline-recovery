import struct
import unittest

from offline_environment import (EnvironmentSchedule, NATIVE_WEATHER_IDS,
                                 WeatherSchedule, environment_weather)


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

    def test_weather_dto_matches_native_callback_fields(self):
        self.assertEqual(environment_weather(2,30),
                         (0x4817,struct.pack('>4I',0,2,30,0)))
        self.assertEqual(NATIVE_WEATHER_IDS,
                         frozenset((*range(1,23),24,25)))
        for weather_id in (0,23,26,2.0,True):
            with self.assertRaises(ValueError):
                environment_weather(weather_id,30)
        for transition in (-1,601,30.0,True):
            with self.assertRaises(ValueError):
                environment_weather(2,transition)

    def test_weather_waits_for_player_and_is_sent_once(self):
        schedule=WeatherSchedule(12,transition_seconds=15,delay=2)
        body=struct.pack('>I3i',1,100,200,300)
        self.assertTrue(schedule.observe(0x002a,body,now=20))
        self.assertIsNone(schedule.take(now=21.99))
        self.assertEqual(schedule.take(now=22),
                         (0x4817,struct.pack('>4I',0,12,15,0)))
        self.assertIsNone(schedule.take(now=30))


if __name__=='__main__':
    unittest.main()
