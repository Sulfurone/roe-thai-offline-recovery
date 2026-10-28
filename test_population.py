"""Terrain screening, finite world generation and reversible-object messages."""
import struct
import unittest
import random

from control_actions import ControlSession
from offline_gameplay import OfflineGameplay
from offline_population import WorldPopulation
from offline_bots import BotRoster, POSITION_MARKER
from offline_ground_survey import GroundSurvey
from test_control_panel import ready_game, jeep_template


class Surface:
    def height_at(self, x, y):
        return 7000


class PopulationTests(unittest.TestCase):
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
        self.assertEqual([m for m, _ in spawned], [0x565, 0xbe7, 0x27] * 2)
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
        self.assertLessEqual(len(game.ground_loot.stacks), 112)
        self.assertEqual(population.auto_vehicles, 12)
        self.assertLess(len(population.visited), 40)

    def test_denser_default_loot_can_be_picked_with_live_camera_after_walking(self):
        game=ready_game()
        game.player_position=(100000,200000,7250)
        population=WorldPopulation(ControlSession(game),Surface(),42,vehicles=False)
        messages=population.tick()
        self.assertEqual([m for m,_ in messages],[0x821]*16)
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
