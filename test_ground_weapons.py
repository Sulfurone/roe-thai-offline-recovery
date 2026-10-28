import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from offline_gameplay import OfflineGameplay
from offline_inventory import Item,WEAPON_TEMPLATE
from offline_world_state import restore,snapshot
from test_ground_loot import request,drop


class GroundWeaponTests(unittest.TestCase):
    def ready(self,path=None):
        game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,world_file=path,magazine=28)
        game.handle(0x2a,struct.pack('>I3i',1,325800,271700,6488))
        return game

    def test_drop_and_pickup_primary_preserve_weapon_uid_and_loaded_rounds(self):
        game=self.ready()
        weapon=game.inventory.items[1,1]
        replies=game.handle(0x3e80,drop(1,container=1,slot=1))
        self.assertEqual([m for m,_ in replies],[0x821,0x3e82,0x3e81])
        self.assertNotIn(0x4a0,dict(replies))
        self.assertEqual((game.magazine,game.selected_slot),(0,0))
        stack=game.ground_loot.stacks[0x400002]
        self.assertEqual((stack.item,stack.magazine),(weapon,28))
        self.assertEqual(game.handle(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,1,0)),[])
        replies=game.handle(0x3b63,request(stack.entity))
        self.assertEqual([m for m,_ in replies],[0x3e82,0x82b,0x3b64])
        self.assertEqual(struct.unpack('>IIBIII',replies[2][1]),(stack.entity,0,1,10201,1,0))
        self.assertEqual(game.inventory.weapon_magazines[weapon.uid],28)
        self.assertEqual(game.inventory.items[1,1],weapon)
        game.handle(0x49e,struct.pack('>I',1))
        game.handle(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,2,0))
        self.assertEqual((game.magazine,game.reserve),(27,120))

    def test_pickup_into_bag_then_equip_second_slot_preserves_rounds(self):
        game=self.ready()
        game.handle(0x3e80,drop(1,container=1,slot=1))
        replies=game.handle(0x3b63,request(0x400002,container=2,destination=8,automatic=0))
        self.assertEqual([m for m,_ in replies],[0x3e82,0x82b,0x3b64])
        # A bagged gun is not carried; the live magazine stays empty until
        # it is equipped, but its rounds stay recorded on the gun.
        self.assertEqual(game.magazine,0)
        self.assertEqual(list(game.inventory.weapon_magazines.values()),[28])
        self.assertIsNone(game.inventory.weapon_slot())
        replies=game.handle(0x3e80,struct.pack('>BBHBHHB',1,2,8,1,2,1,1))
        self.assertNotIn(0x4a0,dict(replies))
        self.assertEqual(game.inventory.weapon_magazines[game.inventory.items[1,2].uid],28)
        game.handle(0x3e80,struct.pack('>BBHBHHB',1,1,2,2,9,1,1))
        game.handle(0x3e80,drop(1,container=2,slot=9))
        self.assertEqual(game.ground_loot.stacks[0x400003].magazine,28)
        self.assertEqual(game.magazine,0)

    def test_occupied_requested_slot_rejects_without_losing_gun(self):
        game=self.ready()
        game.handle(0x3e80,drop(1,container=1,slot=1))
        before=game.state_payload()
        replies=game.handle(0x3b63,request(0x400002,container=2,destination=0,automatic=0))
        self.assertEqual(replies[0][0],0x3b66)
        self.assertEqual(game.state_payload(),before)
        # An explicitly occupied weapon slot is never displaced.
        game.inventory.items[1,2]=Item(1,WEAPON_TEMPLATE,0x100111,1)
        self.assertEqual(game.handle(0x3b63,request(0x400002,container=1,destination=2,automatic=0))[0][0],0x3b66)
        self.assertIn(0x400002,game.ground_loot.stacks)
        # The dropped M4A1 returns to the free long-gun slot.
        self.assertEqual(game.handle(0x3b63,request(0x400002))[0][0],0x3e82)
        self.assertEqual(game.inventory.items[1,1].uid,0x100101)
        # Automatic pickup of a third long gun stores it in the bag instead.
        third=game.ground_loot.add(Item(1,10202,0x100121,1),game.player_position)
        self.assertEqual(game.handle(0x3b63,request(third.entity))[0][0],0x3e82)
        self.assertNotIn(third.entity,game.ground_loot.stacks)
        self.assertEqual(game.inventory.items[2,1].uid,0x100121)

    def test_second_long_gun_keeps_independent_magazine_across_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'world.json'
            game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,arsenal_enabled=True,
                                 world_file=path,magazine=28)
            game.handle(0x2a,struct.pack('>I3i',1,325800,271700,6488))
            second=next(s for s in game.ground_loot.stacks.values() if s.item.template==10202)
            game.handle(0x2a,struct.pack('>I3i',1,*second.position))
            self.assertEqual(game.handle(0x3b63,request(second.entity))[0][0],0x3e82)
            self.assertEqual(game.inventory.items[1,2],second.item)
            game.handle(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,1,0))
            game.handle(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,2,0))
            self.assertEqual(game.magazine,26)
            game.handle(0x49e,struct.pack('>I',2))
            self.assertEqual(game.magazine,0)
            ammo=next(s for s in game.ground_loot.stacks.values() if s.item.template==30002)
            game.handle(0x2a,struct.pack('>I3i',1,*ammo.position))
            self.assertEqual(game.handle(0x3b63,request(ammo.entity))[0][0],0x3e82)
            game.handle(0x49c,struct.pack('>I',2))
            self.assertEqual((game.magazine,game.reserve),(30,150))
            game.handle(0x49e,struct.pack('>I',1))
            self.assertEqual(game.magazine,26)
            reopened=self.ready(path)
            self.assertEqual((reopened.magazine,reopened.selected_slot),(26,1))
            reopened.handle(0x49e,struct.pack('>I',2))
            self.assertEqual(reopened.magazine,30)

    def test_weapon_on_ground_survives_restart_then_equips_same_magazine(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'world.json'
            game=self.ready(path)
            game.handle(0x3e80,drop(1,container=1,slot=1))
            reopened=self.ready(path)
            self.assertEqual((reopened.magazine,reopened.selected_slot),(0,0))
            self.assertEqual(reopened.ground_loot.stacks[0x400002].magazine,28)
            reopened.handle(0x3b63,request(0x400002,container=1,destination=2,automatic=0))
            again=self.ready(path)
            self.assertEqual((again.magazine,again.inventory.weapon_slot()),(28,2))
            self.assertEqual(set(again.ground_loot.stacks),{0x400001})

    def test_failed_weapon_commit_keeps_same_gun_and_loaded_rounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'world.json'
            game=self.ready(path)
            before=path.read_bytes()
            with patch('offline_world_state.write_atomic',side_effect=OSError('test failure')):
                with self.assertRaises(OSError):game.handle(0x3e80,drop(1,container=1,slot=1))
            self.assertEqual(game.magazine,28)
            self.assertEqual(game.inventory.weapon_slot(),1)
            self.assertEqual(path.read_bytes(),before)
            game.handle(0x3e80,drop(1,container=1,slot=1))
            before=path.read_bytes()
            with patch('offline_world_state.write_atomic',side_effect=OSError('test failure')):
                with self.assertRaises(OSError):game.handle(0x3b63,request(0x400002))
            self.assertEqual(game.magazine,0)
            self.assertEqual(game.ground_loot.stacks[0x400002].magazine,28)
            self.assertEqual(path.read_bytes(),before)

    def test_v1_ammunition_world_migrates_and_invalid_weapon_metadata_fails(self):
        game=self.ready()
        original=snapshot(game.inventory,game.ground_loot,game.magazine,game.selected_slot)
        original['version']=1
        for stack in original['ground']['stacks']:stack.pop('magazine')
        inventory,ground,magazine,selected=restore(original)
        self.assertEqual((magazine,selected),(28,1))
        self.assertEqual(next(iter(ground.stacks.values())).magazine,0)
        game=self.ready()
        game.handle(0x3e80,drop(1,container=1,slot=1))
        valid=snapshot(game.inventory,game.ground_loot,game.magazine,game.selected_slot)
        for mutate in [lambda x:x['ground']['stacks'][1].update(magazine=31),
                       lambda x:x['ground']['stacks'][1].pop('magazine'),
                       lambda x:x['inventory'].update(magazine=28),
                       lambda x:x['ground']['stacks'][0].update(magazine=1)]:
            data=copy.deepcopy(valid)
            mutate(data)
            with self.assertRaises(ValueError):restore(data)


if __name__=='__main__':unittest.main()
