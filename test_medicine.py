import struct
import unittest
from unittest.mock import patch
from offline_inventory import OfflineInventory,Item
from offline_vitals import Vitals
from offline_medicine import MedicineUse,MEDICINES
from offline_gameplay import OfflineGameplay
from test_offline_motion import move_body
from offline_motion import actor_actions


def request(slot=3):return struct.pack('>BBHBIB',3,2,slot,0,0,1)


class MedicineTests(unittest.TestCase):
    def prepare(self,template=70001,current=400,count=2):
        inventory=OfflineInventory()
        inventory.items[2,3]=Item(7,template,0x100110,count)
        return MedicineUse(),inventory,Vitals(current,1000)

    def test_original_times_quantities_and_full_heal_cap(self):
        for template,seconds,expected in ((70001,3,500),(70002,6,900),(70003,8,1000)):
            use,inventory,hp=self.prepare(template)
            self.assertEqual(use.begin(request(),inventory,hp,True,100),[inventory.reply(3,template=template)])
            self.assertEqual(use.tick(inventory,hp,256,True,100+seconds-.001),[])
            self.assertEqual(inventory.items[2,3].count,2)
            replies=use.tick(inventory,hp,256,True,100+seconds)
            self.assertEqual([m for m,b in replies],[0x3e82,0x1069])
            self.assertEqual(hp.current,expected)
            self.assertEqual(inventory.items[2,3].count,1)
            self.assertEqual(use.tick(inventory,hp,256,True,999),[])

    def test_duplicate_start_and_final_item_are_not_double_spent(self):
        use,inventory,hp=self.prepare(count=1)
        use.begin(request()+bytes(8),inventory,hp,True,100)
        self.assertEqual(use.begin(request(),inventory,hp,True,102),[])
        self.assertEqual(use.pending['deadline'],103)
        use.tick(inventory,hp,256,True,103)
        self.assertNotIn((2,3),inventory.items)
        self.assertEqual(use.begin(request(),inventory,hp,True,103),[inventory.reply(3,1)])

    def test_full_health_dead_unready_and_wrong_slot_do_not_consume(self):
        for current,allowed,slot in ((1000,True,3),(0,True,3),(400,False,3),(400,True,4)):
            use,inventory,hp=self.prepare(current=current)
            self.assertEqual(use.begin(request(slot),inventory,hp,allowed,100),[inventory.reply(3,1)])
            self.assertIsNone(use.pending)
            self.assertEqual(inventory.items[2,3].count,2)

    def test_removed_source_or_seating_or_death_cancels_without_free_heal(self):
        for cause in ('removed','seated','dead'):
            use,inventory,hp=self.prepare()
            use.begin(request(),inventory,hp,True,100)
            if cause=='removed':del inventory.items[2,3]
            if cause=='dead':hp.damage(1000)
            before=hp.current
            self.assertEqual(use.tick(inventory,hp,256,cause!='seated',104),[])
            self.assertEqual(hp.current,before)
            self.assertIsNone(use.pending)

    def test_gameplay_routes_and_persists_completion_before_reply(self):
        g=OfflineGameplay(inventory_enabled=True,vitals_enabled=True)
        g.actor_ready=g.vitals_sent=True
        g.vitals.damage(600)
        g.inventory.items[2,3]=Item(7,70003,0x100110,1)
        with patch('offline_medicine.time.monotonic',return_value=100):
            self.assertEqual(g.handle(0x3e80,request()),[g.inventory.reply(3,template=70003)])
        with patch.object(g,'save_state') as saved:
            self.assertEqual([m for m,b in g.tick(108)],[0x3e82,0x1069])
            saved.assert_called_once()
        self.assertEqual(g.vitals.current,1000)

    def test_native_cancel_can_be_in_first_batched_point_and_preserves_hp_and_item(self):
        g=OfflineGameplay(inventory_enabled=True,vitals_enabled=True)
        g.actor_ready=g.vitals_sent=True
        g.vitals.damage(600)
        g.inventory.items[2,3]=Item(7,70003,0x100110,1)
        with patch('offline_medicine.time.monotonic',return_value=100):
            g.handle(0x3e80,request())
        body=bytearray(move_body(10,[(325800,271700,6501)]*2))
        body[17]=20
        self.assertEqual(actor_actions(body),(20,0))
        g.handle(0x2a,bytes(body))
        self.assertTrue(g.last_medicine_cancel)
        self.assertIsNone(g.medicine.pending)
        self.assertEqual(g.tick(110),[])
        self.assertEqual((g.vitals.current,g.inventory.items[2,3].count),(400,1))
        g.handle(0x2a,bytes(body))
        self.assertFalse(g.last_medicine_cancel)
        with patch('offline_medicine.time.monotonic',return_value=111):
            self.assertEqual(g.handle(0x3e80,request()),[g.inventory.reply(3,template=70003)])
        g.tick(119)
        self.assertEqual(g.vitals.current,1000)
        self.assertNotIn((2,3),g.inventory.items)

    def test_non_action_fields_or_malformed_trajectory_do_not_cancel_treatment(self):
        base=move_body(10,[(325800,271700,6501)]*2)
        candidates=[base,struct.pack('>I3i',20,325800,271700,6501)]
        for offset in (16,18,19):
            body=bytearray(base);body[offset]=20;candidates.append(bytes(body))
        body=bytearray(base);body[17]=20
        candidates.extend((bytes(body)[:-1],bytes(body)+b'\0'))
        for body in candidates:
            g=OfflineGameplay(inventory_enabled=True,vitals_enabled=True)
            g.actor_ready=g.vitals_sent=True
            g.vitals.damage(600)
            g.inventory.items[2,3]=Item(7,70001,0x100110,2)
            with patch('offline_medicine.time.monotonic',return_value=100):g.handle(0x3e80,request())
            g.handle(0x2a,body)
            self.assertFalse(g.last_medicine_cancel)
            self.assertIsNotNone(g.medicine.pending)
            g.tick(103)
            self.assertEqual((g.vitals.current,g.inventory.items[2,3].count),(500,1))


if __name__=='__main__':unittest.main()
