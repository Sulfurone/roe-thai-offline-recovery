"""Opening deployment lifecycle, without treating synthetic packets as play proof."""
import struct
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from offline_gameplay import OfflineGameplay
from test_ground_loot import request,drop


class OpeningAirDropTests(unittest.TestCase):
    def game(self):
        game=OfflineGameplay(vehicle_config=4,auto_board=True,opening_airdrop=True,
                             aircraft_route_speed=2000,auto_exit_after=40)
        game.vehicle_position=(325800,271700,35000)
        with patch('offline_gameplay.time.monotonic',return_value=100):
            replies=game.board()
        return game,replies

    def test_original_jump_prompt_is_enabled_once_after_boarding_delay(self):
        game,replies=self.game()
        self.assertEqual([m for m,_ in replies],[0x656d,0x6542,0x6564])
        self.assertFalse(game.jump_allowed)
        self.assertNotIn(0x6565,[m for m,_ in game.tick(102.99)])
        self.assertEqual([m for m,_ in game.tick(103)],[0x6565])
        self.assertTrue(game.jump_allowed)
        self.assertEqual(game.deployment_phase,'jump_available')
        self.assertNotIn(0x6565,[m for m,_ in game.tick(104)])

    def test_jump_before_unlock_is_ignored(self):
        game,_=self.game()
        with patch('offline_gameplay.time.monotonic',return_value=102):
            self.assertEqual(game.handle(0x6566,b'\0'),[])
        self.assertTrue(game.seated)
        self.assertEqual(game.vehicle_position,(325800,271700,35000))

    def test_manual_jump_updates_position_before_detaching_and_clears_timer(self):
        game,_=self.game()
        game.tick(103)
        with patch('offline_gameplay.time.monotonic',return_value=106.25):
            replies=game.handle(0x6566,b'\0'+bytes(8))
        self.assertEqual([m for m,_ in replies],[0x6544,0x656d])
        self.assertEqual(struct.unpack_from('>3i',replies[0][1],28),(325980,284200,35120))
        self.assertFalse(game.seated)
        self.assertEqual(game.deployment_phase,'descending')
        self.assertIsNone(game.exit_deadline)
        self.assertIsNotNone(game.route_started)
        self.assertEqual(game.handle(0x6566,b'\0'),[])
        self.assertEqual([m for m,_ in game.tick(107)],[0x6563])
        final=game.tick(140)
        self.assertEqual([m for m,_ in final],[0x6563])
        self.assertEqual(struct.unpack_from('>3i',final[0][1],8),(325800,351700,35000))
        self.assertEqual(struct.unpack_from('>I',final[0][1],33)[0],0)
        self.assertIsNone(game.route_started)
        self.assertEqual(game.tick(160),[])

    def test_route_end_ejects_once_at_the_finite_endpoint(self):
        game,_=self.game()
        replies=game.tick(143)
        self.assertEqual([m for m,_ in replies],[0x6544,0x656d,0x6563])
        self.assertEqual(struct.unpack_from('>3i',replies[0][1],28),(325980,351700,35120))
        self.assertIsNone(game.route_started)
        self.assertIsNone(game.exit_deadline)
        self.assertEqual(game.tick(200),[])

    def test_invalid_opening_configuration_is_rejected(self):
        for kwargs in [dict(),dict(vehicle_config=4,auto_board=True,aircraft_route_speed=2000,auto_exit_after=3),
                       dict(vehicle_config=4,auto_board=True,aircraft_route_speed=3000,auto_exit_after=40),
                       dict(vehicle_config=4,auto_board=True,aircraft_route_speed=2000,auto_exit_after=41)]:
            with self.assertRaises(ValueError):
                OfflineGameplay(opening_airdrop=True,**kwargs)

    def test_cross_map_route_starts_at_west_edge_and_reaches_east_edge(self):
        game=OfflineGameplay(vehicle_config=4,auto_board=True,opening_airdrop=True,
            aircraft_route_speed=5000,auto_exit_after=81.84,aircraft_route_end=(409400,204800,75000))
        game.vehicle_position=(200,204800,75000)
        with patch('offline_gameplay.time.monotonic',return_value=100):
            launch=game.board()[-1][1]
        self.assertEqual(struct.unpack_from('>3i',launch,8),(200,204800,75000))
        self.assertEqual(struct.unpack_from('>3f',launch,21),(1.,0.,0.))
        update=game.tick(101)
        self.assertEqual(struct.unpack_from('>3i',update[0][1],8),(409400,204800,75000))
        game.tick(140.92)
        self.assertEqual(game.vehicle_position,(204800,204800,75000))
        exit_message=game.tick(182)[0][1]
        self.assertEqual(struct.unpack_from('>3i',exit_message,28),(409580,204800,75120))

    def test_cross_map_interpolation_clamps_to_endpoint(self):
        game=OfflineGameplay(aircraft_route_end=(400000,100000,75000),aircraft_route_speed=5000)
        game.route_origin=(0,100000,75000)
        self.assertEqual(game.route_position_at(1000),(400000,100000,75000))
        self.assertEqual(game.route_position_at(-1),(0,100000,75000))
        with self.assertRaises(ValueError):
            OfflineGameplay(aircraft_route_end=(2000000,0,0))

    def test_aircraft_then_ground_arsenal_has_one_spawn_and_persistent_ammo(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'drop-arsenal.json'
            game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,arsenal_enabled=True,
                world_file=path,vehicle_config=4,auto_board=True,opening_airdrop=True,
                aircraft_route_speed=5000,auto_exit_after=81.84,aircraft_route_end=(409400,204800,75000))
            game.vehicle_position=(200,204800,75000)
            with patch('offline_gameplay.time.monotonic',return_value=100):game.board()
            self.assertEqual(game.handle(0x2a,struct.pack('>I3i',1,200,204800,75000)),[])
            self.assertFalse(game.ground_loot.announced)
            game.tick(103)
            with patch('offline_gameplay.time.monotonic',return_value=106):
                self.assertEqual([m for m,_ in game.handle(0x6566,b'\0')],[0x6544,0x656d])
            self.assertFalse(game.seated)
            self.assertEqual(game.handle(0x2a,struct.pack('>I3i',2,30000,204800,50000)),[])
            announced=game.handle(0x2a,struct.pack('>I3i',3,325950,271700,6501))
            self.assertEqual([m for m,_ in announced],[0x821]*26)
            self.assertEqual(game.handle(0x2a,struct.pack('>I3i',4,325950,271700,6501)),[])
            game.handle(0x3e80,drop(1,container=1,slot=1))
            weapon=next(s for s in game.ground_loot.stacks.values() if s.item.template==10202)
            game.handle(0x2a,struct.pack('>I3i',5,*weapon.position))
            self.assertEqual(game.handle(0x3b63,request(weapon.entity))[0][0],0x3e82)
            ammo=next(s for s in game.ground_loot.stacks.values() if s.item.template==30002)
            game.handle(0x2a,struct.pack('>I3i',6,*ammo.position))
            self.assertEqual(game.handle(0x3b63,request(ammo.entity))[0][0],0x3e82)
            game.handle(0x49e,struct.pack('>I',1))
            game.handle(0x49c,struct.pack('>I',1))
            restored=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,world_file=path)
            self.assertEqual((restored.inventory.weapon().template,restored.magazine,
                              restored.inventory.reserve_for(30002)),(10202,30,30))


if __name__=='__main__':
    unittest.main()
