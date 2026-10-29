"""Synthetic checks for the Thai client coordinate system and spawn rules."""
import random
import struct
import unittest

from offline_client_map import ClientHeightfield, ThaiClientMap, HEIGHT_SCALE
from control_actions import ControlSession
from test_control_panel import ready_game,jeep_template


def tile(values):
    return struct.pack('<III',0xff000001,257,257)+b''.join(struct.pack('<H',values(x,y))
        for y in range(257) for x in range(257))


class ClientMapTests(unittest.TestCase):
    def test_peer_search_widens_when_nearby_coast_has_no_dry_ground(self):
        class Coast(ThaiClientMap):
            def __init__(self):pass
            def peer_walkable(self,x,y):
                return 7000 if ((x-100000)**2+(y-200000)**2)**.5>=6000 else None
        spot=Coast().spawn_spot((100000,200000,6501),random.Random(7),'peer',[])
        self.assertIsNotNone(spot)
        self.assertTrue(6000<=((spot[0]-100000)**2+(spot[1]-200000)**2)**.5<=12000)
        self.assertEqual(spot[2],7005)

    def test_height_axes_bilinear_interpolation_and_outer_edge(self):
        field=ClientHeightfield({(0,0):tile(lambda x,y:1000+2*x+3*y)},side=1)
        self.assertAlmostEqual(field.height_at(100,100),1002.5*HEIGHT_SCALE)
        self.assertAlmostEqual(field.height_at(200,0),1002*HEIGHT_SCALE)
        self.assertAlmostEqual(field.height_at(51200,51200),2280*HEIGHT_SCALE)
        self.assertIsNone(field.height_at(-1,0))
        self.assertIsNone(field.height_at(float('nan'),0))

    def test_indoor_loot_and_roadside_vehicles_are_distinct(self):
        field=ClientHeightfield({(0,0):tile(lambda x,y:6000)},side=1)
        road=bytearray(2048*2048*4)
        for row in range(1,120):
            road[(row*2048+50)*4+3]=255
        data=ThaiClientMap(field,road,[(10000,10000,1000,10000)],[(9000,10000,10000,1,0)])
        item=data.spawn_spot((15000,12000,11000),random.Random(2),'loot',[])
        self.assertGreater(item[0],9000)
        self.assertLess(item[0],9300)
        self.assertEqual(item[2],10010)
        vehicle=data.spawn_spot((15000,12000,11000),random.Random(2),'vehicle',[])
        self.assertIsNotNone(vehicle)
        self.assertFalse(data.is_road(*vehicle[:2]))
        self.assertTrue(any(data.is_road(vehicle[0]+dx,vehicle[1]+dy)
            for dx,dy in ((400,0),(-400,0),(0,400),(0,-400))))
        self.assertGreaterEqual(((vehicle[0]-10000)**2+(vehicle[1]-10000)**2)**.5,1200)
        self.assertAlmostEqual(vehicle[2],round(6000*HEIGHT_SCALE)+100)
        game=ready_game()
        game.player_position=(15000,12000,11000)
        control=ControlSession(game,jeep_template())
        control.placement_map=data
        packets,description=control.execute(dict(action='vehicle',config=101,distance=5))
        self.assertEqual(packets[0][0],0x654b)
        self.assertIn('路边',description)
        self.assertFalse(data.is_road(*next(iter(control.vehicles.values())).vehicle_position[:2]))


if __name__ == '__main__':
    unittest.main()
