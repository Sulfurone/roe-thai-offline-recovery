import struct
import unittest
from unittest.mock import patch
from dataclasses import replace
from offline_gameplay import OfflineGameplay


def game():
    g=OfflineGameplay(inventory_enabled=True,magazine=19,reserve=7,reload_seconds=2.5)
    g.actor_ready=True
    return g


class ReloadTimingTests(unittest.TestCase):
    def begin(self,g,now=100):
        with patch('time.monotonic',return_value=now):
            return g.handle(0x49c,struct.pack('>I',1))

    def test_wait_conserves_ammo_and_duplicate_start_does_not_extend_deadline(self):
        g=game()
        self.assertEqual([m for m,b in self.begin(g)],[0x49d])
        self.assertEqual((g.magazine,g.inventory.reserve_for(30001)),(19,7))
        self.begin(g,102)
        self.assertEqual(g.pending_reload['deadline'],102.5)
        self.assertEqual(g.tick(102.49),[])
        self.assertEqual([m for m,b in g.tick(102.5)],[0x4a0,0x3e82])
        self.assertEqual((g.magazine,g.inventory.reserve_for(30001)),(26,0))
        self.assertEqual(g.tick(105),[])
        self.assertEqual([m for m,b in self.begin(g,106)],[0x49d])

    def test_switch_fire_death_seating_and_item_replacement_cancel_without_transfer(self):
        for reason in ('switch','fire','death','seat','replace','remove'):
            g=game();self.begin(g)
            if reason=='switch':g.handle(0x49e,bytes(4))
            if reason=='fire':g.handle(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,1,0))
            if reason=='death':g.vitals.damage(1000)
            if reason=='seat':g.seated=True
            if reason=='replace':g.inventory.items[1,1]=replace(g.inventory.items[1,1],uid=99999)
            if reason=='remove':del g.inventory.items[1,1]
            self.assertEqual(g.tick(103),[])
            self.assertIsNone(g.pending_reload)
            self.assertEqual(g.inventory.reserve_for(30001),7)

    def test_reserve_is_rechecked_at_completion_instead_of_reserved_or_created(self):
        g=game();self.begin(g)
        g.inventory.consume(5,30001)
        self.assertEqual([m for m,b in g.tick(103)],[0x4a0,0x3e82])
        self.assertEqual((g.magazine,g.inventory.reserve_for(30001)),(21,0))

    def test_new_request_after_cancel_waits_from_its_own_start(self):
        g=game();self.begin(g)
        g.handle(0x49e,bytes(4));g.handle(0x49e,struct.pack('>I',1))
        self.begin(g,102)
        self.assertEqual(g.tick(103),[])
        self.assertEqual([m for m,b in g.tick(104.5)],[0x4a0,0x3e82])

    def test_stop_or_malformed_shot_does_not_cancel_new_reload(self):
        g=game();self.begin(g)
        g.handle(0x11d3,b'')
        g.handle(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,1,1))
        g.handle(0x11d3,struct.pack('>6fIB',float('nan'),2,3,1,102,3,1,0))
        self.assertEqual(g.pending_reload['deadline'],102.5)
        self.assertEqual([m for m,b in g.tick(103)],[0x4a0,0x3e82])

    def test_recovered_magazine_duration_and_r870_round_count(self):
        g=game();g.reload_seconds=0;g.reload_original=True
        self.begin(g)
        self.assertEqual(g.tick(101.89),[])
        self.assertEqual([m for m,b in g.tick(101.91)],[0x4a0,0x3e82])
        self.assertEqual((g.magazine,g.inventory.reserve_for(30001)),(26,0))
        for reserve,wait,loaded in ((5,4.06,5),(2,1.96,2)):
            g=game();g.reload_seconds=0;g.reload_original=True
            g.inventory.items={key:replace(item,template=10401 if key==(1,1) else 30004,
                    count=1 if key==(1,1) else reserve)
                for key,item in g.inventory.items.items()}
            g.set_weapon_magazine((1,1),0)
            self.begin(g)
            self.assertEqual(g.tick(100+wait-.01),[])
            self.assertEqual([m for m,b in g.tick(100+wait+.01)],[0x4a0,0x3e82])
            self.assertEqual((g.magazine,g.inventory.reserve_for(30004)),(loaded,0))

    def test_extra_shells_acquired_during_reload_cannot_skip_their_loading_time(self):
        g=game();g.reload_seconds=0;g.reload_original=True
        g.inventory.items={key:replace(item,template=10401 if key==(1,1) else 30004,
                count=1 if key==(1,1) else 2) for key,item in g.inventory.items.items()}
        g.set_weapon_magazine((1,1),0)
        self.begin(g)
        for key,item in list(g.inventory.items.items()):
            if item.template==30004:g.inventory.items[key]=replace(item,count=5)
        g.tick(102)
        self.assertEqual((g.magazine,g.inventory.reserve_for(30004)),(2,3))
        self.begin(g,103)
        self.assertEqual(g.tick(105.65),[])
        g.tick(105.67)
        self.assertEqual((g.magazine,g.inventory.reserve_for(30004)),(5,0))


if __name__=='__main__':unittest.main()
