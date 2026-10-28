import struct
import unittest
from offline_gameplay import OfflineGameplay,TYPED_ACTOR_UID
from offline_inventory import Item
from offline_throwables import Throws


def start(template=50001,serial=37):
    return struct.pack('>I3iB3iB3iBII',template,325800,271700,6650,0,
                       10000,0,0,0,0,0,0,0,serial,3)


def finish(template=50001,serial=37,uids=()):
    return (struct.pack('>II',template,len(uids))+b''.join(struct.pack('>Q',u) for u in uids)
            +struct.pack('>3iBI',326000,271700,6500,0,serial))


class ThrowTests(unittest.TestCase):
    def game(self,template=50001,count=3):
        game=OfflineGameplay(inventory_enabled=True,throwables_enabled=True,actor_uid=TYPED_ACTOR_UID)
        game.actor_ready=True
        game.inventory.items[1,5]=Item(5,template,0x100110,count)
        return game

    def test_every_supported_type_consumes_once_and_completes_original_effect(self):
        for template in (50001,50002,50003):
            g=self.game(template)
            replies=g.handle(0x1004,start(template))
            self.assertEqual([m for m,b in replies],[0x1005,0x3e82])
            self.assertEqual(replies[0][1],struct.pack('>III',template,37,0))
            self.assertEqual(g.inventory.items[1,5].count,2)
            replies=g.handle(0x1007,finish(template,uids=(TYPED_ACTOR_UID,)))
            self.assertEqual([m for m,b in replies],[0x1008,0x1009])
            self.assertEqual(struct.unpack('>II3iBQI',replies[1][1]),
                             (template,37,326000,271700,6500,0,TYPED_ACTOR_UID,0))
            self.assertEqual(g.vitals.current,100)  # client actor list is not damage authority

    def test_retransmissions_never_double_spend_or_repeat_effect(self):
        g=self.game()
        g.handle(0x1004,start())
        self.assertEqual(g.handle(0x1004,start()),[(0x1005,struct.pack('>III',50001,37,0))])
        g.handle(0x1007,finish())
        self.assertEqual(g.handle(0x1007,finish()),[(0x1008,struct.pack('>III',50001,37,0))])
        self.assertEqual(g.inventory.items[1,5].count,2)

    def test_real_client_transport_tail_is_opaque_and_does_not_change_receipt(self):
        g=self.game()
        self.assertEqual([m for m,b in g.handle(0x1004,start()+b'\x18'*8)],[0x1005,0x3e82])
        self.assertEqual([m for m,b in g.handle(0x1004,start()+b'\x29'*8)],[0x1005])
        self.assertEqual([m for m,b in g.handle(0x1007,finish()+b'\x37'*8)],[0x1008,0x1009])
        self.assertEqual([m for m,b in g.handle(0x1007,finish()+b'\x48'*8)],[0x1008])
        self.assertEqual(g.inventory.items[1,5].count,2)

    def test_last_item_removed_and_other_stacks_preserved(self):
        g=self.game(count=1)
        g.inventory.items[2,4]=Item(5,50001,0x100111,5)
        replies=g.handle(0x1004,start())
        self.assertEqual(replies[0][0],0x1005)
        self.assertNotIn((1,5),g.inventory.items)
        self.assertEqual(g.inventory.items[2,4].count,5)

    def test_unready_seated_dead_and_missing_items_reject_without_mutation(self):
        for field,value in (('actor_ready',False),('seated',True),('vitals',None),('inventory',None)):
            g=self.game()
            if field=='vitals':g.vitals.damage(100)
            else:setattr(g,field,value)
            self.assertEqual(g.handle(0x1004,start())[0],(0x1005,struct.pack('>III',50001,37,1)))
            self.assertEqual(g.throws.active,{})

    def test_malformed_forged_and_mismatched_completion_is_rejected(self):
        g=self.game()
        before=g.inventory.snapshot(30,1)
        self.assertEqual(g.handle(0x1004,start()[:-1]),[])
        self.assertEqual(g.handle(0x1004,start(99999))[0][1][-4:],struct.pack('>I',1))
        self.assertEqual(g.handle(0x1007,finish())[0][1][-4:],struct.pack('>I',1))
        self.assertEqual(g.inventory.snapshot(30,1),before)
        g.handle(0x1004,start())
        self.assertEqual(g.handle(0x1004,start(50002))[0][1][-4:],struct.pack('>I',1))
        self.assertEqual(g.handle(0x1007,finish(50002))[0][1][-4:],struct.pack('>I',1))
        self.assertEqual(g.handle(0x1007,finish()+b'\0'),[])
        self.assertEqual(g.handle(0x1007,struct.pack('>II',50001,121)+bytes(17)),[])


if __name__=='__main__':unittest.main()
