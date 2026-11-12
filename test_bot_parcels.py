import struct
import unittest
from types import SimpleNamespace

from offline_bot_ai import BotAI
from offline_bot_parcels import BotParcels
from offline_bots import BotRoster,POSITION_MARKER
from offline_items import SPAWNABLE_EXTRA_ITEMS
from offline_vitals import Vitals
from offline_weapons import WEAPONS,is_weapon
from test_control_panel import ready_game


def setup_parcels(count=1,seed=1):
    game=ready_game(empty_start=True,vitals_enabled=True)
    profile=struct.pack('>IIQI',3,1,1,12)+b'OfflineBot1\0'+POSITION_MARKER
    bots=BotRoster(profile,count)
    ai=BotAI(game,bots,SimpleNamespace(seed=seed),visibility=None)
    for uid in ai.loadouts:
        bots.actors[uid]={'position':game.player_position,'created':100}
        bots.vitals[uid]=Vitals()
    parcels=BotParcels(game,bots,ai)
    bots.death_parcel=parcels.drop
    return game,bots,ai,parcels


class ParcelTests(unittest.TestCase):
    def test_open_take_and_repeat_preserves_all_item_categories_and_selects_first_gun(self):
        game,bots,ai,parcels=setup_parcels()
        uid=bots.FIRST_UID
        ai.tick(100)
        brain=ai.brains[uid]
        brain.magazine=17
        brain.reserve=61
        position = game.player_position
        spawn = parcels.drop(uid)
        self.assertEqual(spawn[0][0],0x821)
        entity = next(iter(parcels.parcels))
        items=dict(parcels.parcels[entity][1])
        self.assertEqual(parcels.drop(uid),[])
        request = struct.pack('>QQ',entity,game.actor_uid)
        game.player_position = (position[0]+1000,*position[1:])
        self.assertEqual(parcels.handle(0xbce,request),[])
        game.player_position = position
        self.assertEqual(parcels.handle(0xbce,request),[parcels.contents(entity)])
        for slot,stack in items.items():
            pickup = struct.pack('>IIQBHB3iB',entity,slot,0,0,0,1,*position,0)
            result = parcels.handle(0x3b63,pickup)
            self.assertEqual([m for m,b in result],[0x3e82,0x3b64,0x3b61])
            self.assertEqual(struct.unpack_from('>II',result[1][1]),(entity,slot))
            self.assertIn(stack.item,game.inventory.items.values())
            before = dict(game.inventory.items)
            parcels.handle(0x3b63,pickup)
            self.assertEqual(game.inventory.items,before)
        self.assertFalse(parcels.parcels[entity][1])
        self.assertEqual(parcels.contents(entity),(0x3b61,struct.pack('>II',entity,0)))
        self.assertEqual((game.selected_slot,game.magazine),(1,17))
        self.assertEqual(game.inventory.weapon_magazines[items[2].item.uid],items[2].magazine)
        self.assertEqual(game.reserve,sum(s.item.count for s in items.values() if s.item.kind==3))
        self.assertEqual(game.inventory.reserve_for(WEAPONS[brain.weapon].ammunition),
                         dict(ai.loadouts[uid].supplies)[WEAPONS[brain.weapon].ammunition]+61)
        self.assertFalse(game.ground_loot.stacks.keys() & parcels.parcels.keys())

    def test_all_63_parcels_have_unique_pairs_even_before_equip_or_outside_interest(self):
        game,bots,ai,parcels=setup_parcels(63,42)
        _,_,another,_=setup_parcels(63,43)
        self.assertNotEqual(ai.loadouts,another.loadouts)
        for uid in reversed(tuple(ai.loadouts)):
            self.assertEqual(bots.damage(uid,200),[])
            self.assertEqual([mid for mid,_ in bots.damage(uid,1000)],[0x821])
            self.assertEqual(bots.damage(uid,1000),[])
        pairs=set()
        kits=set()
        uids=set()
        self.assertEqual(len(parcels.parcels),63)
        for _,items in parcels.parcels.values():
            contents=[s.item for s in items.values()]
            weapons=[i.template for i in contents if is_weapon(i)]
            ammo={i.template for i in contents if i.kind==3}
            self.assertEqual(len(weapons),2)
            self.assertEqual(ammo,{WEAPONS[template].ammunition for template in weapons})
            self.assertEqual({i.template for i in contents if i.kind==5},{50001,50002})
            self.assertEqual(sum(i.kind==7 for i in contents),2)
            self.assertEqual({SPAWNABLE_EXTRA_ITEMS[i.template].slot for i in contents if i.kind==20},{10,11,12})
            self.assertTrue(uids.isdisjoint(i.uid for i in contents))
            uids.update(i.uid for i in contents)
            pairs.add(frozenset(weapons))
            kits.add(tuple(sorted((i.template,i.count) for i in contents)))
        self.assertEqual(len(pairs),63)
        self.assertEqual(len(kits),63)

    def test_empty_combat_magazine_still_drops_ammo_and_uses_the_equipped_rifle(self):
        game,bots,ai,parcels=setup_parcels(63,42)
        uid=next(uid for uid,loadout in ai.loadouts.items() if loadout.primary!=10201)
        bots.active.add(uid)
        ai.tick(101)
        brain=ai.brains[uid]
        self.assertEqual(struct.unpack_from('>I',ai.equipment(uid)[1],12)[0],brain.weapon)
        brain.magazine=brain.reserve=0
        self.assertIn(0x821,[mid for mid,_ in bots.damage(uid,1000)])
        _,items=next(iter(parcels.parcels.values()))
        self.assertEqual((items[1].item.template,items[1].magazine),(brain.weapon,0))
        self.assertTrue(any(s.item.template==WEAPONS[brain.weapon].ammunition and s.item.count>0 for s in items.values()))


if __name__=='__main__':
    unittest.main()
