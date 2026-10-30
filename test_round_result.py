import unittest
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
    def test_no_player_no_result_and_invalid_roster_rejected(self):
        g,b,r=self.make();g.vitals.damage(1000);self.assertFalse(r.tick())
        with self.assertRaises(ValueError):LocalRoundResult(g,SimpleNamespace(count=0))

if __name__=='__main__':unittest.main()
