import json
import contextlib
import io
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from offline_gameplay import OfflineGameplay
from offline_zones import Circle
from offline_zone_schedule import ZonePlan,ZoneStage,ZoneSchedule


def plan():
    return ZonePlan(Circle(200000,200000,150000),
        (ZoneStage(Circle(205000,200000,100000),10,20),
         ZoneStage(Circle(210000,200000,50000),5,10)))


def schedule():
    game=OfflineGameplay();game.actor_ready=True;game.player_position=(200000,200000,6501)
    return ZoneSchedule(game,SimpleNamespace(height_at=lambda x,y:6500),plan())


class ZoneScheduleTests(unittest.TestCase):
    def test_ground_readiness_wait_shrink_skip_and_final_snapshot(self):
        pacing=schedule()
        pacing.game.seated=True
        self.assertEqual(pacing.tick(0),[])
        pacing.game.seated=False;pacing.game.player_position=(200000,200000,75000)
        self.assertEqual(pacing.tick(1),[])
        pacing.game.player_position=(200000,200000,6501)
        self.assertEqual(pacing.tick(2),[])
        self.assertEqual(pacing.tick(4.99),[])
        def state(now):
            packets=pacing.tick(now)
            self.assertEqual([m for m,_ in packets],[0x47b])
            return struct.unpack('>IfIiifiif',packets[0][1])
        self.assertEqual(state(5)[:3],(0,0.,10))
        self.assertEqual(pacing.tick(5.5),[])
        self.assertEqual(state(15)[:3],(2,0.,20))
        self.assertEqual(state(25)[:3],(2,10.,20))
        # A delayed loop sends the current state, not obsolete phase packets.
        self.assertEqual(state(42)[:3],(2,2.,10))
        self.assertEqual(pacing.last_event['stage'],1)
        final=state(50)
        self.assertEqual(final[:3],(0,0.,1))
        self.assertEqual(final[3:6],final[6:9])
        self.assertEqual(pacing.tick(60),[])
        self.assertTrue(pacing.finished)

    def test_stale_water_dead_and_interrupted_ground_readiness_do_not_arm(self):
        pacing=schedule();game=pacing.game
        self.assertEqual(pacing.tick(0),[])
        game.seated=True;self.assertEqual(pacing.tick(2),[])
        game.seated=False;self.assertEqual(pacing.tick(3),[])
        self.assertEqual(pacing.tick(5),[])
        self.assertIsNone(pacing.started)
        game.require_self_position_for_drop=True
        self.assertEqual(pacing.tick(6),[])
        game.accept_self_position(game.player_position,now=7)
        self.assertEqual(pacing.tick(7),[])
        game.vitals.damage(1000)
        self.assertEqual(pacing.tick(10),[])
        self.assertIsNone(pacing.started)
        pacing=schedule();pacing.terrain.height_at=lambda x,y:6400
        self.assertEqual(pacing.tick(100),[])

    def test_interpolation_roundoff_does_not_block_dry_ground(self):
        pacing=schedule();pacing.terrain.height_at=lambda x,y:6499.999999999999
        self.assertEqual(pacing.tick(0),[])
        self.assertEqual(len(pacing.tick(3)),1)
        pacing=schedule();pacing.terrain.height_at=lambda x,y:6499.99
        self.assertEqual(pacing.tick(0),[])
        self.assertEqual(pacing.tick(3),[])

    def test_plan_schema_bounds_and_strictly_contained_shrinking_circles(self):
        data=dict(version=1,initial=dict(x=200000,y=200000,radius=150000),
                  stages=[dict(target=dict(x=205000,y=200000,radius=100000),wait=10,shrink=20)])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'plan.json';path.write_text(json.dumps(data),encoding='utf8')
            self.assertEqual(ZonePlan.read(path),ZonePlan(plan().initial,plan().stages[:1]))
            for change in ('unknown','bool','outside','same','time','oversize'):
                broken=json.loads(json.dumps(data))
                if change=='unknown':broken['command']='ignored?'
                if change=='bool':broken['version']=True
                if change=='outside':broken['stages'][0]['target']['x']=400000
                if change=='same':broken['stages'][0]['target']=broken['initial']
                if change=='time':broken['stages'][0]['wait']=0
                if change=='oversize':broken['stages']*=21
                path.write_text(json.dumps(broken),encoding='utf8')
                with self.assertRaises(ValueError):ZonePlan.read(path)
            path.write_text(' '*16385,encoding='utf8')
            with self.assertRaises(ValueError):ZonePlan.read(path)
            import local_server
            for argv,expected in ((['local_server.py','--world-zone-plan',str(path)],'requires'),
                (['local_server.py','--world-zone-plan',str(path),'--gameplay-prototype',
                  '--world-populate','--gameplay-inventory','--gameplay-ground-loot',
                  '--world-client-ground'],'Cannot prepare local circle plan')):
                stderr=io.StringIO()
                with patch('sys.argv',argv),contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as error:local_server.main()
                self.assertEqual(error.exception.code,2)
                self.assertIn(expected,stderr.getvalue())


if __name__=='__main__':unittest.main()
