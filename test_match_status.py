import struct
import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from offline_gameplay import OfflineGameplay
from offline_match_status import survivor_number,SurvivorStatus
from offline_vitals import Vitals


class SurvivorStatusTests(unittest.TestCase):
    def test_cli_requires_vitals_and_an_explicit_local_roster(self):
        import local_server
        for extra in ([],['--gameplay-prototype','--gameplay-vitals']):
            stderr=io.StringIO()
            with patch('sys.argv',['local_server.py','--world-survivor-status',*extra]),contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as error:local_server.main()
            self.assertEqual(error.exception.code,2)
            self.assertIn('requires prototype, vitals and an explicit local bot roster',stderr.getvalue())

    def test_codec_and_local_input_bounds(self):
        for count in (0,1,100,1000):
            self.assertEqual(survivor_number(count),(0x47d,struct.pack('>II',count,0)))
        for count in (-1,1001,True,1.,'2'):
            with self.assertRaises(ValueError):survivor_number(count)

    def test_ready_active_roster_spawns_deaths_and_unchanged_suppression(self):
        game=OfflineGameplay()
        bots=SimpleNamespace(actors={11:{},12:{}},vitals={11:Vitals(),12:Vitals()})
        status=SurvivorStatus(game,bots)
        self.assertEqual(status.tick(),[])
        game.actor_ready=True
        self.assertEqual(status.tick(),[survivor_number(3)])
        self.assertEqual(status.tick(),[])
        bots.vitals[11].damage(1000)
        self.assertEqual(status.tick(),[survivor_number(2)])
        bots.actors[13]={};bots.vitals[13]=Vitals()
        self.assertEqual(status.tick(),[survivor_number(3)])
        game.vitals.damage(1000)
        self.assertEqual(status.tick(),[survivor_number(2)])
        bots.vitals[12].damage(1000);bots.vitals[13].damage(1000)
        self.assertEqual(status.tick(),[survivor_number(0)])
        self.assertEqual(status.tick(),[])


if __name__=='__main__':unittest.main()
