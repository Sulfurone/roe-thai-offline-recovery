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
from offline_match_status import room_kill_broadcast, survivor_count
from test_combat import fixture

class Bots:
    def __init__(self):
        self.actors={2:{"position":(2100,1000,7000)},3:{"position":(1000,1000,7000)}}
        self.vitals={2:Vitals(),3:Vitals()}
    def damage(self,uid,amount,*,weapon=0):
        if not self.vitals[uid].damage(amount):return []
        result=[self.vitals[uid].packet(uid)]
        if not self.vitals[uid].current:result.append(death_packet(uid))
        return result

class ZoneDamageTests(unittest.TestCase):
    def test_unloaded_bot_still_sends_native_circle_broadcast_once(self):
        game,bots,_,uid=fixture()
        bots.streamed=True
        bots.vitals[uid].current=10
        x,y,_=game.player_position
        schedule=SimpleNamespace(game=game,circle_at=lambda now:(x,y,150),stage_at=lambda now:(0,),plan=ZonePlan(
            Circle(x,y,200),(ZoneStage(Circle(x,y,150),1,1),)))
        bots.death_notice=lambda victim,killer,weapon,headshot: [
            room_kill_broadcast(killer or 0,b'',victim,b'AI-1',weapon,survivor_count(game,bots))]
        damage=ZoneDamage(schedule,bots)
        self.assertEqual(damage.tick(10),[])
        self.assertEqual(damage.tick(11),[room_kill_broadcast(0,b'',uid,b'AI-1',0,1)])
        self.assertEqual(damage.tick(12),[])

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
    def test_closed_circle_damages_even_at_the_center(self):
        g,b,_,_=self.setup_world()
        schedule=SimpleNamespace(game=g,circle_at=lambda now:(1000,1000,0),stage_at=lambda now:(5,))
        z=ZoneDamage(schedule,b)
        self.assertEqual(z.tick(10),[])
        z.tick(11)
        self.assertEqual((g.vitals.current,b.vitals[3].current),(850,850))

    def test_damage_increases_in_later_rounds(self):
        g,_,_,_=self.setup_world()
        stage=0
        schedule=SimpleNamespace(game=g,circle_at=lambda now:(2000,2000,100),stage_at=lambda now:(stage,),
                                 plan=SimpleNamespace(stages=range(5)))
        z=ZoneDamage(schedule)
        z.tick(10)
        for stage,expected in enumerate((10,20,40,70,100)):
            z.tick(11+stage)
            self.assertEqual(z.events[0]['damage'],expected)
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

    def test_zone_uses_ground_vehicle_position_when_foot_reports_are_paused(self):
        g,b,s,_=self.setup_world()
        g.require_self_position_for_drop=True
        g.seated=True
        control=SimpleNamespace(active_vehicle=123)
        damage=ZoneDamage(s,b,control)
        damage.tick(10)
        g.player_position=(2500,1000,7000)
        damage.tick(11)
        self.assertEqual(g.vitals.current,990)
        control.active_vehicle=None
        damage.tick(12)
        self.assertEqual(g.vitals.current,990)
    def test_server_rejects_damage_without_plan_and_vitals(self):
        import local_server
        for argv in (["local_server.py","--world-zone-damage"],
                     ["local_server.py","--world-zone-damage","--world-zone-plan","example.json"]):
            with patch.object(sys,"argv",argv),contextlib.redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as raised:local_server.main()
                self.assertEqual(raised.exception.code,2)
                self.assertIn("--world-zone-damage requires",error.getvalue())

if __name__=="__main__":unittest.main()
