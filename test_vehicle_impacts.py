import struct
import unittest
from unittest.mock import patch

from control_actions import ControlSession
from offline_match_status import room_kill_broadcast
from offline_vehicle_impacts import VehicleImpacts
from test_combat import fixture
from test_control_panel import jeep_template


class VehicleImpactTests(unittest.TestCase):
    def test_driver_physics_can_eliminate_bot_and_broadcast_vehicle_cause(self):
        game,bots,_,victim=fixture()
        start=game.player_position
        bots.actors[victim]['position']=(start[0]+200,*start[1:])
        bots.death_notice=lambda uid,killer,config,_: [room_kill_broadcast(
            killer,b'Test',uid,b'AI-1',config,1,vehicle_impact=True)]
        control=ControlSession(game,jeep_template(),client_boarding=True)
        control.vehicle_impacts=VehicleImpacts(game,bots)
        control.spawn_vehicle(start)
        car,=control.vehicles.values()
        car.vehicle_initialized=True

        def move(x,at):
            body=struct.pack('>QIB3iB3f',car.vehicle_uid,0,0,start[0]+x,*start[1:],0,1700,0,0)+bytes(23)
            with patch('control_actions.time.monotonic',return_value=at):
                return control.handle(0x6549,body)

        self.assertEqual(move(0,10),[])
        control.handle(0x6541,struct.pack('>QI',car.vehicle_uid,1))
        self.assertEqual(move(0,11),[])
        hits=move(350,11.2)
        self.assertEqual(bots.vitals[victim].current,0)
        self.assertEqual([mid for mid,_ in hits],[0x1069,0x533,0x480])
        self.assertEqual(struct.unpack_from('>3I',hits[-1][1],len(hits[-1][1])-17),(1,101,12))
        self.assertEqual(move(500,11.4),[])

    def test_stationary_teleport_upper_floor_and_wall_do_not_hit(self):
        game,bots,_,victim=fixture()
        x,y,z=game.player_position
        for end,location,allowed in (((x,y,z),(x,y,z),True),((x+6000,y,z),(x+200,y,z),True),
                ((x+350,y,z),(x+200,y,z+350),True),((x+350,y,z),(x+200,y+130,z),False)):
            bots.actors[victim]['position']=location
            visibility=type('Visibility',(),{'clear':lambda *args:allowed})()
            impacts=VehicleImpacts(game,bots,visibility)
            self.assertEqual(impacts.move(42,101,(x,y,z),(1700,0,0),10),[])
            self.assertEqual(impacts.move(42,101,end,(1700,0,0),10.2),[])
            self.assertEqual(bots.vitals[victim].current,400)
