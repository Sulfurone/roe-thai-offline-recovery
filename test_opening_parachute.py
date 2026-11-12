"""Aircraft-to-glider handoff and terrain-aware release using synthetic state."""
from array import array
import math
import random
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from offline_environment import environment_clock,environment_weather
from offline_gameplay import OfflineGameplay
from offline_motion import aircraft_spawn_heading, random_aircraft_route
from offline_terrain import TerrainSurface


def spawn(config=3):
    return struct.pack('>QI',999,1)+b'\0'+struct.pack('>III3i',config,0,0,0,0,0)+bytes(5)


class OpeningParachuteTests(unittest.TestCase):
    def test_random_flights_use_map_edges_and_matching_spawn_heading(self):
        terrain=SimpleNamespace(height_at=lambda x,y: 9500 if 25000<=x<=385000 and 25000<=y<=385000 else 6000)
        routes=[random_aircraft_route(random.Random(seed),terrain) for seed in range(16)]
        self.assertEqual(routes[0],random_aircraft_route(random.Random(0),terrain))
        self.assertEqual(len({(a,b) for a,b,_ in routes}),16)
        self.assertGreater(len({(axis,point[axis]) for point,_,_ in routes for axis in (0,1)
                                if point[axis] in (200,409400)}),2)
        for start,end,last_jump in routes:
            self.assertTrue(any(x in (200,409400) for x in start[:2]))
            self.assertTrue(any(x in (200,409400) for x in end[:2]))
            self.assertGreater(math.dist(start,end),250000)
            self.assertTrue(.5<=last_jump<=.9)
            body=aircraft_spawn_heading(spawn(4)+bytes(20),end,origin=start)
            self.assertEqual(struct.unpack_from('>3i',body,25),start)
            qz,qw=struct.unpack_from('>2f',body,46)
            length=math.dist(start,end)
            self.assertLess(math.dist((-2*qz*qw,1-2*qz*qz),((end[0]-start[0])/length,(end[1]-start[1])/length)),1e-6)

    def test_aircraft_keeps_flying_after_manual_or_last_dry_point_exit(self):
        for manual in (False,True):
            with self.subTest(manual=manual):
                game=OfflineGameplay(vehicle_config=4,aircraft_route_speed=5000,
                    aircraft_route_end=(180000,409400,75000),aircraft_continue_route=True,auto_exit_after=55)
                game.vehicle_position=(180000,200,75000)
                self.assertIn(0x6565,[mid for mid,_ in game.board(now=100)])
                if manual:
                    with patch('offline_gameplay.time.monotonic',return_value=110):
                        self.assertEqual([mid for mid,_ in game.handle(0x6566,b'\0')],[0x6544,0x656d])
                else:
                    self.assertEqual([mid for mid,_ in game.tick(155)],[0x6544,0x656d])
                    self.assertEqual(game.vehicle_position,(180000,275200,75000))
                self.assertFalse(game.seated)
                self.assertEqual([mid for mid,_ in game.tick(160)],[0x6563])
                [(mid,body)]=game.tick(182)
                self.assertEqual(mid,0x6563)
                self.assertEqual(struct.unpack_from('>3i',body,8),game.aircraft_route_end)
                self.assertEqual(struct.unpack_from('>I',body,33)[0],0)
                self.assertEqual(game.tick(185),[])

    def game(self):
        game=OfflineGameplay(vehicle_config=4,auto_board=True,opening_airdrop=True,
            aircraft_route_speed=5000,auto_exit_after=81.84,
            aircraft_route_end=(409400,204800,75000),opening_glider_body=spawn(),
            landing_height=lambda x,y:6500)
        game.vehicle_position=(200,204800,75000)
        with patch('offline_gameplay.time.monotonic',return_value=100):game.board()
        return game

    def jump(self,game):
        game.tick(103)
        with patch('offline_gameplay.time.monotonic',return_value=110):
            return game.handle(0x6566,b'\0')

    def test_manual_exit_spawns_distinct_canopy_at_current_exit(self):
        game=self.game()
        replies=self.jump(game)
        self.assertEqual([m for m,_ in replies],[0x6544,0x656d,0x654b,0x6554,0x656e,0x656d,0x6542])
        self.assertFalse(game.seated)
        self.assertTrue(game.opening_glider.seated)
        self.assertEqual(game.deployment_phase,'gliding')
        self.assertEqual(game.opening_glider.vehicle_position,(50380,204800,75120))
        self.assertEqual(struct.unpack_from('>Q',replies[2][1])[0],game.vehicle_uid+1)
        self.assertEqual(struct.unpack_from('>I',replies[-1][1],8)[0],3)
        self.assertEqual(game.handle(0x6566,b'\0'),[])
        glider_position=game.opening_glider.vehicle_position
        self.assertEqual([m for m,_ in game.tick(117.99)],[0x6563])
        self.assertTrue(game.opening_glider.seated)
        self.assertEqual([m for m,_ in game.tick(118)],[0x6544,0x656d])
        self.assertFalse(game.opening_glider.seated)
        self.assertEqual(game.deployment_phase,'descending')
        self.assertEqual([m for m,_ in game.tick(120)],[0x6563])
        self.assertEqual(game.vehicle_position,(100200,204800,75000))
        self.assertEqual(game.opening_glider.vehicle_position,glider_position)

    def test_canopy_releases_near_terrain_once_and_returns_to_ground_path(self):
        game=self.game();self.jump(game)
        report=lambda z:struct.pack('>I3i',1,200000,200000,z)
        self.assertEqual(game.handle(0x2a,report(40000)),[])
        self.assertTrue(game.opening_glider.seated)
        self.assertEqual([m for m,_ in game.handle(0x2a,report(6700))],[0x6544,0x656d])
        self.assertFalse(game.opening_glider.seated)
        self.assertEqual(game.deployment_phase,'landing')
        self.assertEqual(game.player_position,(200000,200000,6700))
        self.assertEqual(game.handle(0x2a,report(6500)),[])
        self.assertEqual(game.handle(0x2a,report(6501)),[])
        self.assertEqual(game.handle(0x2a,report(6501)),[])
        self.assertEqual(game.deployment_phase,'landed')
        self.assertEqual(game.handle(0x6566,b'\0'),[])

    def test_forced_exit_also_opens_canopy_and_stops_the_aircraft(self):
        game=self.game()
        replies=game.tick(200)
        self.assertEqual([m for m,_ in replies],[0x6544,0x656d,0x6563,0x654b,0x6554,0x656e,0x656d,0x6542])
        self.assertEqual(struct.unpack_from('>I',replies[2][1],33)[0],0)
        self.assertEqual(game.opening_glider.vehicle_position,(409580,204800,75120))
        self.assertEqual(game.tick(207.99),[])
        self.assertEqual([m for m,_ in game.tick(208)],[0x6544,0x656d])
        self.assertEqual(game.deployment_phase,'descending')
        self.assertEqual(game.tick(210),[])

    def test_bad_canopy_or_early_vehicle_exit_is_rejected(self):
        with self.assertRaises(ValueError):
            OfflineGameplay(opening_glider_body=spawn())
        game=self.game()
        with patch('offline_gameplay.time.monotonic',return_value=101):
            self.assertEqual(game.handle(0x6543,b'\0'),[])
        self.assertTrue(game.seated)
        self.assertIsNone(game.opening_glider)
        game.opening_glider_body=spawn(101)
        with self.assertRaises(ValueError):game.glider_spawn(game.player_position)

    def test_noon_sync_uses_separate_environment_dto(self):
        self.assertEqual(environment_clock(12,1000),(0x4816,struct.pack('>II',12,1000)))
        self.assertEqual(environment_weather(2,30),(0x4817,struct.pack('>4I',0,2,30,0)))
        for hour in (-1,24,12.5,True):
            with self.assertRaises(ValueError):environment_clock(hour,1000)

    def test_collision_query_interpolates_bounds_without_inventing_outside_height(self):
        surface=TerrainSurface(2,2,200,200,1,(0,0,6000),array('h',[0,100,200,300]))
        self.assertEqual(surface.height_at(100,100),6150)
        self.assertEqual(surface.height_at(200,200),6300)
        self.assertIsNone(surface.height_at(-1,100))
