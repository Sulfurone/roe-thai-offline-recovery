"""Local extension capacity, overflow transactions, reload and persistence."""
import copy
from dataclasses import replace
import struct
import unittest
from unittest.mock import patch

from offline_gameplay import OfflineGameplay
from offline_inventory import OfflineInventory,Item
from offline_ground_loot import OfflineGroundLoot
from offline_weapons import magazine_capacity
from offline_world_state import snapshot,restore
from test_equipment_actions import part_request


def equipped(reserve=0):
    iv=OfflineInventory(reserve)
    gun=iv.items[1,1]
    part=Item(4,40403,iv.next_uid,1);iv.next_uid+=1
    iv.items[1,1]=replace(gun,parts=((3,part),))
    iv.weapon_magazines[gun.uid]=40
    return iv,gun,part


class ExtendedMagazineTests(unittest.TestCase):
    def test_install_reload_fire_and_detach_preserve_every_round(self):
        g=OfflineGameplay(inventory_enabled=True,magazine=19,reserve=70,reload_original=True)
        g.actor_ready=True
        iv=g.inventory;gun=iv.items[1,1]
        part=Item(4,40403,iv.next_uid,1);iv.next_uid+=1;iv.items[2,1]=part
        self.assertEqual([m for m,b in g.handle(0x3e80,part_request(0,2,1,gun.uid,3,3))],[0x3e82,0x3e81])
        self.assertEqual((magazine_capacity(iv.items[1,1]),g.magazine),(40,19))
        with patch('time.monotonic',return_value=100):g.handle(0x49c,struct.pack('>I',1))
        self.assertEqual(g.tick(101.89),[])
        g.tick(101.91)
        self.assertEqual((g.magazine,iv.reserve_for(30001)),(40,49))
        for _ in range(3):g.handle(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,1,0))
        result=g.handle(0x3e80,part_request(gun.uid,3,3,0,2,1))
        self.assertEqual([m for m,b in result],[0x3e82,0x3e81])
        self.assertEqual((g.magazine,iv.reserve_for(30001)),(30,56))
        self.assertEqual(iv.items[2,1],part)

    def test_no_overflow_space_rejects_whole_detach_including_uid_and_magazine(self):
        iv,gun,part=equipped()
        for slot in range(1,128):
            iv.items[2,slot]=Item(7,70001,iv.next_uid,1);iv.next_uid+=1
        before=copy.deepcopy((iv.items,iv.weapon_magazines,iv.next_uid))
        self.assertEqual(iv.handle(part_request(gun.uid,3,3,0,2,0)),[iv.reply(6,1)])
        self.assertEqual((iv.items,iv.weapon_magazines,iv.next_uid),before)

    def test_full_bag_can_use_existing_ammo_stack_but_partial_room_is_atomic(self):
        iv,gun,part=equipped()
        for slot in range(1,128):
            iv.items[2,slot]=Item(7,70001,iv.next_uid,1);iv.next_uid+=1
        iv.items[2,1]=replace(iv.items[2,1],kind=3,template=30001,count=990)
        before=copy.deepcopy(iv.items)
        self.assertEqual(iv.handle(part_request(gun.uid,3,3,0,2,0)),[iv.reply(6,1)])
        self.assertEqual(iv.items,before)
        iv.items[2,1]=replace(iv.items[2,1],count=989)
        self.assertEqual([m for m,b in iv.handle(part_request(gun.uid,3,3,0,2,0))],[0x3e82,0x3e81])
        self.assertEqual((iv.weapon_magazines[gun.uid],iv.items[2,1].count),(30,999))

    def test_new_overflow_stack_has_unique_identity_and_extended_ground_save_round_trips(self):
        iv,gun,part=equipped()
        ground=OfflineGroundLoot()
        iv2,ground2,loaded,slot=restore(snapshot(iv,ground,40,1))
        self.assertEqual(loaded,40)
        loaded_gun=iv2.items.pop((1,1));iv2.weapon_magazines.pop(gun.uid)
        ground2.add(loaded_gun,(1000,2000,3000),40)
        iv3,ground3,_,_=restore(snapshot(iv2,ground2,0,0))
        stack=list(ground3.stacks.values())[-1]
        self.assertEqual((stack.magazine,magazine_capacity(stack.item)),(40,40))
        next_uid=iv.next_uid
        iv.handle(part_request(gun.uid,3,3,0,2,0))
        ammo=[item for key,item in iv.items.items() if item.kind==3]
        self.assertEqual([(item.uid,item.count) for item in ammo],[(next_uid,10)])
        self.assertEqual(iv.next_uid,next_uid+1)

    def test_transferring_magazine_between_guns_unloads_source_without_filling_target(self):
        iv,gun,part=equipped(20)
        other=Item(1,10202,iv.next_uid,1);iv.next_uid+=1
        iv.items[1,2]=other;iv.weapon_magazines[other.uid]=10
        iv.handle(part_request(gun.uid,3,3,other.uid,3,3))
        self.assertEqual((magazine_capacity(iv.items[1,1]),magazine_capacity(iv.items[1,2])),(30,40))
        self.assertEqual((iv.weapon_magazines[gun.uid],iv.weapon_magazines[other.uid],iv.reserve_for(30001)),(30,10,30))
        self.assertEqual(dict(iv.items[1,2].parts)[3],part)


if __name__=='__main__':unittest.main()
