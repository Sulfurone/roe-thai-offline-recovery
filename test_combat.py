import struct
import unittest
from offline_bots import BotRoster,POSITION_MARKER
from offline_combat import BotCombat,death_packet,hit_feedback
from offline_gameplay import OfflineGameplay
from offline_vitals import Vitals
from test_hit_reports import hit_body


def fixture():
    game=OfflineGameplay(inventory_enabled=True,vitals_enabled=True)
    game.actor_ready=True
    game.player_position=(325800,271700,6500)
    profile=struct.pack('>IIQI',3,1,1,12)+b'OfflineBot1\0'+POSITION_MARKER
    bots=BotRoster(profile)
    uid=0x1000000001100
    bots.actors[uid]=dict(origin=(326000,271700,6500),position=(326000,271700,6500),sequence=1)
    bots.vitals[uid]=Vitals(40,1000)
    return game,bots,BotCombat(game,bots),uid


def shoot(game,combat,now=100,flag=0):
    body=struct.pack('>6fIB',325800,271700,6600,327000,271700,6600,0,flag)
    before=game.magazine
    game.handle(0x11d3,body)
    return combat.record_shot(body,before,now)


class CombatTests(unittest.TestCase):
    def test_two_consumed_bullets_kill_once_and_dead_queries_do_not_revive(self):
        game,bots,combat,uid=fixture()
        self.assertTrue(shoot(game,combat))
        first=combat.handle(hit_body()+bytes(8),100.1)
        self.assertEqual([m for m,b in first],[0x1069,0x11eb])
        self.assertEqual(bots.vitals[uid].current,20)
        self.assertEqual(game.magazine,29)
        self.assertTrue(shoot(game,combat,100.2))
        self.assertEqual(combat.handle(hit_body(),100.3),[])
        self.assertEqual(combat.last_event['reason'],'duplicate')
        final=combat.handle(struct.pack('>I',38)+hit_body()[4:],100.4)
        self.assertEqual([m for m,b in final],[0x1069,0x11eb,0x533])
        self.assertEqual(final[-1],death_packet(uid))
        self.assertEqual(game.magazine,28)
        self.assertEqual(bots.vitals[uid].current,0)
        self.assertEqual(bots.damage(uid,20),[])
        self.assertEqual([m for m,b in bots.handle(0xbe6,struct.pack('>IIQ',3,1,uid))],[0xbe7,0x1069,0x533])
        self.assertEqual(bots.vitals[uid].current,0)
        bots.started=100
        self.assertEqual(bots.tick(object(),100.5),[])
        self.assertEqual([m for m,b in bots.tick(object(),101.5)],[0x565,0xbe7,0x1069,0x533])

    def test_unknown_dead_and_outside_target_reports_cannot_damage_a_peer(self):
        for kind in ('uid','dead','position','impact','origin','expired','no_shot'):
            game,bots,combat,uid=fixture()
            if kind!='no_shot':self.assertTrue(shoot(game,combat))
            body=bytearray(hit_body())
            if kind=='uid':struct.pack_into('>Q',body,4,999)
            if kind=='dead':bots.vitals[uid].damage(1000)
            if kind=='position':struct.pack_into('>i',body,37,300000)
            if kind=='impact':struct.pack_into('>f',body,50,326500)
            if kind=='origin':struct.pack_into('>i',body,12,300000)
            before=bots.vitals[uid].current
            self.assertEqual(combat.handle(bytes(body),104 if kind=='expired' else 100.1),[])
            self.assertEqual(bots.vitals[uid].current,before)
            self.assertFalse(combat.last_event['accepted'])

    def test_empty_stop_unready_dead_and_seated_shots_get_no_damage_ticket(self):
        for kind in ('empty','stop','unready','dead','seated'):
            game,bots,combat,uid=fixture()
            if kind=='empty':game.set_weapon_magazine((1,1),0)
            if kind=='unready':game.actor_ready=False
            if kind=='dead':game.vitals.damage(1000)
            if kind=='seated':game.seated=True
            self.assertFalse(shoot(game,combat,flag=int(kind=='stop')))
            self.assertEqual(combat.handle(hit_body(),100.1),[])
            self.assertEqual(bots.vitals[uid].current,40)

    def test_report_needs_the_consumed_shot_line_and_each_ticket_is_single_use(self):
        game,bots,combat,uid=fixture()
        self.assertTrue(shoot(game,combat))
        combat.shots[0].aim=(325800,273000,6600)
        self.assertEqual(combat.handle(hit_body(),100.1),[])
        combat.shots[0].aim=(327000,271700,6600)
        self.assertEqual(len(combat.handle(hit_body(),100.2)),2)
        self.assertEqual(combat.handle(struct.pack('>I',38)+hit_body()[4:],100.3),[])
        self.assertEqual(bots.vitals[uid].current,20)

    def test_malformed_reports_and_feedback_fields_fail_without_damage(self):
        game,bots,combat,uid=fixture()
        self.assertTrue(shoot(game,combat))
        self.assertEqual(combat.handle(hit_body()[:-1],100.1),[])
        self.assertEqual(bots.vitals[uid].current,40)
        for owner in (0,-1,2**64,True):
            with self.assertRaises(ValueError):death_packet(owner)
        for values in ((0,uid,(0,0,0),1,20,False),(256,uid,(0,0,0),1,-1,False),
                       (256,uid,(0,0,0),1,20,1),(256,uid,(0.,0,0),1,20,False)):
            with self.assertRaises(ValueError):hit_feedback(*values)


if __name__=='__main__':unittest.main()
