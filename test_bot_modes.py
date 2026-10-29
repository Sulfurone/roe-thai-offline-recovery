"""Behavior transitions and the real session mailbox, using synthetic actors."""
import json
import math
import tempfile
import unittest
from unittest.mock import patch

from test_bot_ai import setup
from control_actions import ControlSession
from offline_control import ControlHub,validate_command
from ingame_bridge import IngameMailbox
from ingame_client import MailboxClient,bot_hint


class BotModeTests(unittest.TestCase):
    def test_fire_stop_is_delayed_once_and_pausing_cancels_fire_without_refilling(self):
        g,bots,ai,uid=setup()
        ai.tick(100)
        g.accept_self_position(g.player_position,100.8)
        shot=ai.tick(100.8)
        self.assertEqual([b[-1] for m,b in shot if m==0x11d4],[0])
        self.assertNotIn(0x11d4,[m for m,b in ai.tick(100.85)])
        self.assertEqual([b[-1] for m,b in ai.tick(100.93) if m==0x11d4],[1])
        self.assertNotIn(0x11d4,[m for m,b in ai.tick(100.99)])
        ai.brains[uid].firing=(bots.actors[uid]['position'],g.player_position)
        before=(ai.brains[uid].magazine,ai.brains[uid].reserve)
        self.assertEqual([b[-1] for m,b in ai.set_mode('target')],[1])
        g.accept_self_position(g.player_position,101)
        point=bots.actors[uid]['position']
        self.assertEqual(ai.tick(101),[])
        self.assertEqual(bots.actors[uid]['position'],point)
        self.assertEqual((ai.brains[uid].magazine,ai.brains[uid].reserve),before)
        ai.set_mode('patrol')
        g.accept_self_position(g.player_position,101.5)
        packets=ai.tick(101.5)
        self.assertIn(0x27,[m for m,b in packets])
        self.assertNotIn(0x11d4,[m for m,b in packets])

    def test_switching_to_combat_requires_new_reaction_and_dead_bot_stays_dead(self):
        g,bots,ai,uid=setup()
        ai.set_mode('target');ai.tick(100)
        ai.set_mode('combat')
        g.accept_self_position(g.player_position,101)
        self.assertEqual(ai.tick(101),[])
        g.accept_self_position(g.player_position,101.8)
        self.assertIn(0x11d4,[m for m,b in ai.tick(101.8)])
        bots.vitals[uid].current=0
        self.assertEqual([b[-1] for m,b in ai.tick(101.81) if m==0x11d4],[1])
        ai.set_mode('patrol');ai.set_mode('combat')
        g.accept_self_position(g.player_position,105)
        self.assertEqual(ai.tick(105),[])
        self.assertEqual(bots.vitals[uid].current,0)

    def test_reload_finishes_while_target_stale_and_never_refills_twice(self):
        g,bots,ai,uid=setup();ai.tick(100)
        brain=ai.brains[uid];brain.magazine=0;brain.reserve=7
        ai.tick(100.1)
        ai.tick(102)  # stale; used to lose the reload deadline
        self.assertEqual((brain.magazine,brain.reserve),(0,7))
        self.assertIn(0x547,[m for m,b in ai.tick(103.1)])
        self.assertEqual((brain.magazine,brain.reserve),(7,0))
        ai.tick(110)
        self.assertEqual((brain.magazine,brain.reserve),(7,0))

    def test_lost_target_search_uses_last_observation_and_expires(self):
        g,bots,ai,uid=setup();ai.tick(100)
        known=ai.brains[uid].last_known
        with patch.object(ai.visibility,'sight_clear',return_value=False),patch.object(ai,'walk_towards',return_value=[]) as walk:
            g.accept_self_position((300000,270000,6505),101)
            ai.tick(101)
            self.assertEqual(walk.call_args.args[1],known)
            g.accept_self_position((300000,270000,6505),106)
            ai.tick(106)
            self.assertIsNone(ai.brains[uid].last_known)
            self.assertNotEqual(walk.call_args.args[1],known)

    def test_aim_noise_is_bounded_and_does_not_adjust_during_reaction(self):
        g,bots,ai,uid=setup();ai.AIM_ERROR_DEGREES=1.2
        origin=(0,0,150);target=(6000,0,90)
        samples=[ai.aim_at(origin,target) for _ in range(40)]
        self.assertTrue(any(p[1]<0 for p in samples) and any(p[1]>0 for p in samples))
        for p in samples:self.assertLessEqual(abs(math.degrees(math.atan2(p[1],p[0]))),1.2)
        ai.tick(100);locked=ai.brains[uid].target
        g.accept_self_position((325800,271800,6505),100.4);ai.tick(100.4)
        self.assertEqual(ai.brains[uid].target,locked)

    def test_native_menu_round_trip_and_status_use_same_bot_state(self):
        g,bots,ai,uid=setup();ai.tick(100)
        control=ControlSession(g);control.peer_positions=bots.actors;control.bot_ai=ai
        with tempfile.TemporaryDirectory() as folder:
            mailbox=IngameMailbox(folder);hub=ControlHub()
            hub.update(**control.snapshot());mailbox.publish(hub.snapshot())
            client=MailboxClient(mailbox.directory)
            for mode in (0,1,2):
                client.send(dict(action='bots',mode=mode));mailbox.poll(hub)
                cmd=hub.take();self.assertEqual(cmd['mode'],mode)
                replies,message=control.execute(cmd);hub.finish(cmd['id'],'sent',message)
                hub.update(**control.snapshot());mailbox.publish(hub.snapshot());state=client.state()
                self.assertEqual(state['bot_mode'],ai.MODES[mode])
                self.assertIn('OfflineBot1',bot_hint(state))
                self.assertIn(f'HP {bots.vitals[uid].current}',bot_hint(state))
            self.assertEqual(json.loads(state['peers'])[0]['hp'],bots.vitals[uid].current)
        for command in ({'action':'bots','mode':3},{'action':'bots','mode':True},{'action':'bots','mode':1,'count':100}):
            with self.assertRaises(ValueError):validate_command(command)
        with self.assertRaises(ValueError):ControlSession(g).execute(dict(action='bots',mode=1))


if __name__=='__main__':unittest.main()
