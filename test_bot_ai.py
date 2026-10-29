import math
from pathlib import Path
from types import SimpleNamespace
import struct
import tempfile
import unittest
from unittest.mock import patch
from offline_bot_ai import BotAI
from offline_peer_messages import peer_equipment,peer_fire
from offline_visibility import StaticVisibility
from test_combat import fixture
from control_actions import ControlSession
from offline_bots import BotRoster,POSITION_MARKER
from offline_population import WorldPopulation


class Flat:
    def height_at(self,x,y):return 6500


def setup():
    game,bots,combat,uid=fixture()
    visibility=StaticVisibility(Flat(),[])
    ai=BotAI(game,bots,SimpleNamespace(terrain=Flat()),visibility)
    ai.WARMUP=ai.EQUIP_DELAY=0
    game.accept_self_position((325800,271700,6505),100)
    return game,bots,ai,uid


class PeerMessageTests(unittest.TestCase):
    def test_remote_equipment_and_fire_use_distinct_messages_and_quantities(self):
        message,body=peer_equipment(256,300,magazine=29)
        self.assertEqual(message,0x547)
        self.assertEqual(len(body),86)
        self.assertEqual(struct.unpack_from('>QI',body),(256,1))
        self.assertEqual(struct.unpack_from('>IQIBI',body,12),(10201,300,1,0,1))
        self.assertEqual(struct.unpack_from('>3I',body,33),(7,30001,29))
        self.assertEqual(peer_fire(256,(1,2,3),(10,20,30)),(0x11d4,struct.pack('>Q6fB',256,1,2,3,10,20,30,0)))
        self.assertEqual(peer_fire(256,(1,2,3),(10,20,30),True)[1][-1],1)
        for values in ((0,300),(256,0)):
            with self.assertRaises(ValueError):peer_equipment(*values)
        with self.assertRaises(ValueError):peer_equipment(256,300,magazine=31)
        with self.assertRaises(ValueError):peer_fire(256,(math.nan,2,3),(10,20,30))


