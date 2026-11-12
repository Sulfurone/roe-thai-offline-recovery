import struct
import unittest
from dataclasses import replace
from offline_bots import BotRoster,POSITION_MARKER
from offline_combat import BotCombat,death_packet,hit_feedback
from offline_gameplay import OfflineGameplay
from offline_vitals import Vitals
from offline_visibility import StaticVisibility
from test_hit_reports import hit_body


def fixture():
    game=OfflineGameplay(inventory_enabled=True,vitals_enabled=True)
    game.actor_ready=True
    game.player_position=(325800,271700,6500)
    profile=struct.pack('>IIQI',3,1,1,12)+b'OfflineBot1\0'+POSITION_MARKER
    bots=BotRoster(profile)
    uid=0x1000000001100
    bots.actors[uid]=dict(origin=(326000,271700,6500),position=(326000,271700,6500),sequence=1)
    bots.vitals[uid]=Vitals(2*BotCombat.DAMAGE,1000)
    return game,bots,BotCombat(game,bots),uid


def shoot(game,combat,now=100,flag=0,serial=0,z=6600):
    body=struct.pack('>6fIB',325800,271700,z,326800,271700,z,serial,flag)
    before=game.magazine
    game.handle(0x11d3,body)
    return combat.record_shot(body,before,now)


