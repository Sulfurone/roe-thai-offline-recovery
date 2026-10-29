import struct
import unittest
from unittest.mock import patch

from offline_blast import BlastCombat
from offline_bots import BotRoster,POSITION_MARKER
from offline_gameplay import OfflineGameplay
from offline_inventory import Item
from offline_visibility import StaticVisibility
from offline_vitals import Vitals
from test_throwables import start,finish


class Flat:
    def height_at(self,x,y):return 6500


def setup(points=((0,0,6505),(500,0,6505),(2000,0,6505))):
    game=OfflineGameplay(inventory_enabled=True,vitals_enabled=True,throwables_enabled=True)
    game.actor_ready=True
    game.player_position=(-3000,0,6505)
    game.inventory.items[1,5]=Item(5,50001,0x100110,3)
    profile=struct.pack('>IIQI',3,1,1,12)+b'OfflineBot1\0'+POSITION_MARKER
    bots=BotRoster(profile,max(1,len(points)))
    for i,point in enumerate(points):
        uid=0x1000000001100+i
        bots.actors[uid]=dict(origin=point,position=point,sequence=1)
        bots.vitals[uid]=Vitals()
    return game,bots,BlastCombat(game,bots,StaticVisibility(Flat(),[]))


def release(game,endpoint=(0,0,6505),serial=37,uids=()):
    begin=bytearray(start(serial=serial))
    struct.pack_into('>3i',begin,4,*game.player_position[:2],game.player_position[2]+145)
    end=bytearray(finish(serial=serial,uids=uids))
    struct.pack_into('>3i',end,8+8*len(uids),*endpoint)
    with patch('time.monotonic',return_value=100):
        game.handle(0x1004,bytes(begin))
        packets=game.handle(0x1007,bytes(end))
    return game.throws.take_completion(),packets,bytes(end)


class BlastTests(unittest.TestCase):
    def test_owned_near_targets_take_falloff_damage_and_die_without_uid_list_authority(self):
        game,bots,blast=setup()
        far=max(bots.actors)
        event,original,_=release(game,uids=(far,))
        self.assertEqual([m for m,b in original],[0x1008,0x1009])
        packets=blast.complete(event,100)
        self.assertEqual([hp.current for hp in bots.vitals.values()],[0,331,1000])
        self.assertEqual([m for m,b in packets],[0x1069,0x533,0x1069])
        self.assertEqual(game.vitals.current,1000)
        self.assertEqual(blast.events[-1]['affected'],2)

    def test_completion_and_transport_replays_cannot_damage_again(self):
        game,bots,blast=setup()
        event,_,wire=release(game)
        blast.complete(event,100)
        before=[hp.current for hp in bots.vitals.values()]
        self.assertEqual(blast.complete(event,101),[])
        self.assertEqual(blast.events[-1]['reason'],'duplicate')
        with patch('time.monotonic',return_value=101):
            self.assertEqual(game.handle(0x1007,wire+bytes(8)),[(0x1008,struct.pack('>3I',50001,37,0))])
        self.assertIsNone(game.throws.take_completion())
        self.assertEqual([hp.current for hp in bots.vitals.values()],before)

    def test_static_wall_blocks_blast_and_terrain_does_not_act_as_a_roof_floor(self):
        game,bots,blast=setup(((500,0,6505),))
        event,_,_=release(game)
        blast.visibility=StaticVisibility(Flat(),[(250,0,6580,150)])
        self.assertEqual(blast.complete(event,100),[])
        self.assertEqual(next(iter(bots.vitals.values())).current,1000)
        self.assertEqual(blast.events[-1]['affected'],0)

    def test_suicide_uses_hp_and_death_and_cancels_pending_medicine(self):
        game,bots,blast=setup(())
        game.vitals.current=40
        game.medicine.pending=dict(uid=999,template=70001,deadline=105)
        event,_,_=release(game,game.player_position)
        self.assertEqual([m for m,b in blast.complete(event,100)],[0x1069,0x533])
        self.assertEqual(game.vitals.current,0)
        self.assertIsNone(game.medicine.pending)

    def test_grenade_already_released_still_affects_bots_after_thrower_dies(self):
        game,bots,blast=setup(((0,0,6505),))
        event,_,_=release(game)
        game.vitals.damage(1000)
        self.assertEqual([m for m,b in blast.complete(event,100)],[0x1069,0x533])
        self.assertEqual(next(iter(bots.vitals.values())).current,0)

    def test_stale_self_position_is_skipped_but_does_not_cancel_existing_grenade(self):
        game,bots,blast=setup(((0,0,6505),))
        game.require_self_position_for_drop=True
        game.accept_self_position(game.player_position,100)
        event,_,_=release(game,game.player_position)
        self.assertEqual(blast.complete(event,102),[])
        self.assertEqual(game.vitals.current,1000)
        self.assertEqual(blast.events[-1]['affected'],0)

    def test_source_and_endpoint_bounds_fail_without_hp_changes(self):
        for change,reason in ((dict(reference=None),'source_unavailable'),
                              (dict(origin=(3000,0,6505)),'source_position'),
                              (dict(position=(50000,0,6505)),'endpoint_distance'),
                              (dict(position=(float('nan'),0,6505)),'source_unavailable')):
            game,bots,blast=setup()
            event,_,_=release(game)
            event.update(change)
            self.assertEqual(blast.complete(event,100),[])
            self.assertEqual(blast.events[-1]['reason'],reason)
            self.assertTrue(all(hp.current==1000 for hp in bots.vitals.values()))

    def test_smoke_and_flash_never_reuse_frag_damage_rule(self):
        for template in (50002,50003):
            game,bots,blast=setup()
            event,_,_=release(game);event['template']=template
            self.assertEqual(blast.complete(event,100),[])
            self.assertEqual(game.vitals.current,1000)
            self.assertTrue(all(hp.current==1000 for hp in bots.vitals.values()))


if __name__=='__main__':unittest.main()
