import math
from pathlib import Path
import struct
import unittest

from offline_bot_parcels import WorldParcels
from offline_supply_drops import SupplyDrops
from offline_zone_schedule import ZonePlan,ZoneSchedule
from offline_weapons import WEAPONS,is_weapon
from test_control_panel import ready_game
from test_offline_motion import plane_body


class Terrain:
    def height_at(self,x,y):
        return 9500 if 30000<=x<=380000 and 30000<=y<=380000 else 6300


def scenario(terrain=None):
    game=ready_game(empty_start=True,vitals_enabled=True)
    game.player_position=(204800,204800,9501)
    plan=ZonePlan.read(Path(__file__).with_name('examples')/'thai-match-circle-plan.json')
    zones=ZoneSchedule(game,terrain if terrain is not None else Terrain(),plan)
    parcels=WorldParcels(game)
    return game,zones,parcels,SupplyDrops(game,zones,parcels,plane_body(),seed=13)


class SupplyTests(unittest.TestCase):
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
        landed=drops.tick(239)
        self.assertEqual([mid for mid,_ in landed],[0x654b,0x6571])
        cargo_uid=flight.aircraft+1
        self.assertEqual(landed[1][1],struct.pack('>QI',cargo_uid,next(iter(parcels.parcels))))
        offset=12+struct.unpack_from('>I',landed[0][1],8)[0]
        self.assertEqual(struct.unpack_from('>III3i',landed[0][1],offset),(501,1,100,*flight.landing))
        entity=next(iter(parcels.parcels))
        position,items=parcels.parcels[entity]
        self.assertEqual(drops.status(239),('landed',*position[:2],0))
        templates={stack.item.template for stack in items.values()}
        weapon=next(stack.item for stack in items.values() if is_weapon(stack.item))
        self.assertIn(WEAPONS[weapon.template].ammunition,templates)
        self.assertTrue({200103,201003,200903,70003,50001,50002}<=templates)
        search=struct.pack('>Q',cargo_uid)
        self.assertEqual(parcels.handle(0x656f,search),[])
        game.player_position=position
        self.assertEqual(parcels.handle(0x656f,search),[parcels.contents(entity)])
        request=struct.pack('>IIQBHB3iB',entity,1,game.actor_uid,0,0,1,*position,0)
        self.assertEqual([mid for mid,_ in parcels.handle(0x3b63,request)],[0x3e82,0x3b64,0x3b61])
        self.assertEqual(game.inventory.items[1,1],weapon)
        self.assertEqual(parcels.handle(0x3b63,request),[parcels.contents(entity)])
        self.assertEqual([mid for mid,_ in drops.tick(520)],[0x4a6,0x654b,0x6564])
        self.assertEqual([mid for mid,_ in drops.tick(526)],[0x654b,0x6563])
        self.assertEqual(drops.tick(538.99),[(0x654c,struct.pack('>Q',drops.flight.aircraft))])
        self.assertEqual([mid for mid,_ in drops.tick(539)],[0x654c,0x654b,0x6571])
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
