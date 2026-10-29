import struct
import unittest
from offline_gameplay import OfflineGameplay
from offline_inventory import Item,OfflineInventory
from test_offline_inventory import transfer
from test_throwables import start


class ThrowableEquipmentTests(unittest.TestCase):
    def test_missing_flash_config_is_not_offered_as_usable_loot(self):
        from offline_control import validate_command
        from offline_items import EXTRA_ITEMS,SPAWNABLE_EXTRA_ITEMS,THROWABLE_CONFIG_IDS
        self.assertIn(50003,EXTRA_ITEMS)  # Old private profiles still decode.
        self.assertNotIn(50003,SPAWNABLE_EXTRA_ITEMS)
        self.assertEqual({i for i,s in SPAWNABLE_EXTRA_ITEMS.items() if s.kind==5},set(THROWABLE_CONFIG_IDS))
        with self.assertRaisesRegex(ValueError,'原生配置'):
            validate_command(dict(action='item',template=50003))
    def test_observed_single_item_drag_replaces_a_different_throwable_stack(self):
        game=OfflineGameplay(inventory_enabled=True,throwables_enabled=True)
        game.actor_ready=True
        inv=game.inventory
        old=Item(5,50002,inv.next_uid,4);inv.next_uid+=1
        source=Item(5,50001,inv.next_uid,5);inv.next_uid+=1
        inv.items[1,5]=old;inv.items[2,7]=source
        before=inv.next_uid
        # Exactly the slot/quantity request repeatedly rejected in the live log.
        request=bytes.fromhex('01020007010005000101')
        replies=game.handle(0x3e80,request)
        self.assertEqual([mid for mid,_ in replies],[0x3e82,0x3e81])
        self.assertEqual(inv.items[1,5],Item(5,50001,before,1))
        self.assertEqual(inv.items[2,7],Item(5,50001,source.uid,4))
        self.assertEqual([v for k,v in inv.items.items() if k[0]==2 and v.template==50002],[old])
        self.assertEqual(replies[0][1][0],3)
        self.assertEqual(game.handle(0x49e,struct.pack('>I',5)),[])
        self.assertEqual(game.handle(0x1004,start())[0],(0x1005,struct.pack('>III',50001,37,0)))
        self.assertNotIn((1,5),inv.items)
        self.assertEqual(inv.items[2,7].count,4)

    def test_full_bag_cannot_destroy_or_duplicate_a_partial_equipment_swap(self):
        inv=OfflineInventory()
        inv.items[1,5]=Item(5,50002,100,3)
        for i in range(128):inv.items[2,i]=Item(5,50001,1000+i,5)
        inv.next_uid=2000
        before=inv.snapshot(30,1)
        self.assertEqual(inv.handle(transfer((2,7),(1,5),1)),[inv.reply(1,1)])
        self.assertEqual(inv.snapshot(30,1),before)
        # A whole-stack swap reuses its source slot and still works when full.
        self.assertEqual([mid for mid,_ in inv.handle(transfer((2,7),(1,5),5))],[0x3e82,0x3e81])
        self.assertEqual(inv.items[2,7],Item(5,50002,100,3))

    def test_empty_throw_slot_and_same_type_stacking_keep_existing_behavior(self):
        inv=OfflineInventory()
        inv.items[2,7]=Item(5,50001,100,5)
        inv.handle(transfer((2,7),(1,5),1))
        self.assertEqual(inv.items[1,5].count,1)
        inv.handle(transfer((2,7),(1,5),1))
        self.assertEqual((inv.items[1,5].count,inv.items[2,7].count),(2,3))
        inv.handle(transfer((2,7),(2,7),99))
        self.assertFalse(inv.last_transfer_event['accepted'])
        inv.handle(transfer((2,7),(2,7),1))
        self.assertTrue(inv.last_transfer_event['accepted'])


if __name__=='__main__':unittest.main()
