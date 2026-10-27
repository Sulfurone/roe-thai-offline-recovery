import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from offline_gameplay import OfflineGameplay
from offline_inventory import Item,OfflineInventory


def transfer(source,destination,quantity,current=1):
    return struct.pack('>BBHBHHB',1,*source,*destination,quantity,current)


class InventoryTests(unittest.TestCase):
    def test_initial_payload_matches_original_native_generated_fixture(self):
        fixture=Path(__file__).parent/'private/native-roster/inventory-m4a1-candidate.bin'
        self.assertEqual(OfflineInventory().full_body(),fixture.read_bytes())

    def test_split_merge_and_move_conserve_ammunition_and_identity(self):
        inventory=OfflineInventory()
        uid=inventory.items[2,0].uid
        replies=inventory.handle(transfer((2,0),(2,5),20)+bytes(8))
        self.assertEqual([m for m,_ in replies],[0x3e82,0x3e81])
        self.assertEqual([inventory.items[2,n].count for n in (0,5)],[100,20])
        self.assertNotEqual(inventory.items[2,5].uid,uid)
        inventory.handle(transfer((2,5),(2,0),20))
        self.assertNotIn((2,5),inventory.items)
        self.assertEqual(inventory.items[2,0].uid,uid)
        inventory.handle(transfer((2,0),(2,9),120))
        self.assertNotIn((2,0),inventory.items)
        self.assertEqual(inventory.items[2,9].uid,uid)
        self.assertEqual(inventory.reserve,120)

    def test_invalid_operations_and_unsupported_drop_preserve_items(self):
        inventory=OfflineInventory()
        before=inventory.snapshot(30,1)
        for body in [transfer((2,0),(1,2),10),transfer((2,0),(2,128),10),
                     transfer((2,0),(2,1),121),transfer((2,0),(2,1),0),
                     transfer((2,0),(2,1),10,0),transfer((2,0),(2,1),10)[:-1],
                     struct.pack('>BBHHQB',2,2,0,20,0,1)]:
            inventory.handle(body)
            self.assertEqual(inventory.snapshot(30,1),before)

    def test_same_slot_is_noop_and_whole_stack_swap_preserves_objects(self):
        inventory=OfflineInventory()
        before=dict(inventory.items)
        inventory.handle(transfer((2,0),(2,0),20))
        self.assertEqual(inventory.items,before)
        inventory.handle(transfer((1,1),(2,1),1))
        inventory.handle(transfer((2,0),(2,1),120))
        self.assertEqual(inventory.items[2,0].uid,0x100101)
        self.assertEqual(inventory.items[2,1].uid,0x100102)
        self.assertEqual(inventory.reserve,120)

    def test_weapon_slot_change_reload_and_empty_ammo_stack(self):
        game=OfflineGameplay(inventory_enabled=True,magazine=29,reserve=2)
        game.handle(0x3e80,transfer((2,0),(2,5),1))
        game.handle(0x3e80,transfer((1,1),(1,2),1))
        self.assertEqual(struct.unpack('>QII',game.handle(0x49e,struct.pack('>I',2))[0][1])[1:],(2,29))
        shot=struct.pack('>6fIB',1,2,3,1,102,3,1,0)
        game.handle(0x11d3,shot)
        replies=game.handle(0x49c,struct.pack('>I',2))
        self.assertEqual(game.magazine,30)
        self.assertEqual(game.reserve,0)
        self.assertNotIn((2,0),game.inventory.items)
        self.assertNotIn((2,5),game.inventory.items)
        self.assertEqual(replies[-1][0],0x3e82)
        self.assertEqual(replies[-1][1][0],2)
        self.assertNotEqual(struct.unpack('>II',game.handle(0x49c,struct.pack('>I',1))[0][1])[1],0)

    def test_stowed_weapon_cannot_fire_or_reload(self):
        game=OfflineGameplay(inventory_enabled=True,magazine=29)
        game.handle(0x3e80,transfer((1,1),(2,8),1))
        self.assertEqual(game.handle(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,1,0)),[])
        game.handle(0x49c,struct.pack('>I',1))
        # The live magazine mirrors the selected slot; the stowed gun keeps
        # its rounds in the per-weapon record.
        self.assertEqual((game.magazine,game.reserve),(0,120))
        self.assertEqual(game.inventory.weapon_magazines[0x100101],29)
        game.handle(0x3e80,transfer((2,8),(1,2),1))
        self.assertEqual(game.inventory.weapon_slot(),2)
        game.handle(0x49e,struct.pack('>I',2))
        self.assertEqual(game.magazine,29)

    def test_atomic_save_reopen_and_noop_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'profile.json'
            game=OfflineGameplay(inventory_enabled=True,state_file=path,magazine=29)
            game.handle(0x3e80,transfer((2,0),(2,5),20))
            game.handle(0x3e80,transfer((1,1),(1,2),1))
            game.handle(0x49e,struct.pack('>I',2))
            game.handle(0x49c,struct.pack('>I',2))
            self.assertTrue(game.save_state())
            self.assertFalse(game.save_state())
            self.assertFalse(path.with_suffix('.json.tmp').exists())
            restored=OfflineGameplay(inventory_enabled=True,state_file=path)
            self.assertEqual((restored.magazine,restored.reserve,restored.selected_slot),(30,119,2))
            self.assertEqual(restored.inventory.items,game.inventory.items)
            self.assertEqual(restored.inventory.next_uid,game.inventory.next_uid)

    def test_corrupt_profile_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'profile.json'
            path.write_text('{broken profile',encoding='utf-8')
            with self.assertRaises(ValueError):
                OfflineGameplay(inventory_enabled=True,state_file=path)
            self.assertEqual(path.read_text(encoding='utf-8'),'{broken profile')

    def test_profile_validation_rejects_duplicate_and_out_of_range_data(self):
        valid=OfflineGameplay(inventory_enabled=True).inventory.snapshot(30,1)
        for mutate in [lambda x:x.update(version=1),
                       lambda x:x.update(magazine=-1),
                       lambda x:x['items'][1].update(uid=x['items'][0]['uid']),
                       lambda x:x['items'][1].update(count=1000),
                       lambda x:x['items'][1].update(slot=128),
                       lambda x:x['items'][1].update(template=999),
                       lambda x:x.update(selected_slot=True),
                       lambda x:x['weapon_magazines'][0].update(magazine=999),
                       lambda x:x['weapon_magazines'][0].update(magazine=29),
                       lambda x:x['weapon_magazines'][0].update(uid=999),
                       lambda x:x['weapon_magazines'].append({'uid':x['items'][0]['uid'],'magazine':1})]:
            data=copy.deepcopy(valid)
            mutate(data)
            with self.assertRaises(ValueError):
                OfflineInventory.restore(data)

    def test_two_long_guns_and_one_pistol_carry_but_a_third_long_gun_fails(self):
        inventory=OfflineInventory()
        primary=inventory.items[1,1]
        inventory.items[1,2]=Item(1,10202,0x100081,1)
        inventory.items[1,3]=Item(2,20002,0x100082,1)
        inventory.weapon_magazines={primary.uid:30,0x100081:0,0x100082:17}
        restored=OfflineInventory.restore(inventory.snapshot(30,1))
        self.assertEqual(restored.weapon_magazines,inventory.weapon_magazines)
        inventory.items[2,5]=Item(1,10201,0x100083,1)
        with self.assertRaises(ValueError):
            OfflineInventory.restore(inventory.snapshot(30,1))

    def test_automatic_inventory_probe_returns_weapon_without_repeating(self):
        game=OfflineGameplay(inventory_enabled=True,inventory_selftest=True)
        game.inventory_test_started=100
        self.assertEqual(game.tick(101),[])
        game.tick(102)
        self.assertEqual(game.inventory.items[2,5].count,30)
        game.tick(104)
        self.assertEqual(game.inventory.weapon_slot(),2)
        game.tick(106)
        self.assertEqual(game.inventory.weapon_slot(),1)
        self.assertEqual(game.inventory.reserve,120)
        self.assertEqual(game.tick(200),[])


if __name__=='__main__':
    unittest.main()
