import random
import struct
import tempfile
from pathlib import Path
import unittest

from offline_gameplay import OfflineGameplay
from offline_ground_loot import MAX_GROUND_STACKS
from offline_inventory import Item


def position(x,y,z):
    return struct.pack('>I3i',1,x,y,z)


class ScatterLootTests(unittest.TestCase):
    def ready(self,path=None,seed=7):
        game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,
                             world_file=path,scatter_loot=True)
        game.scatter_random=random.Random(seed)
        game.handle(0x2a,position(325800,271700,6488))
        return game

    def test_first_report_anchors_and_600m_travel_spawns_a_cluster(self):
        game=self.ready()
        self.assertEqual(len(game.ground_loot.stacks),1)
        replies=game.handle(0x2a,position(325800,271700+60000,6488))
        self.assertEqual([message for message,_ in replies],[0x821,0x821])
        self.assertEqual(len(game.ground_loot.stacks),3)
        weapon,ammo=sorted(game.ground_loot.stacks.values(),key=lambda s:s.entity)[-2:]
        kinds={stack.item.kind for stack in (weapon,ammo)}
        self.assertEqual(kinds,{1,3})
        for stack in (weapon,ammo):
            self.assertEqual(stack.position[2],6488)
            self.assertLessEqual(abs(stack.position[0]-325800),8000)
            self.assertLessEqual(abs(stack.position[1]-(271700+60000)),8000)
        self.assertEqual(weapon.magazine,game.ground_loot.stacks[weapon.entity].magazine)
        self.assertTrue(40<=ammo.item.count<=60)
        self.assertLess(weapon.item.uid,game.inventory.next_uid)
        self.assertLess(ammo.item.uid,game.inventory.next_uid)

    def test_short_travel_and_airborne_positions_do_not_scatter(self):
        game=self.ready()
        game.handle(0x2a,position(325800,271700+30000,6488))
        self.assertEqual(len(game.ground_loot.stacks),1)
        self.assertEqual(game.handle(0x2a,position(325800,271700+60000,30000)),[])
        self.assertEqual(len(game.ground_loot.stacks),1)
        # The airborne report did not move the anchor.
        self.assertEqual(game.handle(0x2a,position(325800,271700+60000,6488))[0][0],0x821)
        self.assertEqual(len(game.ground_loot.stacks),3)

    def test_scattering_stops_when_the_ground_is_full(self):
        game=self.ready()
        while len(game.ground_loot.stacks)<MAX_GROUND_STACKS-1:
            uid=game.inventory.next_uid
            game.inventory.next_uid+=1
            game.ground_loot.add(Item(3,30001,uid,60),(325900,271700,6488))
        self.assertEqual(game.handle(0x2a,position(325800,271700+60000,6488)),[])
        self.assertEqual(len(game.ground_loot.stacks),MAX_GROUND_STACKS-1)

    def test_scattered_clusters_persist_across_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'world.json'
            game=self.ready(path)
            game.handle(0x2a,position(325800,271700+60000,6488))
            saved=dict(game.ground_loot.stacks)
            reopened=self.ready(path)
            self.assertEqual(reopened.ground_loot.stacks,saved)
            # The anchor is fresh after a restart; 600m more spawns again.
            self.assertEqual(reopened.handle(0x2a,position(325800,271700+120000,6488))[0][0],0x821)
            self.assertEqual(len(reopened.ground_loot.stacks),5)


if __name__=='__main__':unittest.main()
