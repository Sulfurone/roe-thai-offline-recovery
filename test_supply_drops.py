import math
from pathlib import Path
import struct
import unittest

from offline_bot_parcels import WorldParcels
from offline_bots import POSITION_MARKER
from offline_supply_drops import SMOKE_TEMPLATE, SupplyDrops
from offline_zone_schedule import ZonePlan,ZoneSchedule
from offline_weapons import WEAPONS,is_weapon
from test_control_panel import ready_game
from test_offline_motion import plane_body


class Terrain:
    def height_at(self,x,y):
        return 9500 if 30000<=x<=380000 and 30000<=y<=380000 else 6300


def scenario(terrain=None, *, smoke_profile=None):
    game=ready_game(empty_start=True,vitals_enabled=True)
    game.player_position=(204800,204800,9501)
    plan=ZonePlan.read(Path(__file__).with_name('examples')/'thai-match-circle-plan.json')
    zones=ZoneSchedule(game,terrain if terrain is not None else Terrain(),plan)
    parcels=WorldParcels(game)
    return game,zones,parcels,SupplyDrops(game,zones,parcels,plane_body(),seed=13,smoke_profile=smoke_profile)


class SupplyTests(unittest.TestCase):
    def test_smoke_waits_for_landing_and_range_and_cleans_up_once(self):
        profile=struct.pack('>IIQI',3,1,256,9)+b'Offline\0'+POSITION_MARKER
        game,zones,parcels,drops=scenario(smoke_profile=profile)
        zones.started=100
        drops.tick(220)
        position=drops.flight.landing
        game.player_position=(position[0]+46000,*position[1:])
        self.assertEqual([mid for mid,_ in drops.tick(226)],[0x654b,0x6563])
        self.assertEqual([mid for mid,_ in drops.tick(239)],[0x654c,0x654c,0x821])
        self.assertEqual(drops.tick(240),[])
        game.player_position=position
        entered=dict(drops.tick(241))
        self.assertEqual(set(entered),{0x565,0xbe7})
        origin=(*position[:2],position[2]-10000)
        owner=struct.unpack_from('>Q',entered[0xbe7],8)[0]
        self.assertNotEqual(owner,game.actor_uid)
        self.assertEqual(entered[0x565],struct.pack('>B3iBQ',1,*origin,0,owner))
        self.assertTrue(entered[0xbe7].endswith(struct.pack('>3i',*origin)))
        self.assertEqual(drops.tick(241.99),[])
        start,=drops.tick(242)
        template,serial,thrower,*coords=struct.unpack('>IIQ3iB3iBI',start[1])
        self.assertEqual((start[0],template,thrower,tuple(coords[:3])),(0x1006,SMOKE_TEMPLATE,owner,position))
        end,=drops.tick(242.25)
        self.assertEqual(end,(0x1009,struct.pack('>II3iBQI',template,serial,*position,0,owner,0)))
        self.assertEqual(drops.tick(243),[])
        self.assertEqual(drops.tick(307.25),[(0x605,struct.pack('>HQ',1,owner))])
        self.assertTrue(parcels.parcels)
        self.assertEqual(drops.tick(308),[])

    def test_empty_box_cancels_pending_smoke(self):
        game,zones,parcels,drops=scenario(smoke_profile=bytes(24)+POSITION_MARKER)
        zones.started=100
        drops.tick(220)
        game.player_position=drops.flight.landing
        self.assertEqual([mid for mid,_ in drops.tick(239)],[0x654c,0x821,0x565,0xbe7])
        next(iter(parcels.parcels.values()))[1].clear()
        self.assertEqual([mid for mid,_ in drops.tick(240)],[0x82b,0x605])
        self.assertEqual(drops.tick(241),[])

    def test_timed_flyby_cargo_landing_pickup_and_expiration(self):
        game,zones,parcels,drops=scenario()
        self.assertEqual(drops.tick(500),[])
        zones.started=100
        self.assertEqual(drops.tick(219.99),[])
        started=drops.tick(220)
        self.assertEqual([mid for mid,_ in started],[0x4a6,0x654b,0x6564])
        flight=drops.flight
        circle=zones.plan.stages[0].target
        self.assertLess(math.dist((circle.x,circle.y),flight.landing[:2]),circle.radius)
        self.assertEqual(struct.unpack('>3iB3iB',started[0][1]),(*flight.landing[:2],flight.start[2],0,0,0,0,0))
        self.assertEqual(drops.status(221),('incoming',*flight.landing[:2],18))
        self.assertEqual([mid for mid,_ in drops.tick(225)],[0x6563])
        cargo=drops.tick(226)
        self.assertEqual([mid for mid,_ in cargo],[0x654b,0x6563])
        cargo_body=cargo[0][1]
        self.assertEqual(struct.unpack_from('>I',cargo_body,12+struct.unpack_from('>I',cargo_body,8)[0])[0],501)
        self.assertFalse(parcels.parcels)
        self.assertEqual([mid for mid,_ in drops.tick(232)],[0x654c])
        self.assertEqual([mid for mid,_ in drops.tick(239)],[0x654c,0x821])
        entity=next(iter(parcels.parcels))
        position,items=parcels.parcels[entity]
        self.assertEqual(drops.status(239),('landed',*position[:2],0))
        templates={stack.item.template for stack in items.values()}
        weapon=next(stack.item for stack in items.values() if is_weapon(stack.item))
        self.assertIn(WEAPONS[weapon.template].ammunition,templates)
        self.assertTrue({200103,201003,200903,70003,50001,50002}<=templates)
        search=struct.pack('>QQ',entity,game.actor_uid)
        self.assertEqual(parcels.handle(0xbce,search),[])
        game.player_position=position
        self.assertEqual(parcels.handle(0xbce,search),[parcels.contents(entity)])
        request=struct.pack('>IIQBHB3iB',entity,1,game.actor_uid,0,0,1,*position,0)
        self.assertEqual([mid for mid,_ in parcels.handle(0x3b63,request)],[0x3e82,0x3b64,0x3b61])
        self.assertEqual(game.inventory.items[1,1],weapon)
        self.assertEqual(parcels.handle(0x3b63,request),[parcels.contents(entity)])
        self.assertEqual([mid for mid,_ in drops.tick(520)],[0x4a6,0x654b,0x6564])
        self.assertEqual([mid for mid,_ in drops.tick(526)],[0x654b,0x6563])
        self.assertEqual(drops.tick(538.99),[(0x654c,struct.pack('>Q',drops.flight.aircraft))])
        self.assertEqual([mid for mid,_ in drops.tick(539)],[0x82b,0x654c,0x821])
        self.assertNotIn(entity,parcels.parcels)

    def test_waits_for_dry_ground_and_does_not_spawn_after_death(self):
        water=Terrain()
        water.height_at=lambda x,y:4000
        game,zones,parcels,drops=scenario(water)
        zones.started=100
        self.assertEqual(drops.tick(220),[])
        self.assertEqual(drops.next_attempt,225)
        self.assertEqual(drops.index,0)
        water.height_at=Terrain().height_at
        self.assertEqual(drops.tick(224),[])
        game.vitals.damage(1000)
        self.assertEqual(drops.tick(230),[])
        self.assertFalse(parcels.parcels)


if __name__=='__main__':
    unittest.main()
