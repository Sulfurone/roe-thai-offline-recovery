import struct
import unittest
from offline_vitals import Vitals
from offline_gameplay import OfflineGameplay,TYPED_ACTOR_UID


class VitalsTests(unittest.TestCase):
    def test_initialization_waits_for_actor_and_never_refills_on_later_ticks(self):
        game=OfflineGameplay(vitals_enabled=True,actor_uid=TYPED_ACTOR_UID)
        self.assertEqual(game.tick(100),[])
        game.actor_ready=True
        self.assertEqual(game.tick(101),[game.vitals.packet(TYPED_ACTOR_UID)])
        game.vitals.damage(25)
        self.assertEqual(game.tick(102),[])
        self.assertEqual(game.vitals.current,975)

    def test_damage_healing_bounds_and_zero_is_not_resurrected(self):
        hp=Vitals(100,100)
        self.assertEqual(hp.damage(25),25)
        self.assertEqual(hp.heal(10),10)
        self.assertEqual(hp.heal(50),15)
        self.assertEqual(hp.damage(1000),100)
        self.assertEqual(hp.heal(1000),0)
        for value in (-1,True,1.5):
            with self.assertRaises(ValueError):hp.damage(value)
            with self.assertRaises(ValueError):hp.heal(value)
        with self.assertRaises(ValueError):Vitals(101,100)

    def test_default_uses_original_medical_full_health_scale(self):
        hp=Vitals()
        self.assertEqual((hp.current,hp.maximum),(1000,1000))
        hp.damage(600)
        self.assertEqual(hp.heal(500),500)
        self.assertEqual(hp.current,900)

    def test_delta_addresses_current_and_maximum_without_motion_attributes(self):
        message,body=Vitals(73,100).packet(TYPED_ACTOR_UID)
        self.assertEqual(message,0x1069)
        self.assertEqual(struct.unpack_from('>QBB',body),(TYPED_ACTOR_UID,0,1))
        self.assertEqual(struct.unpack_from('>BII',body,10),(0,73,100))
        self.assertEqual(len(body),19)


if __name__=='__main__':unittest.main()
