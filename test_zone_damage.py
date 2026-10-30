import unittest
import contextlib, io, sys
from unittest.mock import patch
from types import SimpleNamespace
from offline_gameplay import OfflineGameplay
from offline_zones import Circle
from offline_zone_schedule import ZonePlan, ZoneStage, ZoneSchedule
from offline_zone_damage import ZoneDamage
from offline_vitals import Vitals
from offline_combat import death_packet

class Bots:
    def __init__(self):
        self.actors={2:{"position":(2100,1000,7000)},3:{"position":(1000,1000,7000)}}
        self.vitals={2:Vitals(),3:Vitals()}
    def damage(self,uid,amount):
        if not self.vitals[uid].damage(amount):return []
        result=[self.vitals[uid].packet(uid)]
        if not self.vitals[uid].current:result.append(death_packet(uid))
        return result

class ZoneDamageTests(unittest.TestCase):
    def setup_world(self):
        game=OfflineGameplay();game.actor_ready=True;game.player_position=(1000,1000,7000)
        plan=ZonePlan(Circle(1000,1000,1000),(ZoneStage(Circle(1000,1000,500),2,4),))
        schedule=ZoneSchedule(game,SimpleNamespace(height_at=lambda x,y:7000),plan)
        schedule.started=10
        bots=Bots()
        return game,bots,schedule,ZoneDamage(schedule,bots)
    def test_interpolation_and_final_circle_persist(self):
        _,_,s,_=self.setup_world()
        self.assertEqual(s.circle_at(11),(1000,1000,1000))
        self.assertEqual(s.circle_at(14),(1000,1000,750))
        s.finished=True
        self.assertEqual(s.circle_at(30),(1000,1000,500))
    def test_boundary_damage_and_delayed_tick_has_no_burst(self):
        g,b,s,z=self.setup_world()
        self.assertEqual(z.tick(10),[])
        z.tick(11);self.assertEqual((g.vitals.current,b.vitals[2].current,b.vitals[3].current),(1000,990,1000))
        g.player_position=(1750,1000,7000)
        z.tick(14);self.assertEqual(g.vitals.current,1000)  # exactly on boundary
        z.tick(15);self.assertEqual(g.vitals.current,990)
        z.tick(50);self.assertEqual(g.vitals.current,980)
    def test_stale_player_not_damaged_and_death_sent_once(self):
        g,b,s,z=self.setup_world();g.require_self_position_for_drop=True
        g.player_position=(2500,1000,7000);g.vitals.current=10;b.vitals[2].current=10
        z.tick(10);packets=z.tick(11)
        self.assertEqual(g.vitals.current,10)
        self.assertEqual([m for m,_ in packets].count(0x533),1)
        g.accept_self_position(g.player_position,now=12)
        packets=z.tick(12);self.assertEqual(g.vitals.current,0)
        self.assertEqual([m for m,_ in packets].count(0x533),1)
        self.assertEqual(z.tick(13),[])
    def test_server_rejects_damage_without_plan_and_vitals(self):
        import local_server
        for argv in (["local_server.py","--world-zone-damage"],
                     ["local_server.py","--world-zone-damage","--world-zone-plan","example.json"]):
            with patch.object(sys,"argv",argv),contextlib.redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as raised:local_server.main()
                self.assertEqual(raised.exception.code,2)
                self.assertIn("--world-zone-damage requires",error.getvalue())

if __name__=="__main__":unittest.main()
