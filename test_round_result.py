import unittest
import struct
from types import SimpleNamespace
from offline_gameplay import OfflineGameplay
from offline_vitals import Vitals
from offline_round_result import LocalRoundResult
from control_actions import ControlSession

class LocalRoundTests(unittest.TestCase):
    def make(self):
        game=OfflineGameplay(); bots=SimpleNamespace(count=2,actors={},vitals={})
        return game,bots,LocalRoundResult(game,bots)
    def test_waits_for_full_roster_and_is_idempotent_after_victory(self):
        g,b,r=self.make();g.actor_ready=True
        b.actors[1]={};b.vitals[1]=Vitals(current=0)
        self.assertFalse(r.tick());self.assertEqual(r.state,'waiting')
        b.actors[2]={};b.vitals[2]=Vitals()
        self.assertFalse(r.tick());self.assertEqual(r.state,'playing')
        b.vitals[2].damage(1000);self.assertTrue(r.tick());self.assertEqual(r.state,'won')
        self.assertEqual((r.placement,r.size),(1,3))
        self.assertFalse(r.tick());g.vitals.damage(1000);self.assertFalse(r.tick())
    def test_missing_registered_actor_cannot_grant_victory(self):
        g,b,r=self.make();g.actor_ready=True
        b.actors={1:{},2:{}};b.vitals={1:Vitals(),2:Vitals()}
        r.tick();b.vitals[1].damage(1000);b.vitals[2].damage(1000);del b.actors[2]
        self.assertFalse(r.tick());self.assertEqual(r.state,'playing')
    def test_player_death_precedes_victory_and_snapshot_exposes_result(self):
        g,b,r=self.make();g.actor_ready=True
        b.actors={1:{},2:{}};b.vitals={1:Vitals(current=0),2:Vitals(current=0)}
        g.vitals.damage(1000);self.assertTrue(r.tick());self.assertEqual(r.state,'lost')
        control=ControlSession(g);control.round_result=r
        self.assertEqual(control.snapshot()['round_state'],'lost')

    def test_placement_counts_pending_bots_and_freezes_at_death(self):
        game=OfflineGameplay();game.actor_ready=True
        bots=SimpleNamespace(count=63,actors={},vitals={1:Vitals(current=0),2:Vitals()})
        result=LocalRoundResult(game,bots)
        game.vitals.damage(1000)
        self.assertTrue(result.tick())
        bots.vitals[2].damage(1000)
        self.assertFalse(result.tick())
        control=ControlSession(game);control.round_result=result
        snapshot=control.snapshot()
        self.assertEqual((snapshot['round_state'],snapshot['round_placement'],snapshot['round_size']),
                         ('lost',63,64))
    def test_no_player_no_result_and_invalid_roster_rejected(self):
        g,b,r=self.make();g.vitals.damage(1000);self.assertFalse(r.tick())
        with self.assertRaises(ValueError):LocalRoundResult(g,SimpleNamespace(count=0))

    def test_thai_outcome_messages_carry_matching_room_and_placement(self):
        game,bots,result=self.make()
        self.assertEqual(result.native_messages(1,b'Test\0'),[])
        game.actor_ready=True
        game.vitals.damage(1000)
        self.assertTrue(result.tick())
        name=b'Test\0'
        messages=result.native_messages(17,name,killer_uid=34,killer_name=b'OfflineBot2')
        self.assertEqual([mid for mid,_ in messages],[0xd77,0x106e,0xd62])
        self.assertEqual(struct.unpack_from('>IQ',messages[0][1]),(0,17))
        self.assertEqual(struct.unpack_from('>QI',messages[1][1]),(34,12))
        outcome=messages[-1][1]
        self.assertEqual(struct.unpack_from('>QQI',outcome),(17,game.actor_uid,len(name)))
        self.assertEqual(struct.unpack_from('>4I',outcome,20+len(name)),(3,3,3,3))
        self.assertEqual(outcome[-1],0)

if __name__=='__main__':unittest.main()