class VisibilityTests(unittest.TestCase):
    def test_static_spheres_block_crossing_inside_and_cross_cell_segments(self):
        data=StaticVisibility(Flat(),[(10000,10000,6600,500)])
        self.assertFalse(data.clear((9000,10000,6600),(11000,10000,6600)))
        self.assertFalse(data.clear((10000,10000,6600),(11000,10000,6600)))
        self.assertTrue(data.clear((9000,12000,6600),(11000,12000,6600)))
        self.assertIsNone(data.walk((9000,10000,6505),(11000,10000,6505)))

    def test_terrain_unknown_height_cliffs_and_nonfinite_input_are_blocked(self):
        class Hill:
            def height_at(self,x,y):return 6700 if 200<x<400 else 6500
        data=StaticVisibility(Hill(),[])
        self.assertFalse(data.clear((0,0,6600),(600,0,6600)))
        self.assertIsNone(data.walk((0,0,6505),(600,0,6505)))
        self.assertIsNone(data.walk((math.nan,0,6505),(600,0,6505)))
        self.assertFalse(data.clear((0,0,math.inf),(600,0,6600)))
        self.assertEqual(StaticVisibility(Flat(),[]).walk((0,0,6505),(100,0,6505)),(100,0,6505))
        class Unknown:
            def height_at(self,x,y):return None
        self.assertFalse(StaticVisibility(Unknown(),[]).clear((0,0,6600),(600,0,6600)))

    def test_own_scene_schema_and_complete_bounded_spheres_are_required(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'scene.xml'
            path.write_text('<r ObjName="x.eu_killzone_2048.ClientTable.RigidStaticInPxScene">'
                '<mItems mID="1" mBoundingX="10000" mBoundingY="10000" mBoundingZ="6600" mBoundingRadius="500"/>'
                '</r>',encoding='utf8')
            data=StaticVisibility.from_scene(Flat(),path)
            self.assertEqual(len(data.bounds),1)
            path.write_text('<r ObjName="other"><mItems mID="1"/></r>',encoding='utf8')
            with self.assertRaises(ValueError):StaticVisibility.from_scene(Flat(),path)


class BotAITests(unittest.TestCase):
    def test_missing_spawn_retries_in_same_cell_after_cooldown(self):
        game,bots,ai,uid=setup()
        bots.actors.clear();bots.vitals.clear()
        population=WorldPopulation(ControlSession(game),Flat(),bots=bots,loot=False,vehicles=False)
        with patch.object(population,'choose_spot',side_effect=[None,(326000,271700,6505)]) as chosen:
            with patch('time.monotonic',return_value=100):self.assertEqual(population.tick(),[])
            with patch('time.monotonic',return_value=101):self.assertEqual(population.tick(),[])
            with patch('time.monotonic',return_value=103):
                self.assertEqual([m for m,b in population.tick()],[0x565,0xbe7,0x1069,0x27])
            self.assertEqual(chosen.call_count,2)
            self.assertEqual(len(population.visited),1)

    def test_partial_roster_fills_missing_uid_without_reanimating_dead_peer(self):
        game,_,_,_=setup()
        profile=struct.pack('>IIQI',3,1,1,12)+b'OfflineBot1\0'+POSITION_MARKER
        bots=BotRoster(profile,2)
        population=WorldPopulation(ControlSession(game),Flat(),bots=bots,loot=False,vehicles=False)
        with patch.object(population,'choose_spot',side_effect=[(326000,271700,6505),None]):
            with patch('time.monotonic',return_value=100):bots.spawn(population,game.player_position,None)
        first=next(iter(bots.actors));bots.vitals[first].damage(1000)
        with patch.object(population,'choose_spot',return_value=(327000,271700,6505)):
            with patch('time.monotonic',return_value=110):
                self.assertEqual([m for m,b in bots.spawn(population,game.player_position,None)],[0x565,0xbe7,0x1069,0x27])
        second=max(bots.actors)
        self.assertEqual((bots.vitals[first].current,bots.vitals[second].current),(0,1000))
        retried=bots.tick(population,111)
        self.assertTrue(any(m==0xbe7 and struct.unpack_from('>Q',b,8)[0]==second for m,b in retried))
        self.assertEqual(bots.actors[second]['retry'],1)
        self.assertEqual(bots.vitals[first].current,0)

    def test_arm_react_fire_stop_damage_and_death_use_native_messages(self):
        game,bots,ai,uid=setup()
        game.vitals.current=20
        game.medicine.pending=dict(uid=999,template=70001,deadline=104)
        self.assertEqual([m for m,b in ai.tick(100)],[0x547])
        game.accept_self_position(game.player_position,100.8)
        packets=ai.tick(100.8)
        self.assertEqual([m for m,b in packets],[0x11d4,0x11d4,0x1069,0x11eb,0x533])
        self.assertEqual(game.vitals.current,0)
        self.assertIsNone(game.medicine.pending)
        self.assertEqual(ai.brains[uid].magazine,29)
        self.assertEqual(ai.tick(101),[])
        self.assertEqual(ai.brains[uid].phase,'waiting')
        before=game.magazine
        game.handle(0x11d3,struct.pack('>6fIB',325800,271700,6600,327000,271700,6600,0,0))
        self.assertEqual(game.magazine,before)
        self.assertEqual(game.handle(0x49c,struct.pack('>I',1)),[(0x49d,struct.pack('>II',1,1))])
        control=ControlSession(game)
        self.assertFalse(control.snapshot()['ready'])
        with self.assertRaisesRegex(ValueError,'死亡'):
            control.execute(dict(action='weather',weather_id=2,transition=0))

    def test_lateral_movement_can_dodge_and_moving_along_the_ray_does_not(self):
        for lateral in (True,False):
            game,bots,ai,uid=setup()
            ai.tick(100)
            game.accept_self_position((325800 if lateral else 325950,271900 if lateral else 271700,6505),100.8)
            packets=ai.tick(100.8)
            self.assertEqual([m for m,b in packets][:2],[0x11d4,0x11d4])
            self.assertEqual(game.vitals.current,1000 if lateral else 980)

    def test_stale_air_seated_dead_targets_and_obstruction_prevent_attacks(self):
        for reason in ('stale','air','seated','dead','wall'):
            game,bots,ai,uid=setup()
            ai.tick(100)
            if reason=='air':game.accept_self_position((325800,271700,75000),100.8)
            elif reason!='stale':game.accept_self_position(game.player_position,100.8)
            if reason=='seated':game.seated=True
            if reason=='dead':game.vitals.current=0
            if reason=='wall':ai.visibility=StaticVisibility(Flat(),[(325900,271700,6600,100)])
            before=game.vitals.current
            packets=ai.tick(102 if reason=='stale' else 100.8)
            self.assertNotIn(0x11d4,[m for m,b in packets])
            self.assertEqual(game.vitals.current,before)

    def test_reload_conserves_limited_reserve_and_dead_bot_never_fires(self):
        game,bots,ai,uid=setup()
        ai.tick(100)
        brain=ai.brains[uid]
        brain.magazine=0;brain.reserve=2
        ai.tick(100.1)
        self.assertEqual(brain.phase,'reload')
        game.accept_self_position(game.player_position,103)
        self.assertEqual(ai.tick(103),[])
        game.accept_self_position(game.player_position,103.1)
        self.assertEqual([m for m,b in ai.tick(103.1)],[0x547])
        self.assertEqual((brain.magazine,brain.reserve),(2,0))
        bots.vitals[uid].current=0
        self.assertEqual(ai.tick(103.2),[])
        self.assertEqual(brain.phase,'dead')

    def test_chase_steps_are_bounded_and_static_blockers_stop_walks(self):
        game,bots,ai,uid=setup()
        bots.actors[uid]['position']=(334300,271700,6505)
        ai.tick(100)
        game.accept_self_position(game.player_position,100.5)
        packets=ai.tick(100.5)
        self.assertEqual([m for m,b in packets],[0x27])
        self.assertLessEqual(math.dist(bots.actors[uid]['position'],(334300,271700,6505)),111)
        before=bots.actors[uid]['position']
        ai.visibility=StaticVisibility(Flat(),[(*before[:2],before[2]+100,1000)])
        game.accept_self_position(game.player_position,100.9)
        self.assertEqual(ai.tick(100.9),[])
        self.assertEqual(bots.actors[uid]['position'],before)


if __name__=='__main__':unittest.main()
