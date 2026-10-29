"""Local bullet protection, exact condition and conservative persistence."""
import struct
import unittest
from unittest.mock import patch

from offline_armour import absorb_bullet,local_region
from offline_inventory import Item,OfflineInventory,read_item,item_fields
from offline_world_state import snapshot,restore
from offline_ground_loot import OfflineGroundLoot
from test_bot_ai import setup


def put(iv,template,slot,condition=None):
    item=Item(20,template,iv.next_uid,1,durability=condition)
    iv.next_uid+=1;iv.items[1,slot]=item
    return item


class ArmourTests(unittest.TestCase):
    def test_only_equipped_corresponding_region_protects_and_partial_break_is_bounded(self):
        iv=OfflineInventory()
        helmet=put(iv,200103,10);vest=put(iv,201001,12,3)
        hit=absorb_bullet(iv,20,'torso')
        self.assertEqual((hit.damage,hit.absorbed,hit.before,hit.after),(17,3,3,0))
        self.assertEqual(iv.items[1,10],helmet)
        self.assertEqual(absorb_bullet(iv,20,'torso').damage,20)
        hit=absorb_bullet(iv,20,'head')
        self.assertEqual((hit.damage,hit.absorbed,iv.items[1,10].durability),(9,11,2289))
        before=dict(iv.items)
        self.assertEqual(absorb_bullet(iv,20,'limb').damage,20)
        self.assertEqual(iv.items,before)
        iv.items[2,3]=iv.items.pop((1,10))
        self.assertEqual(absorb_bullet(iv,20,'head').damage,20)
        self.assertEqual(iv.items[1,12].uid,vest.uid)

    def test_fresh_levels_use_original_defense_facts_as_local_percentages(self):
        for template,slot,region,remaining,hp_loss in (
                (200101,10,'head',794,14),(200102,10,'head',1492,12),(200103,10,'head',2289,9),
                (201001,12,'torso',1994,14),(201002,12,'torso',2192,12),(201003,12,'torso',2489,9)):
            iv=OfflineInventory();put(iv,template,slot)
            hit=absorb_bullet(iv,20,region)
            self.assertEqual((hit.damage,hit.after),(hp_loss,remaining))
            wire=iv.items[1,slot].wire()
            self.assertEqual(struct.unpack_from('>I',wire,30)[0],remaining)
            self.assertEqual(hit.damage+hit.absorbed,20)

    def test_condition_survives_transfer_ground_and_world_restore_without_repair(self):
        iv=OfflineInventory();item=put(iv,201003,12,7)
        iv.transfer((1,12),(2,2),1)
        self.assertEqual(iv.items[2,2].durability,7)
        iv.transfer((2,2),(1,12),1)
        self.assertEqual(iv.items[1,12],item)
        ground=OfflineGroundLoot();iv.weapon_magazines[iv.items[1,1].uid]=30
        ground.add(iv.items.pop((1,12)),(1000,2000,3000))
        inventory,world,_,_=restore(snapshot(iv,ground,30,1))
        self.assertEqual(list(world.stacks.values())[-1].item.durability,7)
        data=item_fields(item);self.assertEqual(read_item(data),item)
        data.pop('durability');self.assertIsNone(read_item(data).durability)
        for condition in (-1,2501,True,None):
            bad=dict(data,durability=condition)
            with self.assertRaises(ValueError):read_item(bad)
        with self.assertRaises(ValueError):read_item(dict(kind=3,template=30001,uid=99,count=1,durability=3))

    def test_ai_damage_updates_armour_hp_and_feedback_without_reloading_weapon(self):
        game,bots,ai,uid=setup();put(game.inventory,201002,12,10)
        p=game.player_position;impact=(p[0],p[1],p[2]+90)
        replies=ai.damage_player(uid,impact)
        self.assertEqual([m for m,b in replies],[0x3e82,0x1069,0x11eb])
        self.assertEqual((game.vitals.current,game.inventory.items[1,12].durability),(988,2))
        self.assertEqual(struct.unpack_from('>I',replies[-1][1],30)[0],12)
        replies=ai.damage_player(uid,impact)
        self.assertEqual((game.vitals.current,game.inventory.items[1,12].durability),(970,0))
        self.assertEqual([m for m,b in ai.damage_player(uid,impact)],[0x1069,0x11eb])
        self.assertEqual(game.vitals.current,950)
        game.vitals.damage(1000);before=game.inventory.items[1,12]
        self.assertEqual(ai.damage_player(uid,impact),[])
        self.assertEqual(game.inventory.items[1,12],before)

    def test_failed_durability_commit_does_not_spend_condition_or_change_hp(self):
        game,bots,ai,uid=setup();item=put(game.inventory,201001,12)
        p=game.player_position
        with patch.object(game,'save_state',side_effect=OSError('own test full disk')):
            with self.assertRaises(OSError):ai.damage_player(uid,(p[0],p[1],p[2]+90))
        self.assertEqual((game.vitals.current,game.inventory.items[1,12]),(1000,item))

    def test_local_hit_regions_do_not_guess_native_hit_part_numbers(self):
        feet=(1,2,300)
        self.assertEqual([local_region((1,2,300+h),feet) for h in (35,90,160)],['limb','torso','head'])
        with self.assertRaises(ValueError):absorb_bullet(OfflineInventory(),-1,'head')
        with self.assertRaises(ValueError):absorb_bullet(OfflineInventory(),20,2)


if __name__=='__main__':unittest.main()
