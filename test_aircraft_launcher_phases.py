import unittest
from pathlib import Path

from probes.prepare_cross_map_airdrop import remove_environment_clock, set_vehicle_push_phase


class AircraftLauncherPhaseTests(unittest.TestCase):
    root = Path(__file__).resolve().parent

    def test_vehicle_push_moves_from_each_supported_phase(self):
        for source in ('load-success', 'map-load', 'player-ready'):
            text = f'--push-after-{source} 0x654b:"vehicle.bin"'
            result = set_vehicle_push_phase(text, 'map-load')
            self.assertEqual(result, '--push-after-map-load 0x654b:"vehicle.bin"')

    def test_vehicle_push_rejects_missing_or_duplicate_spawn(self):
        with self.assertRaises(ValueError):
            set_vehicle_push_phase('no vehicle here', 'map-load')
        with self.assertRaises(ValueError):
            set_vehicle_push_phase(
                '--push-after-load-success 0x654b:a --push-after-player-ready 0x654b:b',
                'map-load')

    def test_aircraft_phase_removes_both_clock_switches(self):
        text = ('server --environment-hour 12 --environment-trigger load '
                '--environment-ready-delay 1 --environment-once --gameplay-prototype')
        self.assertEqual(remove_environment_clock(text), 'server --gameplay-prototype')

    def test_only_day_weather_launcher_adds_player_ready_clock(self):
        stable = (self.root / 'start_offline_parachute.cmd').read_text(encoding='utf-8')
        experimental = (self.root / 'start_offline_day_weather.cmd').read_text(encoding='utf-8')
        self.assertNotIn('--environment-', stable)
        self.assertIn('--environment-hour 12', experimental)
        self.assertIn('--environment-trigger player-ready', experimental)
        self.assertIn('--environment-ready-delay 1', experimental)
        self.assertNotIn('--environment-once', experimental)


if __name__ == '__main__':
    unittest.main()
