"""Thai attachment identity conservation and new loot/drop regression checks."""
import copy
import struct
import unittest
from unittest.mock import patch

from offline_inventory import Item,OfflineInventory,item_uids
from offline_items import EXTRA_ITEMS
from offline_ground_loot import OfflineGroundLoot
from offline_population import WorldPopulation
from offline_world_state import snapshot,restore
from control_actions import ControlSession
from test_control_panel import ready_game
from test_population import Surface


def part_request(source,src,src_slot,target,dst,dst_slot):
    return struct.pack('>BQBHQBHHB',6,source,src,src_slot,target,dst,dst_slot,1,1)


class EquipmentActionsTests(unittest.TestCase):
    def inventory(self):
        iv=OfflineInventory()
        iv.weapon_magazines[iv.items[1,1].uid]=30
        iv.items[2,1]=Item(4,40305,iv.next_uid,1)
        iv.next_uid+=1
        iv.items[2,2]=Item(4,40303,iv.next_uid,1)
        iv.next_uid+=1
        return iv

    def test_attach_replace_detach_conserve_unique_parts_and_wire_ids(self):
        iv=self.inventory()
        gun=iv.items[1,1]
        red,four=iv.items[2,1],iv.items[2,2]
        for key in ((2,1),(2,2)):
            part=iv.items[key]
            replies=iv.handle(part_request(part.uid,*key,gun.uid,3,2))
            self.assertEqual([m for m,b in replies],[0x3e82,0x3e81])
            self.assertEqual(dict(iv.items[1,1].parts)[2],part)
            self.assertEqual(struct.unpack_from('>3I',iv.item_wire(iv.items[1,1]),66),(2,part.template,0))
        self.assertEqual(iv.items[2,2],red)  # previous scope returns to the source slot
        self.assertNotIn((2,1),iv.items)
        iv.handle(part_request(gun.uid,3,2,0,2,1))
        self.assertEqual(iv.items[2,1],four)
        self.assertEqual(iv.items[1,1].parts,())
        uids=[uid for item in iv.items.values() for uid in item_uids(item)]
        self.assertEqual(len(uids),len(set(uids)))

    def test_incompatible_part_bad_uid_and_full_detach_target_are_atomic(self):
        iv=self.inventory()
        gun=iv.items[1,1]
        iv.items[2,3]=Item(4,40101,iv.next_uid,1)  # sniper muzzle does not fit M4A1
        iv.next_uid+=1
        cases=[part_request(iv.items[2,3].uid,2,3,gun.uid,3,0),
               part_request(iv.items[2,1].uid+99,2,1,gun.uid,3,2),
               part_request(iv.items[2,1].uid,2,1,gun.uid,3,1)]
        for request in cases:
            before=copy.deepcopy(iv.items)
            self.assertEqual(iv.handle(request)[0][0],0x3e81)
            self.assertEqual(iv.items,before)
        iv.handle(part_request(iv.items[2,1].uid,2,1,gun.uid,3,2))
        before=copy.deepcopy(iv.items)
        iv.handle(part_request(gun.uid,3,2,0,2,2))
        self.assertEqual(iv.items,before)

    def test_original_slot_based_attach_allows_zero_bag_uid_but_requires_weapon_identity(self):
        iv=self.inventory();gun=iv.items[1,1];part=iv.items[2,1]
        replies=iv.handle(part_request(0,2,1,gun.uid,3,2))
        self.assertEqual([m for m,b in replies],[0x3e82,0x3e81])
        self.assertEqual(dict(iv.items[1,1].parts)[2],part)
        self.assertEqual(iv.weapon_magazines[gun.uid],30)
        before=copy.deepcopy(iv.items)
        for request in (part_request(0,3,2,0,2,1),
                        part_request(iv.items[2,2].uid+999,2,2,gun.uid,3,2)):
            self.assertEqual(iv.handle(request),[iv.reply(6,1)])
            self.assertEqual(iv.items,before)
        iv.handle(part_request(gun.uid,3,2,0,2,1))
        self.assertEqual(iv.items[2,1],part)
        self.assertEqual(iv.items[1,1].parts,())

    def test_installed_part_survives_world_save_gun_drop_pickup_and_detach(self):
        game=ready_game()
        game.inventory=self.inventory()
        game.ground_loot.stacks.clear()  # this test supplies its own item allocator
        gun=game.inventory.items[1,1]
        part=game.inventory.items[2,1]
        game.handle(0x3e80,part_request(part.uid,2,1,gun.uid,3,2))
        game.handle(0x3e80,struct.pack('>BBHHQB',2,1,1,0,0,1))
        stack=list(game.ground_loot.stacks.values())[-1]
        iv,world,mag,slot=restore(snapshot(game.inventory,game.ground_loot,game.magazine,game.selected_slot))
        self.assertEqual(dict(world.stacks[stack.entity].item.parts)[2],part)
        game.inventory,game.ground_loot=iv,world
        world.announced=True
        game.handle(0x3b63,struct.pack('>IIQBHB3iB',stack.entity,0,0,1,1,0,*stack.position,0))
        self.assertEqual(dict(game.inventory.items[1,1].parts)[2],part)
        game.handle(0x3e80,part_request(gun.uid,3,2,0,2,1))
        self.assertEqual(game.inventory.items[2,1],part)

    def test_nested_part_duplicate_identity_and_incompatible_profile_rejected(self):
        iv=self.inventory()
        gun=iv.items[1,1]
        iv.handle(part_request(iv.items[2,1].uid,2,1,gun.uid,3,2))
        data=iv.snapshot(30,1)
        gunrow=next(r for r in data['items'] if r['uid']==gun.uid)
        for field,value in (('uid',gun.uid),('template',40101)):
            bad=copy.deepcopy(data)
            row=next(r for r in bad['items'] if r['uid']==gun.uid)
            row['parts'][0][field]=value
            with self.assertRaises(ValueError):OfflineInventory.restore(bad)
        self.assertEqual(gunrow['parts'][0]['index'],2)

    def test_new_cell_contains_medicine_helmets_and_vests_in_bounded_world(self):
        game=ready_game()
        game.player_position=(100000,200000,7250)
        population=WorldPopulation(ControlSession(game),Surface(),42,vehicles=False,extra_items=True)
        population.tick()
        specs=[EXTRA_ITEMS[s.item.template] for s in game.ground_loot.stacks.values() if s.item.template in EXTRA_ITEMS]
        self.assertEqual(sum(s.kind==7 for s in specs),4)
        for slot in (10,11,12):self.assertEqual(sum(s.slot==slot for s in specs),4)
        for i in range(20):
            game.player_position=(100000+i*15000,200000,7250)
            population.tick()
        self.assertLessEqual(len(game.ground_loot.stacks),WorldPopulation.AUTO_GROUND_CAP)

    def test_medicine_stacks_and_armor_go_to_original_slots(self):
        game=ready_game()
        control=ControlSession(game)
        for template in (70001,70002,70003,200101,201001):
            control.execute(dict(action='item',template=template))
            stack=list(game.ground_loot.stacks.values())[-1]
            replies=game.handle(0x3b63,struct.pack('>IIQBHB3iB',stack.entity,0,0,0,0,1,*game.player_position,0))
            self.assertEqual(replies[0][0],0x3e82)
            key=next(k for k,v in game.inventory.items.items() if v.uid==stack.item.uid)
            self.assertEqual(key[0],1 if EXTRA_ITEMS[template].slot else 2)
        self.assertEqual(game.inventory.items[1,10].template,200101)
        self.assertEqual(game.inventory.items[1,12].template,201001)

    def test_drop_uses_recent_successful_pickup_floor_instead_of_old_foot(self):
        game=ready_game()
        old=game.player_position
        camera=(old[0]+2500,old[1],old[2]+170)
        stack=game.ground_loot.add(Item(7,70001,game.inventory.next_uid,1),(camera[0],camera[1],old[2]))
        game.inventory.next_uid+=1
        with patch('offline_gameplay.time.monotonic',return_value=100):
            game.handle(0x3b63,struct.pack('>IIQBHB3iB',stack.entity,0,0,0,0,1,*camera,0))
            key=next(k for k,v in game.inventory.items.items() if v.uid==stack.item.uid)
            replies=game.handle(0x3e80,struct.pack('>BBHHQB',2,*key,0,0,1))
        dropped=list(game.ground_loot.stacks.values())[-1]
        self.assertEqual(replies[0][0],0x821)
        self.assertEqual(dropped.position,(*camera[:2],old[2]))
        self.assertEqual(dropped.item,stack.item)
        self.assertEqual(game.player_position,old)  # do not promote camera to a foot report
        self.assertEqual(game.last_drop_event['source'],'recent_pickup_camera_floor')
        again=game.handle(0x3b63,struct.pack('>IIQBHB3iB',dropped.entity,0,0,0,0,1,*camera,0))
        self.assertEqual(again[0][0],0x3e82)

    def test_drop_anchor_expires_and_new_foot_report_invalidates_it(self):
        game=ready_game()
        game.pickup_drop_anchor=(100,200,300)
        game.pickup_drop_time=100
        with patch('offline_gameplay.time.monotonic',return_value=131):
            game.handle(0x3e80,struct.pack('>BBHHQB',2,2,0,1,0,1))
        self.assertEqual(game.last_drop_event['source'],'actor_keyframe')
        game.handle(0x2a,struct.pack('>I3i',1,*game.player_position))
        self.assertIsNone(game.pickup_drop_anchor)

    def test_part_mutation_is_rolled_back_if_world_commit_fails(self):
        from pathlib import Path
        game=ready_game()
        iv=game.inventory
        iv.items[2,1]=Item(4,40305,iv.next_uid,1)
        iv.next_uid+=1
        game.world_file=Path('synthetic-unused-world.json')
        before=snapshot(iv,game.ground_loot,game.magazine,game.selected_slot)
        request=part_request(iv.items[2,1].uid,2,1,iv.items[1,1].uid,3,2)
        with patch.object(game,'save_state',side_effect=OSError('synthetic write failure')):
            with self.assertRaises(OSError):game.handle(0x3e80,request)
        self.assertEqual(snapshot(game.inventory,game.ground_loot,game.magazine,game.selected_slot),before)


if __name__=='__main__':unittest.main()
