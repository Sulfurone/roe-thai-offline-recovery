"""Extra loot conservation, equipment slots, mailbox and native vehicle IDs."""
import json
import struct
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from offline_items import SPAWNABLE_EXTRA_ITEMS as EXTRA_ITEMS
from offline_vehicles import SPAWNABLE_LAND_VEHICLES as LAND_VEHICLES
from offline_control import ControlHub,validate_command
from control_actions import ControlSession,vehicle_spawn
from offline_world_state import restore,snapshot
from ingame_bridge import IngameMailbox
from ingame_client import MailboxClient
from test_control_panel import ready_game,jeep_template


class ExtraItemTests(unittest.TestCase):
    def test_motorbike_rejected_before_allocating_or_sending_vehicle(self):
        game=ready_game()
        control=ControlSession(game,jeep_template())
        next_uid=control.next_vehicle_uid
        with self.assertRaisesRegex(ValueError,'车轮'):
            validate_command(dict(action='vehicle',config=108))
        with self.assertRaisesRegex(ValueError,'车轮'):
            control.execute(dict(action='vehicle',config=108))
        # Automatic spawning has its own entry, bypassing menu validation.
        with self.assertRaisesRegex(ValueError,'车轮'):
            control.spawn_vehicle(game.player_position,108)
        with self.assertRaisesRegex(ValueError,'车轮'):
            vehicle_spawn(jeep_template(),next_uid,game.player_position,108)
        self.assertEqual(control.next_vehicle_uid,next_uid)
        self.assertEqual(control.vehicles,{})

    def test_mixed_roadside_population_keeps_other_models_without_motorbike(self):
        import random
        from offline_population import WorldPopulation
        from test_population import Surface
        configs=set()
        for seed in range(32):
            game=ready_game()
            game.player_position=(100000,200000,7250)
            control=ControlSession(game,jeep_template())
            population=WorldPopulation(control,Surface(),extra_items=True)
            replies=population.try_vehicles(game.player_position,random.Random(seed),(0,0))
            self.assertEqual(sum(m==0x654b for m,_ in replies),3)
            configs.update(car.vehicle_config for car in control.vehicles.values())
        self.assertNotIn(108,configs)
        self.assertEqual(configs,set(range(101,108)))

    def test_spawn_pickup_equip_and_drop_preserve_identity(self):
        game=ready_game()
        control=ControlSession(game)
        for template,spec in EXTRA_ITEMS.items():
            responses,_=control.execute(dict(action='item',template=template))
            self.assertEqual(responses[0][0],0x821)
            stack=list(game.ground_loot.stacks.values())[-1]
            request=struct.pack('>IIQBHB3iB',stack.entity,0,0,0,0,1,*game.player_position,0)
            self.assertEqual([m for m,_ in game.handle(0x3b63,request)],[0x3e82,0x82b,0x3b64])
            key=next(k for k,v in game.inventory.items.items() if v.uid==stack.item.uid)
            if spec.slot and (template==200901 or template==50001):
                self.assertEqual(key,(1,spec.slot))
            self.assertEqual(game.inventory.items[key],stack.item)
        inventory,ground,_,_=restore(snapshot(game.inventory,game.ground_loot,game.magazine,game.selected_slot))
        self.assertEqual(inventory.items,game.inventory.items)
        # Drop an equipped backpack through the same original slot request.
        bag=game.inventory.items[1,11]
        body=struct.pack('>BBHHQB',2,1,11,0,0,1)
        game.handle(0x3e80,body)
        self.assertNotIn((1,11),game.inventory.items)
        self.assertEqual(list(game.ground_loot.stacks.values())[-1].item,bag)

    def test_grenade_stack_limits_and_wrong_equipment_slot(self):
        game=ready_game()
        control=ControlSession(game)
        for template in (50001,50001):
            control.execute(dict(action='item',template=template,count=5))
            stack=list(game.ground_loot.stacks.values())[-1]
            game.handle(0x3b63,struct.pack('>IIQBHB3iB',stack.entity,0,0,0,0,1,*game.player_position,0))
        self.assertEqual(game.inventory.items[1,5].count,10)
        before=dict(game.inventory.items)
        self.assertEqual(game.inventory.transfer((1,5),(1,1),1)[0][0],0x3e81)
        self.assertEqual(game.inventory.items,before)
        for template,count in ((200901,2),(40301,2),(50003,11)):
            with self.assertRaises(ValueError):
                validate_command(dict(action='item',template=template,count=count))

    def test_land_vehicle_model_health_seat_and_input_routing(self):
        game=ready_game()
        control=ControlSession(game,jeep_template())
        for config,spec in LAND_VEHICLES.items():
            packets,_=control.execute(dict(action='vehicle',config=config))
            uid=struct.unpack_from('>Q',packets[0][1])[0]
            car=control.vehicles[uid]
            self.assertEqual(car.vehicle_config,config)
            self.assertEqual(struct.unpack_from('>I',packets[1][1],8)[0],spec.hp)
            game.player_position=car.vehicle_position
            boarded=control.handle(0x6541,struct.pack('>QI',uid,1))
            body=next(body for message,body in boarded if message==0x6542)
            self.assertEqual(struct.unpack_from('>I',body,8)[0],config)
            self.assertEqual(control.handle(0x6547,struct.pack('>I',spec.seats+1))[0][1][-4:],struct.pack('>I',1))
            drive=struct.pack('>IBQB',1,0,uid,1)
            self.assertEqual(control.handle(0x6572,drive),[(0x6573,drive)])
            control.handle(0x6543,b'\0')

    def test_equipment_command_round_trips_through_mailbox(self):
        with tempfile.TemporaryDirectory() as folder:
            mailbox=IngameMailbox(folder)
            hub=ControlHub()
            hub.update(connected=True,ready=True,weapons_enabled=True)
            mailbox.publish(hub.snapshot())
            client=MailboxClient(mailbox.directory)
            client.send(dict(action='item',template=200903))
            mailbox.poll(hub)
            command=hub.take()
            self.assertEqual((command['action'],command['template'],command['count']),('item',200903,1))

    def test_failed_extra_item_save_rolls_back_ground_and_inventory(self):
        game=ready_game()
        before=snapshot(game.inventory,game.ground_loot,game.magazine,game.selected_slot)
        with patch.object(game,'save_state',side_effect=OSError('synthetic write failure')):
            with self.assertRaises(OSError):
                ControlSession(game).execute(dict(action='item',template=200903))
        self.assertEqual(snapshot(game.inventory,game.ground_loot,game.magazine,game.selected_slot),before)
        self.assertTrue(game.ground_loot.announced)

    def test_equipment_does_not_expand_original_delta_row_array(self):
        game=ready_game()
        game.inventory.delta([(2,i) for i in range(128)])
        with self.assertRaises(ValueError):
            game.inventory.delta([(2,i) for i in range(128)]+[(1,11)])

    def test_local_boarding_uses_loaded_selected_car_despite_old_walking_position(self):
        game=ready_game()
        control=ControlSession(game,jeep_template(),client_boarding=True)
        control.spawn_vehicle((game.player_position[0]+1957,*game.player_position[1:]),105)
        car=next(iter(control.vehicles.values()))
        car.vehicle_ready=True
        body=struct.pack('>QI',car.vehicle_uid,1)
        self.assertEqual(car.handle(0x6541,body),[])  # the strict baseline still rejects the old distance
        replies=control.handle(0x6541,body)
        self.assertIn(0x6542,[m for m,_ in replies])
        self.assertTrue(game.seated)
        self.assertEqual(control.active_vehicle,car.vehicle_uid)
        self.assertTrue(control.last_board_event['accepted'])
        self.assertEqual(control.handle(0x6572,struct.pack('>IBQB',1,0,car.vehicle_uid,1))[0][0],0x6573)
        control.handle(0x6543,b'\0')
        self.assertFalse(game.seated)

    def test_local_boarding_requires_loaded_target_ground_state_and_real_seat(self):
        for mode in ('unloaded','airborne','bad-seat'):
            game=ready_game()
            control=ControlSession(game,jeep_template(),client_boarding=True)
            control.spawn_vehicle(game.player_position,102)
            car=next(iter(control.vehicles.values()))
            car.vehicle_ready=mode!='unloaded'
            if mode=='airborne':game.deployment_phase='gliding'
            seat=3 if mode=='bad-seat' else 1
            replies=control.handle(0x6541,struct.pack('>QI',car.vehicle_uid,seat))
            self.assertEqual(struct.unpack_from('>I',replies[0][1],28)[0],1)
            self.assertFalse(game.seated)
            self.assertFalse(control.last_board_event['accepted'])


if __name__=='__main__':
    unittest.main()
