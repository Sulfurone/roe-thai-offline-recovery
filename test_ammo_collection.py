import struct
import unittest
from offline_gameplay import OfflineGameplay
from offline_inventory import OfflineInventory,Item,MAX_AMMO
from test_ground_loot import request


class AmmoCollectionTests(unittest.TestCase):
    def test_explicit_slot_pickups_compact_existing_rounds_and_keep_other_types(self):
        game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True)
        game.actor_ready=True;game.ground_loot.announced=True
        inv=game.inventory
        inv.items[2,1]=Item(3,30001,inv.next_uid,600);inv.next_uid+=1
        inv.items[2,2]=Item(3,30002,inv.next_uid,90);inv.next_uid+=1
        inv.items[2,3]=Item(3,30001,inv.next_uid,100);inv.next_uid+=1
        stack=game.ground_loot.add(Item(3,30001,inv.next_uid,200),game.player_position)
        inv.next_uid+=1
        replies=game.handle(0x3b63,request(stack.entity,container=2,destination=5,automatic=0))
        self.assertEqual([m for m,_ in replies],[0x3e82,0x82b,0x3b64])
        self.assertEqual([(k,v.count) for k,v in inv.items.items() if v.kind==3 and v.template==30001],
                         [((2,0),999),((2,1),21)])
        self.assertEqual(inv.items[2,2].count,90)
        self.assertNotIn((2,3),inv.items);self.assertNotIn((2,5),inv.items)
        self.assertNotIn(stack.entity,game.ground_loot.stacks)
        self.assertEqual(replies[0][1][0],3)  # Two changed stacks plus a cleared old slot.

    def test_full_bag_uses_space_across_fragmented_stacks(self):
        inv=OfflineInventory(700)
        inv.items[2,1]=Item(3,30001,100,700)
        for i in range(2,128):inv.items[2,i]=Item(4,40305,1000+i,1)
        changed=inv.collect_ammunition(Item(3,30001,9999,500))
        self.assertIsNotNone(changed)
        self.assertEqual([inv.items[2,i].count for i in (0,1)],[999,901])
        before=dict(inv.items)
        self.assertIsNone(inv.collect_ammunition(Item(3,30001,9999,100)))
        self.assertEqual(inv.items,before)

    def test_one_pickup_never_exceeds_original_stack_bound(self):
        inv=OfflineInventory(MAX_AMMO)
        changed=inv.collect_ammunition(Item(3,30001,100,120),(2,8))
        self.assertEqual(inv.items[2,0].count,MAX_AMMO)
        self.assertEqual(inv.items[2,8],Item(3,30001,100,120))
        self.assertEqual(changed,[(2,8)])

    def test_fire_deltas_reach_zero_and_reload_only_spends_finite_reserve(self):
        game=OfflineGameplay(inventory_enabled=True,magazine=3,reserve=2)
        shot=struct.pack('>6fIB',1,2,3,1,102,3,1,0)
        for remaining in (2,1,0,0):
            replies=game.handle(0x11d3,shot)
            self.assertEqual([m for m,_ in replies],[0x3e82])
            self.assertEqual(struct.unpack_from('>3I',replies[0][1],70),(7,30001,remaining))
            self.assertEqual(game.inventory.reserve_for(30001),2)
        game.handle(0x49c,struct.pack('>I',1))
        self.assertEqual((game.magazine,game.inventory.reserve_for(30001)),(2,0))
        for _ in range(3):game.handle(0x11d3,shot)
        self.assertEqual((game.magazine,game.inventory.reserve_for(30001)),(0,0))
        self.assertEqual([m for m,_ in game.handle(0x49c,struct.pack('>I',1))],[0x49d])


if __name__=='__main__':unittest.main()
