import json
from pathlib import Path
import struct
import tempfile
import unittest

from offline_gameplay import OfflineGameplay,TYPED_ACTOR_UID
from offline_inventory import Item,OfflineInventory
from offline_weapons import WEAPONS,AMMUNITION
from offline_world_state import restore,snapshot
from test_ground_loot import request,drop

ROOT=Path(__file__).resolve().parent

class ArsenalTests(unittest.TestCase):
    def ready(self,path=None,arsenal=True):
        g=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,arsenal_enabled=arsenal,
                          world_file=path,actor_uid=TYPED_ACTOR_UID)
        g.handle(0x2a,struct.pack('>I3i',1,325800,271700,6488))
        return g

    def pick(self,g,template):
        stack=next(s for s in g.ground_loot.stacks.values() if s.item.template==template)
        g.handle(0x2a,struct.pack('>I3i',1,*stack.position))
        replies=g.handle(0x3b63,request(stack.entity))
        self.assertEqual(replies[0][0],0x3e82)
        return stack,replies

    def test_catalogue_matches_independently_extracted_original_data(self):
        data=json.loads((ROOT/'private/gameplay-catalog/weapon-stat-prefixes.json').read_text(encoding='utf-8'))
        original={r['id']:(r['item_category'],r['max_ammo'],r['ammo_template']) for r in data['firearms']}
        self.assertEqual({i:(s.kind,s.capacity,s.ammunition) for i,s in WEAPONS.items()},original)
        self.assertEqual(AMMUNITION,{30001,30002,30003,30004,30005,30006})

    def test_all_firearms_seed_and_survive_save_without_reseeding(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'world.json'
            game=self.ready(path)
            self.assertEqual(len(game.ground_loot.stacks),26)
            self.assertEqual({x.item.template for x in game.ground_loot.stacks.values()},set(WEAPONS)|AMMUNITION)
            self.assertTrue(path.exists())
            before=path.read_bytes()
            again=self.ready(path)
            self.assertEqual(again.ground_loot.stacks,game.ground_loot.stacks)
            self.assertEqual(path.read_bytes(),before)

    def test_ak_uses_only_762_ammo_and_retains_rounds_when_dropped(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'world.json'
            game=self.ready(path)
            game.handle(0x3e80,drop(1,container=1,slot=1))
            self.pick(game,10202)
            game.handle(0x49e,struct.pack('>I',1))
            game.handle(0x49c,struct.pack('>I',1))
            self.assertEqual((game.magazine,game.inventory.reserve_for(30001)),(0,120))
            self.pick(game,30002)
            game.handle(0x49c,struct.pack('>I',1))
            self.assertEqual((game.magazine,game.inventory.reserve_for(30001),game.inventory.reserve_for(30002)),(30,120,30))
            game.handle(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,1,0))
            game.handle(0x3e80,drop(1,container=1,slot=1))
            saved=next(s for s in game.ground_loot.stacks.values() if s.item.template==10202)
            self.assertEqual(saved.magazine,29)
            again=self.ready(path)
            self.assertEqual(again.ground_loot.stacks[saved.entity].magazine,29)
            picked,_=self.pick(again,10202)
            self.assertEqual((picked.item.uid,again.magazine),(saved.item.uid,29))

    def test_glock_uses_original_pistol_slot_and_capacity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'world.json'
            game=self.ready(path)
            game.handle(0x3e80,drop(1,container=1,slot=1))
            pistol,replies=self.pick(game,20002)
            self.assertEqual((game.inventory.weapon_slot(),game.magazine),(3,0))
            self.assertEqual(len(replies[0][1]),91)  # unique gun with its loaded-ammo row
            self.assertEqual(replies[2][1][8],2)
            self.pick(game,30003)
            game.handle(0x49e,struct.pack('>I',3))
            game.handle(0x49c,struct.pack('>I',3))
            self.assertEqual((game.magazine,game.inventory.reserve_for(30003)),(17,43))
            game.handle(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,1,0))
            game.handle(0x3e80,drop(1,container=1,slot=3))
            saved=next(s for s in game.ground_loot.stacks.values() if s.item.uid==pistol.item.uid)
            self.assertEqual(saved.magazine,16)
            again=self.ready(path)
            self.pick(again,20002)
            self.assertEqual((again.inventory.weapon_slot(),again.magazine),(3,16))

    def test_wrong_slot_and_invalid_magazine_are_rejected(self):
        inv=OfflineInventory()
        self.assertFalse(inv.fits((1,3),Item(1,10202,123,1)))
        self.assertFalse(inv.fits((1,1),Item(2,20002,123,1)))
        game=self.ready()
        game.handle(0x3e80,drop(1,container=1,slot=1))
        self.pick(game,20002)
        data=snapshot(game.inventory,game.ground_loot,game.magazine,game.selected_slot)
        data['inventory']['magazine']=18
        with self.assertRaises(ValueError):restore(data)
        data=snapshot(game.inventory,game.ground_loot,game.magazine,game.selected_slot)
        row=next(r for r in data['ground']['stacks'] if r['item']['template']==10402)
        row['magazine']=3
        with self.assertRaises(ValueError):restore(data)

if __name__=='__main__':unittest.main()
