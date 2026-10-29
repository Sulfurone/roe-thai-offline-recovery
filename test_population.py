"""Terrain screening, finite world generation and reversible-object messages."""
import struct
import unittest
import random

from control_actions import ControlSession
from offline_gameplay import OfflineGameplay
from offline_population import WorldPopulation
from offline_bots import BotRoster, POSITION_MARKER
from offline_ground_survey import GroundSurvey
from offline_items import EXTRA_ITEMS
from test_control_panel import ready_game, jeep_template


class Surface:
    def height_at(self, x, y):
        return 7000


class PopulationTests(unittest.TestCase):
    def test_sparse_house_floor_keeps_medicine_armor_optics_and_other_categories(self):
        class Sparse(Surface):
            used=False
            def spawn_spot(self,position,rng,kind,occupied):
                if self.used:return None
                self.used=True
                return 100100,200100,7010
        game=ready_game()
        game.player_position=(100000,200000,7250)
        population=WorldPopulation(ControlSession(game),Sparse(),extra_items=True,vehicles=False)
        population.tick()
        generated=[s for entity,s in game.ground_loot.stacks.items() if entity in population.auto_item_ids]
        self.assertEqual(len(generated),26)
        extras=[s for s in generated if s.item.template in EXTRA_ITEMS]
        self.assertEqual(len(extras),24)
        for predicate in (lambda v:v.slot==11,lambda v:v.kind==5,lambda v:v.kind==4,
                          lambda v:v.kind==7,lambda v:v.slot==10,lambda v:v.slot==12):
            self.assertEqual(sum(predicate(EXTRA_ITEMS[s.item.template]) for s in extras),4)
        self.assertIn(40305,[s.item.template for s in extras])
        self.assertTrue(all(s.position[2]==7010 and ((s.position[0]-100100)**2+(s.position[1]-200100)**2)**.5<=46 for s in extras))

    def test_client_ground_survey_rejects_air_and_distant_height_claims(self):
        surface = GroundSurvey()
        surface.observe((100000, 200000, 75000))
        surface.observe((100010, 200000, 74800))
        self.assertEqual(surface.points, [])
        surface.observe((100000, 200000, 20000), 2)
        surface.observe((100100, 200000, 20010), 0)
        self.assertEqual(surface.height_at(100100, 200000), 20010)
        self.assertIsNone(surface.height_at(110000, 200000))
        game = ready_game()
        control = ControlSession(game, jeep_template())
        population = WorldPopulation(control, surface, 5)
        game.player_position = (100100, 200000, 20010)
        messages = population.tick()
        self.assertTrue(any(m == 0x821 for m, _ in messages))
        self.assertTrue(any(m == 0x654b for m, _ in messages))
        self.assertTrue(all(abs(s.position[2] - 20040) < 5 for s in list(game.ground_loot.stacks.values())[1:]))

    def test_peer_roster_queries_and_terrain_patrol(self):
        profile = struct.pack('>IIQI', 3, 1, 1, 12) + b'OfflineBot1\0' + POSITION_MARKER
        bots = BotRoster(profile, 2)
        population = WorldPopulation(ControlSession(ready_game()), Surface(), bots=bots)
        spawned = bots.spawn(population, (100000, 200000, 7250), random.Random(1))
        self.assertEqual([m for m, _ in spawned], [0x565, 0xbe7, 0x1069, 0x27] * 2)
        self.assertEqual(len(bots.actors), 2)
        self.assertEqual(bots.spawn(population, (100000, 200000, 7250), random.Random(1)), [])
        for uid in bots.actors:
            reply = bots.handle(0xbe6, struct.pack('>IIQ', 2, 1, uid))
            self.assertEqual(struct.unpack_from('>II',reply[0][1]),(3,1))
            self.assertEqual(struct.unpack_from('>Q', reply[0][1], 8)[0], uid)
            self.assertEqual(struct.unpack_from('>3i',reply[0][1],bots.position_offset),bots.actors[uid]['position'])
        moved = bots.tick(population, bots.started + 1)
        self.assertEqual(len([1 for m,b in moved if m == 0x27 and len(b) == 36]), 2)
        self.assertEqual([m for m,b in moved].count(0xbe7), 2)
        self.assertEqual(bots.tick(population, bots.started + 1.1), [])
        self.assertEqual(bots.handle(0xbe6, b''), None)

    def test_peer_health_is_per_actor_and_profile_retries_do_not_refill(self):
        profile=struct.pack('>IIQI',3,1,1,12)+b'OfflineBot1\0'+POSITION_MARKER
        bots=BotRoster(profile)
        population=WorldPopulation(ControlSession(ready_game()),Surface(),bots=bots)
        bots.spawn(population,(100000,200000,7250),random.Random(1))
        uid=next(iter(bots.actors))
        bots.vitals[uid].damage(125)
        retried=bots.tick(population,bots.started+1)
        self.assertEqual([b for m,b in retried if m==0x1069],[bots.vitals[uid].packet(uid)[1]])
        self.assertEqual(struct.unpack_from('>II',bots.vitals[uid].packet(uid)[1],11),(875,1000))
        self.assertEqual(bots.handle(0xbe6,struct.pack('>IIQ',2,1,uid))[-1],bots.vitals[uid].packet(uid))

    def test_door_open_close_retries_and_bad_inputs(self):
        game = OfflineGameplay(door_interactions=True)
        for state in (1, 2, 0, 0):
            packets = game.handle(0x6f57, struct.pack('>II', 17415, state))
            self.assertEqual(packets, [(0x6f55, struct.pack('>5I', 17415, state, 1, 0, 0))])
        before = dict(game.doors.states)
        for body in (b'', bytes(7), bytes(9), struct.pack('>II', 0, 1), struct.pack('>II', 2, 3)):
            self.assertEqual(game.handle(0x6f57, body), [])
        self.assertEqual(game.doors.states, before)
        self.assertEqual(OfflineGameplay().handle(0x6f57, struct.pack('>II', 17415, 1)), [])

    def test_population_uses_terrain_unique_ids_and_shared_vehicle_routing(self):
        game = ready_game()
        game.player_position = (100000, 200000, 7250)
        control = ControlSession(game, jeep_template())
        population = WorldPopulation(control, Surface(), 42,clusters=3,vehicle_clusters=1)
        messages = population.tick()
        self.assertEqual([m for m, _ in messages], [0x821]*6 + [0x654b, 0x6554, 0x656e])
        self.assertEqual(population.tick(), [])
        car = next(iter(control.vehicles.values()))
        self.assertEqual(car.vehicle_position[2], 7100)
        game.player_position = car.vehicle_position
        boarded = control.handle(0x6541, struct.pack('>QI', car.vehicle_uid, 1))
        self.assertTrue(any(m == 0x6542 for m, _ in boarded))
        self.assertTrue(game.seated)
        self.assertEqual(population.tick(), [])
        self.assertEqual(len({s.item.uid for s in game.ground_loot.stacks.values()}), len(game.ground_loot.stacks))

    def test_airborne_water_steep_ground_and_caps(self):
        game = ready_game()
        control = ControlSession(game, jeep_template())
        population = WorldPopulation(control, Surface())
        self.assertEqual(population.tick(), [])  # below this synthetic surface
        game.player_position = (100000, 200000, 75000)
        self.assertEqual(population.tick(), [])
        for value in (None, float('nan'), 0):
            population.terrain = type('BadSurface', (), {'height_at': lambda self, x, y: value})()
            self.assertIsNone(population.surface(100000, 200000))
        population.terrain = type('Slope', (), {'height_at': lambda self, x, y: x})()
        self.assertIsNone(population.surface(100000, 200000))
        population.terrain = type('FlatRoundoff', (), {'height_at': lambda self, x, y: 6500 - 1e-9})()
        self.assertEqual(population.surface(100000, 200000), 6500)
        population.terrain = Surface()
        for index in range(40):
            game.player_position = (100000 + index * 5000, 200000, 7250)
            population.tick()
        self.assertLessEqual(len(game.ground_loot.stacks), WorldPopulation.AUTO_GROUND_CAP)
        self.assertLessEqual(population.auto_vehicles, 12)
        self.assertLess(len(population.visited), 40)

    def test_streaming_reclaims_far_automatic_objects_and_keeps_spawning(self):
        game=ready_game()
        control=ControlSession(game,jeep_template())
        population=WorldPopulation(control,Surface(),42,extra_items=True)
        all_uids=set()
        saw_removals=False
        for x in range(30000,390000,30000):
            game.player_position=(x,200000,7250)
            before=set(control.vehicles)
            packets=population.tick()
            self.assertIn(0x821,[m for m,_ in packets])
            added=set(control.vehicles)-before
            self.assertFalse(added & all_uids)
            all_uids.update(added)
            saw_removals|=any(m==0x654c for m,_ in packets)
            self.assertLessEqual(len(game.ground_loot.stacks),WorldPopulation.AUTO_GROUND_CAP)
            self.assertLessEqual(len(control.vehicles),12)
            self.assertLess(len(population.spots),400)
        self.assertTrue(saw_removals)
        self.assertGreater(len(all_uids),12)

    def test_unloaded_region_revisits_and_common_optic_is_attempted(self):
        game=ready_game()
        population=WorldPopulation(ControlSession(game),Surface(),42,vehicles=False,extra_items=True)
        first=(100000,200000,7250)
        game.player_position=first
        population.tick()
        first_ids=set(population.auto_item_ids)
        self.assertTrue(any(s.item.template in (40303,40304,40305) for s in game.ground_loot.stacks.values()))
        game.player_position=(300000,200000,7250)
        population.tick()
        self.assertFalse(first_ids & set(game.ground_loot.stacks))
        game.player_position=first
        packets=population.tick()
        self.assertIn(0x821,[m for m,_ in packets])
        self.assertTrue(all(uid not in first_ids for uid in population.auto_item_ids))

    def test_streaming_preserves_manual_loot_and_current_car_while_driving(self):
        game=ready_game()
        control=ControlSession(game,jeep_template())
        population=WorldPopulation(control,Surface(),42,extra_items=True)
        game.player_position=(100000,200000,7250)
        population.tick()
        manual=game.ground_loot.stacks[0x400001]
        driver=next(iter(control.vehicles))
        control.active_vehicle=driver
        control.vehicles[driver].seated=True
        game.seated=True
        game.player_position=(300000,200000,7250)
        packets=population.tick()
        self.assertIn(0x821,[m for m,_ in packets])
        self.assertIn(driver,control.vehicles)
        self.assertEqual(game.ground_loot.stacks[manual.entity],manual)
        self.assertNotIn((0x654c,struct.pack('>Q',driver)),packets)

    def test_vehicle_allocator_never_reuses_a_retired_car_uid(self):
        game=ready_game()
        control=ControlSession(game,jeep_template())
        for _ in range(3):control.spawn_vehicle(game.player_position)
        previous=set(control.vehicles)
        del control.vehicles[min(previous)]
        control.spawn_vehicle(game.player_position)
        self.assertEqual(len(control.vehicles),3)
        self.assertGreater(max(control.vehicles),max(previous))

    def test_denser_default_loot_can_be_picked_with_live_camera_after_walking(self):
        game=ready_game()
        game.player_position=(100000,200000,7250)
        population=WorldPopulation(ControlSession(game),Surface(),42,vehicles=False)
        messages=population.tick()
        self.assertEqual([m for m,_ in messages],[0x821]*32)
        ammo=next(stack for stack in game.ground_loot.stacks.values()
                  if stack.entity!=0x400001 and stack.item.kind==3)
        before=sum(item.count for item in game.inventory.items.values() if item.kind==3)
        body=struct.pack('>IIQBHB3iB',ammo.entity,0,0,0,0,1,
                         ammo.position[0],ammo.position[1],ammo.position[2]+137,0)
        replies=game.handle(0x3b63,body)
        self.assertEqual([m for m,_ in replies],[0x3e82,0x82b,0x3b64])
        self.assertNotIn(ammo.entity,game.ground_loot.stacks)
        self.assertEqual(sum(item.count for item in game.inventory.items.values() if item.kind==3),
                         before+ammo.item.count)
        self.assertEqual(game.player_position,(100000,200000,7250))


if __name__ == '__main__':
    unittest.main()
