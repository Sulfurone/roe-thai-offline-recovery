import struct
import unittest
from types import SimpleNamespace

from offline_bot_parcels import BotParcels
from test_control_panel import ready_game


class ParcelTests(unittest.TestCase):
    def test_open_take_and_repeat_conserve_weapon_and_reserve(self):
        game = ready_game()
        uid = 0x1000000001100
        position = game.player_position
        bots = SimpleNamespace(actors={uid: {'position': position}})
        ai = SimpleNamespace(brains={uid: SimpleNamespace(equipped=True,magazine=17,reserve=61)})
        parcels = BotParcels(game,bots,ai)
        spawn = parcels.drop(uid)
        self.assertEqual(spawn[0][0],0x821)
        entity = next(iter(parcels.parcels))
        self.assertEqual(parcels.drop(uid),[])
        request = struct.pack('>QQ',entity,game.actor_uid)
        game.player_position = (position[0]+1000,*position[1:])
        self.assertEqual(parcels.handle(0xbce,request),[])
        game.player_position = position
        self.assertEqual(parcels.handle(0xbce,request),[parcels.contents(entity)])
        for slot in (1,2):
            pickup = struct.pack('>IIQBHB3iB',entity,slot,0,0,0,1,*position,0)
            result = parcels.handle(0x3b63,pickup)
            self.assertEqual([m for m,b in result],[0x3e82,0x3b64,0x3b61])
            before = dict(game.inventory.items)
            parcels.handle(0x3b63,pickup)
            self.assertEqual(game.inventory.items,before)
        self.assertFalse(parcels.parcels[entity][1])
        self.assertEqual(parcels.contents(entity),(0x3b61,struct.pack('>II',entity,0)))
        self.assertIn(17,game.inventory.weapon_magazines.values())


if __name__=='__main__':
    unittest.main()
