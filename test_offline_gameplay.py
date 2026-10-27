import struct
import unittest
from offline_gameplay import OfflineGameplay, ACTOR_UID, JEEP_UID, TYPED_ACTOR_UID, TYPED_VEHICLE_UID


class GameplayStateTests(unittest.TestCase):
    def test_stationary_fire_consumes_every_round_and_cannot_go_negative(self):
        game = OfflineGameplay()
        shot = struct.pack('>6fIB',1,2,3,0,1,0,7,0)
        for _ in range(35):
            game.handle(0x11d3,shot+bytes(8))
        self.assertEqual(game.magazine,0)
        self.assertEqual(game.reserve,120)

    def test_reload_transfers_only_available_ammunition(self):
        game = OfflineGameplay(magazine=2,reserve=9)
        replies=game.handle(0x49c,struct.pack('>I',1))
        self.assertEqual((game.magazine,game.reserve),(11,0))
        self.assertEqual([m for m,_ in replies],[0x49d,0x4a0,0x3e82])
        game.handle(0x49c,struct.pack('>I',1))
        self.assertEqual((game.magazine,game.reserve),(11,0))

    def test_holstered_weapon_does_not_fire(self):
        game=OfflineGameplay()
        game.handle(0x49e,bytes(4))
        self.assertEqual(game.handle(0x11d3,bytes(29)),[])
        self.assertEqual(game.magazine,30)

    def test_zero_direction_stop_message_does_not_consume_ammo(self):
        game=OfflineGameplay()
        self.assertEqual(game.handle(0x11d3,bytes(29)),[])
        self.assertEqual(game.magazine,30)

    def test_nonzero_stop_coordinates_and_zero_length_ray_do_not_consume_ammo(self):
        game=OfflineGameplay()
        for shot in (struct.pack('>6fIB',10,20,30,10,120,30,1,1),
                     struct.pack('>6fIB',10,20,30,10,20,30,1,0)):
            self.assertEqual(game.handle(0x11d3,shot),[])
        self.assertEqual(game.magazine,30)

    def test_unknown_or_remote_vehicle_cannot_be_boarded(self):
        game=OfflineGameplay()
        self.assertEqual(game.handle(0x6541,struct.pack('>QI',42,1)),[])
        game.player_position=(0,0,0)
        self.assertEqual(game.handle(0x6541,struct.pack('>QI',JEEP_UID,1)),[])
        self.assertFalse(game.seated)

    def test_board_leave_ownership_and_exit_position(self):
        game=OfflineGameplay()
        game.player_position=game.vehicle_position
        replies=game.handle(0x6541,struct.pack('>QI',JEEP_UID,1)+bytes(8))
        self.assertTrue(game.seated)
        self.assertEqual(struct.unpack('>QIQ',replies[0][1]),(JEEP_UID,0,ACTOR_UID))
        self.assertEqual(struct.unpack_from('>I',replies[1][1],8)[0],101)
        self.assertEqual(game.handle(0x6541,struct.pack('>QI',JEEP_UID,1)),[])
        game.vehicle_position=(330000,270000,7000)
        replies=game.handle(0x6543,b'\0')
        self.assertFalse(game.seated)
        self.assertEqual(game.player_position,(330180,270000,7120))
        self.assertEqual(struct.unpack('>QIQ',replies[1][1]),(JEEP_UID,0,0))

    def test_auto_board_waits_for_own_vehicle_physics(self):
        game=OfflineGameplay(auto_board=True)
        body=bytearray(61)
        struct.pack_into('>Q',body,0,JEEP_UID)
        struct.pack_into('>3i',body,13,326400,272200,6501)
        self.assertEqual(game.handle(0x6549,body),[])
        self.assertEqual(game.vehicle_position,(326400,272200,6501))
        move=struct.pack('>I3i',2,325800,271700,6488)
        self.assertEqual(len(game.handle(0x2a,move)),2)
        self.assertEqual(game.handle(0x6549,body),[])
        self.assertEqual(game.handle(0x2a,move),[])

    def test_malformed_requests_do_not_change_state(self):
        game=OfflineGameplay()
        for message in (0x49c,0x49e,0x11d3,0x6541,0x6543,0x6549):
            self.assertEqual(game.handle(message,b''),[])
        self.assertEqual((game.magazine,game.reserve,game.seated),(30,120,False))

    def test_typed_identity_is_used_for_ammo_owner_and_passenger(self):
        game=OfflineGameplay(actor_uid=TYPED_ACTOR_UID,vehicle_uid=TYPED_VEHICLE_UID,vehicle_config=3)
        self.assertEqual(struct.unpack_from('>Q',game.ammo_sync()[1])[0],TYPED_ACTOR_UID)
        self.assertEqual(game.handle(0x6541,struct.pack('>QI',JEEP_UID,1)),[])
        # An airborne attachment is server initiated, not a proximity action.
        replies=game.board()
        self.assertEqual(struct.unpack('>QIQ',replies[0][1]),(TYPED_VEHICLE_UID,0,TYPED_ACTOR_UID))
        self.assertEqual(struct.unpack_from('>I',replies[1][1],8)[0],3)
        self.assertEqual(struct.unpack_from('>Q',replies[1][1],16)[0],TYPED_ACTOR_UID)

    def test_diagnostic_vehicle_initialization_and_exit_timer_are_explicit(self):
        game=OfflineGameplay(initialize_vehicle=True,auto_exit_after=8)
        replies=game.board()
        self.assertEqual([m for m,_ in replies],[0x6554,0x656e,0x656d,0x6542])
        self.assertEqual(struct.unpack('>QII',replies[0][1]),(JEEP_UID,24000,0))
        self.assertEqual(struct.unpack('>QI',replies[1][1]),(JEEP_UID,0))
        deadline=game.exit_deadline
        self.assertEqual(game.tick(deadline-1),[])
        self.assertEqual([m for m,_ in game.tick(deadline)],[0x6544,0x656d])
        self.assertFalse(game.seated)
        self.assertEqual(game.tick(deadline+1),[])

    def test_glider_uses_announced_altitude_and_actor_ready_without_car_physics(self):
        game=OfflineGameplay(auto_board=True,vehicle_config=3)
        name=b'Glider\0'
        spawn=struct.pack('>QI',JEEP_UID,len(name))+name+struct.pack('>III3i',3,0,0,325800,271700,35000)+bytes(40)
        game.observe_spawn(0x654b,spawn)
        self.assertTrue(game.vehicle_announced)
        self.assertFalse(game.can_auto_board())
        replies=game.handle(0x2a,struct.pack('>I3i',2,325800,271700,35000))
        self.assertTrue(game.seated)
        self.assertEqual(struct.unpack_from('>3i',replies[-1][1],32),(325800,271700,35000))
        self.assertEqual(game.handle(0x2a,bytes(16)),[])

    def test_spawn_from_other_vehicle_or_config_does_not_enable_boarding(self):
        game=OfflineGameplay(auto_board=True,vehicle_config=3)
        for uid,config in ((42,3),(JEEP_UID,101)):
            body=struct.pack('>QI',uid,2)+b'G\0'+struct.pack('>III3i',config,0,0,1,2,3)+bytes(40)
            game.observe_spawn(0x654b,body)
        self.assertFalse(game.vehicle_announced)

    def test_aircraft_boarding_enables_jump_and_jump_request_detaches_once(self):
        game=OfflineGameplay(vehicle_config=4)
        replies=game.board()
        self.assertEqual(replies[-1],(0x6565,struct.pack('>Q',JEEP_UID)))
        self.assertEqual([m for m,_ in game.handle(0x6566,b'\0')],[0x6544,0x656d])
        self.assertEqual(game.handle(0x6566,b'\0'),[])

    def test_vehicle_initialization_is_not_repeated_on_reboarding(self):
        game=OfflineGameplay(initialize_vehicle=True)
        self.assertEqual(len(game.board()),4)
        game.leave()
        self.assertEqual([m for m,_ in game.board()],[0x656d,0x6542])

    def test_driver_input_broadcast_preserves_only_known_vehicle_input(self):
        game=OfflineGameplay()
        body=struct.pack('>IBQB',35,6,game.vehicle_uid,1)
        self.assertEqual(game.handle(0x6572,body),[])
        game.board()
        self.assertEqual(game.handle(0x6572,body+bytes(8)),[(0x6573,body)])
        self.assertEqual(game.handle(0x6572,body[:-1]),[])
        foreign=struct.pack('>IBQB',35,6,123,1)
        self.assertEqual(game.handle(0x6572,foreign),[])
        game.leave()
        stop=body[:-1]+b'\x10'
        self.assertEqual(game.handle(0x6572,stop),[(0x6573,stop)])

    def test_aircraft_route_and_timed_exit_use_current_position(self):
        from unittest.mock import patch
        game=OfflineGameplay(vehicle_config=4,aircraft_route_speed=2000,auto_exit_after=8)
        game.vehicle_position=(325800,271700,35000)
        with patch('offline_gameplay.time.monotonic',return_value=100):
            replies=game.board()
        self.assertEqual(replies[-1][0],0x6564)
        update=game.tick(100.5)
        self.assertEqual(update[0][0],0x6563)
        self.assertEqual(struct.unpack_from('>3i',update[0][1],8),(325800,273700,35000))
        self.assertEqual(game.tick(100.6),[])
        exit_message=game.tick(108)[0]
        self.assertEqual(struct.unpack_from('>3i',exit_message[1],28),(325980,287700,35120))
        self.assertIsNone(game.route_started)
        self.assertEqual(game.tick(200),[])

    def test_seat_switch_preserves_identity_and_driver_input_authority(self):
        game=OfflineGameplay()
        self.assertEqual(game.handle(0x6547,struct.pack('>I',2)),[])
        game.board()
        reply=game.handle(0x6547,struct.pack('>I',2)+bytes(8))[0]
        self.assertEqual(reply[0],0x6548)
        self.assertEqual(struct.unpack('>QQIII',reply[1]),(game.vehicle_uid,game.actor_uid,1,2,0))
        self.assertEqual(game.seat,2)
        key=struct.pack('>IBQB',35,6,game.vehicle_uid,1)
        self.assertEqual(game.handle(0x6572,key),[])
        bad=game.handle(0x6547,struct.pack('>I',5))[0]
        self.assertEqual(struct.unpack('>QQIII',bad[1])[-1],1)
        self.assertEqual(game.seat,2)
        game.handle(0x6547,struct.pack('>I',1))
        self.assertEqual(game.handle(0x6572,key),[(0x6573,key)])
        self.assertEqual(struct.unpack_from('>I',game.leave()[0][1],20)[0],1)


if __name__=='__main__':
    unittest.main()