class CombatTests(unittest.TestCase):
    def test_shotgun_shell_accepts_native_pellet_collision_once(self):
        game,bots,combat,uid=fixture()
        game.inventory.items[1,1]=replace(game.inventory.items[1,1],template=10403)
        game.set_weapon_magazine((1,1),5)
        bots.actors[uid]['position']=(326225,271700,6500)
        self.assertTrue(shoot(game,combat,serial=39))
        report=hit_body(shot_serial=39,target=(326225,271700,6500),impact=(326222,271712,6600))
        self.assertEqual([mid for mid,_ in combat.handle(report,100.01)],[0x1069,0x11eb])
        for sequence in range(38,45):
            self.assertEqual(combat.handle(struct.pack('>I',sequence)+report[4:],100.02),[])
        self.assertEqual(game.magazine,4)
        self.assertEqual(bots.vitals[uid].current,BotCombat.DAMAGE)

    def test_long_ray_uses_weapon_drop_and_recently_displayed_body(self):
        game,bots,combat,uid=fixture()
        game.inventory.items[1,1]=replace(game.inventory.items[1,1],template=10302)
        game.set_weapon_magazine((1,1),25)
        combat.visibility=StaticVisibility(FlatTerrain(),[])
        actor=bots.actors[uid]
        actor['position']=(339800,271700,6500)
        combat.tick(99.8)
        actor['position']=(339800,271800,6500)
        # At 140 m the 350 m/s round falls ~79 cm. The straight ray
        # passes above the model and its current position is 1 m off line.
        self.assertTrue(shoot(game,combat,serial=3,z=6720))
        self.assertEqual(combat.tick(100.5),[])
        self.assertEqual([mid for mid,_ in combat.tick(100.7)],[0x1069,0x11eb])
        self.assertAlmostEqual(combat.last_event['distance_m'],140,delta=1)
        self.assertTrue(shoot(game,combat,101,serial=4,z=6720))
        self.assertEqual(combat.tick(102),[])
        self.assertEqual(bots.vitals[uid].current,BotCombat.DAMAGE)

    def test_missing_client_collision_still_confirms_a_close_or_long_clear_hit(self):
        for distance in (200,14000):
            game,bots,combat,uid=fixture()
            target=(325800+distance,271700,6500)
            bots.actors[uid]['position']=target
            combat.visibility=StaticVisibility(FlatTerrain(),[])
            self.assertTrue(shoot(game,combat,serial=12))
            self.assertEqual(combat.tick(100.24),[])
            replies=combat.tick(101)
            self.assertEqual([mid for mid,_ in replies],[0x1069,0x11eb])
            self.assertEqual(combat.last_event['source'],'local_ray')
            report=hit_body(shot_serial=12,target=target,impact=(*target[:2],6600))
            self.assertEqual(combat.handle(report,101.01),[])
            self.assertEqual(combat.tick(101.02),[])
            self.assertEqual(bots.vitals[uid].current,BotCombat.DAMAGE)

    def test_fallback_rejects_misses_blocked_rays_and_unloaded_bots(self):
        for reason in ('miss','blocked','unloaded'):
            game,bots,combat,uid=fixture()
            bots.actors[uid]['position']=(331800,271800 if reason=='miss' else 271700,6500)
            bounds=[(330000,271700,6600,50)] if reason=='blocked' else []
            combat.visibility=StaticVisibility(FlatTerrain(),bounds)
            if reason=='unloaded':bots.streamed=True
            self.assertTrue(shoot(game,combat,serial=12))
            self.assertEqual(combat.tick(101),[])
            self.assertEqual(bots.vitals[uid].current,2*BotCombat.DAMAGE)

    def test_native_report_wins_before_delayed_fallback(self):
        game,bots,combat,uid=fixture()
        combat.visibility=StaticVisibility(FlatTerrain(),[])
        self.assertTrue(shoot(game,combat))
        self.assertEqual([mid for mid,_ in combat.handle(hit_body(),100.1)],[0x1069,0x11eb])
        self.assertEqual(combat.last_event['source'],'client_collision')
        self.assertEqual(combat.tick(101),[])

    def test_close_hip_fire_and_distant_hits_match_serial_and_emit_native_feedback(self):
        for distance in (40,2469,14000):
            game,bots,combat,uid=fixture()
            target=(325800+distance,271700,6500)
            bots.actors[uid]['position']=(target[0]+130,target[1],target[2])
            self.assertTrue(shoot(game,combat,serial=11))
            self.assertTrue(shoot(game,combat,100.05,serial=12))
            hit=dict(shooter=(325780,271720,6450),target=target,
                     impact=(target[0],target[1],6600))
            self.assertEqual(combat.handle(hit_body(shot_serial=13,**hit),100.1),[])
            self.assertEqual(combat.handle(hit_body(shot_serial=12,muzzle=(325800,271708,6600),**hit),100.1),[])
            feedback=combat.handle(hit_body(shot_serial=12,**hit),100.1)
            self.assertEqual([mid for mid,_ in feedback],[0x1069,0x11eb])
            self.assertEqual(feedback[1],hit_feedback(game.actor_uid,uid,(0,0,100),2,BotCombat.DAMAGE,False))
            self.assertEqual([shot.serial for shot in combat.shots],[11])
            self.assertEqual(combat.handle(struct.pack('>I',38)+hit_body(shot_serial=12,**hit)[4:],100.2),[])

    def test_two_consumed_bullets_kill_once_and_dead_queries_do_not_revive(self):
        game,bots,combat,uid=fixture()
        self.assertTrue(shoot(game,combat))
        first=combat.handle(hit_body()+bytes(8),100.1)
        self.assertEqual([m for m,b in first],[0x1069,0x11eb])
        self.assertEqual(bots.vitals[uid].current,BotCombat.DAMAGE)
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
            self.assertEqual(bots.vitals[uid].current,2*BotCombat.DAMAGE)

    def test_report_needs_the_consumed_shot_line_and_each_ticket_is_single_use(self):
        game,bots,combat,uid=fixture()
        self.assertTrue(shoot(game,combat))
        combat.shots[0].aim=(325800,273000,6600)
        self.assertEqual(combat.handle(hit_body(),100.1),[])
        combat.shots[0].aim=(327000,271700,6600)
        self.assertEqual(len(combat.handle(hit_body(),100.2)),2)
        self.assertEqual(combat.handle(struct.pack('>I',38)+hit_body()[4:],100.3),[])
        self.assertEqual(bots.vitals[uid].current,BotCombat.DAMAGE)

    def test_malformed_reports_and_feedback_fields_fail_without_damage(self):
        game,bots,combat,uid=fixture()
        self.assertTrue(shoot(game,combat))
        self.assertEqual(combat.handle(hit_body()[:-1],100.1),[])
        self.assertEqual(bots.vitals[uid].current,2*BotCombat.DAMAGE)
        for owner in (0,-1,2**64,True):
            with self.assertRaises(ValueError):death_packet(owner)
        for values in ((0,uid,(0,0,0),1,20,False),(256,uid,(0,0,0),1,-1,False),
                       (256,uid,(0,0,0),1,20,1),(256,uid,(0.,0,0),1,20,False)):
            with self.assertRaises(ValueError):hit_feedback(*values)


class FlatTerrain:
    def height_at(self,x,y):return 6500


if __name__=='__main__':unittest.main()
