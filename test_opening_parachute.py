"""Aircraft-to-glider handoff and terrain-aware release using synthetic state."""
from array import array
import struct
import unittest
from unittest.mock import patch
from offline_environment import environment_clock
from offline_gameplay import OfflineGameplay
from offline_terrain import TerrainSurface


def spawn(config=3):
    return struct.pack('>QI',999,1)+b'\0'+struct.pack('>III3i',config,0,0,0,0,0)+bytes(5)


class OpeningParachuteTests(unittest.TestCase):
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
        for hour in (-1,24,12.5,True):
            with self.assertRaises(ValueError):environment_clock(hour,1000)

    def test_collision_query_interpolates_bounds_without_inventing_outside_height(self):
        surface=TerrainSurface(2,2,200,200,1,(0,0,6000),array('h',[0,100,200,300]))
        self.assertEqual(surface.height_at(100,100),6150)
        self.assertEqual(surface.height_at(200,200),6300)
        self.assertIsNone(surface.height_at(-1,100))
