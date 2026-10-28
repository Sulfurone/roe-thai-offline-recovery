"""Per-gun loaded rounds and reserve conservation across actual inventory actions."""
import struct
import unittest

from offline_gameplay import OfflineGameplay
from offline_inventory import Item
from test_offline_inventory import transfer
from test_equipment_actions import part_request


class AmmunitionTests(unittest.TestCase):
    def test_stack_quantity_is_in_native_stack_union_not_category_tag(self):
        for kind,template,count in ((3,30001,120),(4,40305,1),(5,50001,4),(7,70001,5)):
            wire=Item(kind,template,11,count).wire()
            self.assertEqual(wire[0],2)
            self.assertEqual(struct.unpack_from('>H',wire,30)[0],count)

    def test_switch_pickup_drop_and_backpack_change_do_not_emit_reload(self):
        game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,magazine=19)
        gun=Item(2,20002,game.inventory.next_uid,1)
        game.inventory.next_uid+=1
        game.inventory.items[1,3]=gun
        game.inventory.weapon_magazines[gun.uid]=7
        for slot,expected in ((3,7),(0,0),(1,19),(3,7),(1,19)):
            self.assertEqual(game.handle(0x49e,struct.pack('>I',slot)),[])
            self.assertEqual(game.magazine,expected)
        replies=game.handle(0x3e80,transfer((2,0),(2,5),20))
        self.assertNotIn(0x4a0,dict(replies))
        self.assertEqual((game.magazine,game.reserve),(19,120))
        game.inventory.items[2,6]=Item(4,40305,game.inventory.next_uid,1)
        game.inventory.next_uid+=1
        part=game.inventory.items[2,6]
        replies=game.handle(0x3e80,part_request(part.uid,2,6,game.inventory.items[1,1].uid,3,2))
        self.assertNotIn(0x4a0,dict(replies))
        self.assertEqual(game.magazine,19)

    def test_loaded_rounds_encoded_before_pickup_delta_and_preserved_on_transfer(self):
        game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True)
        game.actor_ready=True
        game.ground_loot.announced=True
        gun=Item(1,10202,game.inventory.next_uid,1)
        game.inventory.next_uid+=1
        stack=game.ground_loot.add(gun,game.player_position,9)
        request=struct.pack('>IIQBHB3iB',stack.entity,0,0,1,2,0,*stack.position,0)
        replies=game.handle(0x3b63,request)
        wire=dict(replies)[0x3e82]
        self.assertEqual(struct.unpack_from('>3I',wire,4+66),(7,30002,9))
        self.assertNotIn(0x4a0,dict(replies))
        game.handle(0x3e80,transfer((1,2),(2,8),1))
        game.handle(0x3e80,transfer((2,8),(1,2),1))
        game.handle(0x49e,struct.pack('>I',2))
        self.assertEqual(game.magazine,9)

    def test_reload_uses_selected_gun_ammo_and_never_creates_rounds(self):
        game=OfflineGameplay(inventory_enabled=True,magazine=19,reserve=7)
        wrong=Item(3,30002,game.inventory.next_uid,50)
        game.inventory.next_uid+=1
        game.inventory.items[2,1]=wrong
        before=game.magazine+game.inventory.reserve_for(30001)
        game.handle(0x49c,struct.pack('>I',1))
        self.assertEqual((game.magazine,game.inventory.reserve_for(30001)),(26,0))
        self.assertEqual(game.magazine+game.inventory.reserve_for(30001),before)
        self.assertEqual(game.inventory.items[2,1],wrong)
        self.assertEqual([m for m,_ in game.handle(0x49c,struct.pack('>I',1))],[0x49d])
        game.handle(0x49e,bytes(4))
        game.handle(0x49c,struct.pack('>I',1))
        self.assertEqual(game.inventory.weapon_magazines[0x100101],26)

    def test_fire_consumes_without_equal_count_reload_receipt(self):
        game=OfflineGameplay(inventory_enabled=True,magazine=3)
        shot=struct.pack('>6fIB',1,2,3,1,102,3,1,0)
        for expected in (2,1,0,0):
            self.assertEqual(game.handle(0x11d3,shot),[])
            self.assertEqual(game.magazine,expected)
        self.assertEqual(game.reserve,120)


if __name__=='__main__':unittest.main()
