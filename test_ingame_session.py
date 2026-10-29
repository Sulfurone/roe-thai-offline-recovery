"""File mailbox actions reach a real encrypted game connection without HTTP."""
import contextlib
import io
import json
from pathlib import Path
import queue
import socket
import struct
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import local_server
from ingame_client import MailboxClient
from offline_gameplay import JEEP_UID,OfflineGameplay
from offline_inventory import Item
from test_throwables import start as throw_start,finish as throw_finish
from test_medicine import request as medicine_request
from test_hit_reports import hit_body
from test_collision_assets import collision_xml,sfc
from offline_collision_assets import sfc_path_key
from offline_visibility import StaticVisibility
from test_offline_motion import move_body, plane_body
from test_control_panel import jeep_template
from offline_bots import POSITION_MARKER,BotRoster
from offline_combat import BotCombat
from offline_bot_ai import BotAI
from tpdu import decrypt, encrypt, frame, read_frame


class IngameSessionTests(unittest.TestCase):
    def test_native_mailbox_replies_and_owned_file_cleanup(self):
        self.run_session('--ingame-control')

    def test_overlay_mailbox_replies_without_client_file_installation(self):
        self.run_session('--ingame-overlay')

    def test_daytime_aircraft_jump_then_menu_ground_actions(self):
        self.run_session('--ingame-overlay', aircraft=True)

    def test_random_world_doors_and_peer_query_over_encrypted_connection(self):
        self.run_session('--ingame-overlay', population=True)

    def test_posture_speed_delta_after_readiness_is_sent_once(self):
        self.run_session('--ingame-overlay',posture=True)

    def test_life_state_is_sent_once_after_readiness_over_encrypted_connection(self):
        self.run_session('--ingame-overlay',vitals=True)

    def test_daytime_parachute_life_and_throw_receipts_with_menu_over_encrypted_connection(self):
        self.run_session('--ingame-overlay',aircraft=True,vitals=True,throws=True)

    def test_timed_medical_use_and_hp_delta_over_encrypted_connection(self):
        self.run_session('--ingame-overlay',vitals=True,medicine=True)

    def test_native_medical_cancel_does_not_spend_or_heal_and_new_cast_restarts_timer(self):
        self.run_session('--ingame-overlay',vitals=True,medicine=True,cancel_medicine=True)

    def test_collision_reports_are_diagnostic_without_invented_hp_or_ammo_changes(self):
        self.run_session('--ingame-overlay',vitals=True,hit_reports=True)

    def test_consumed_shots_damage_peer_and_send_native_death_over_encrypted_connection(self):
        self.run_session('--ingame-overlay',population=True,vitals=True,combat=True)

    def test_bot_ai_arms_fires_and_damages_local_player_over_encrypted_connection(self):
        self.run_session('--ingame-overlay',population=True,vitals=True,combat=True,ai=True)

    def test_native_throw_completion_applies_self_blast_once_over_encrypted_connection(self):
        self.run_session('--ingame-overlay',population=True,vitals=True,throws=True,blast=True)

    def test_collision_assets_prepared_before_encrypted_throw_session(self):
        self.run_session('--ingame-overlay',population=True,vitals=True,throws=True,blast=True,collision=True)

    def test_reload_wait_and_switch_cancel_over_encrypted_connection(self):
        self.run_session('--ingame-overlay',timed_reload=True)

    def test_recovered_reload_duration_over_encrypted_connection(self):
        self.run_session('--ingame-overlay',timed_reload=True,original_reload=True)

    def test_native_slot_attachment_replace_and_detach_over_encrypted_connection(self):
        self.run_session('--ingame-overlay',attachments=True)

    def test_extended_magazine_reload_and_detach_return_ammo_over_encrypted_connection(self):
        self.run_session('--ingame-overlay',attachments=True,extensions=True)

    def run_session(self, interface, aircraft=False, population=False,posture=False,vitals=False,throws=False,medicine=False,hit_reports=False,combat=False,ai=False,cancel_medicine=False,blast=False,collision=False,timed_reload=False,original_reload=False,attachments=False,extensions=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            game = root / '32838'
            game.mkdir()
            (game / 'Europa_Client.exe').write_bytes(b'fixture identity; never executed')
            vehicle = root / 'jeep.bin'
            vehicle.write_bytes(jeep_template())
            with socket.socket() as reserved:
                reserved.bind(('127.0.0.1', 0))
                port = reserved.getsockname()[1]
            output, errors = io.StringIO(), queue.Queue()
            argv = ['local_server.py', '--seconds', '15', '--port', str(port), '--single-session',
                    interface, '--control-vehicle-template', str(vehicle),
                    '--gameplay-prototype', '--gameplay-inventory', '--gameplay-ground-loot']
            if posture:
                argv.append('--gameplay-posture-speeds')
            if timed_reload:argv.extend(['--gameplay-original-reload'] if original_reload else ['--gameplay-reload-seconds','.3'])
            if extensions:argv.append('--gameplay-original-reload')
            if vitals:
                argv.append('--gameplay-vitals')
            if throws:
                argv.append('--gameplay-throwables')
            if combat:
                argv.append('--world-bot-combat')
            if population:
                terrain = root / 'surface.repx'
                terrain.write_text('<root><PxHeightField><NbRows>2</NbRows><NbColumns>2</NbColumns>'
                    '<samples>6500 6500 6500 6500</samples></PxHeightField><PxRigidStatic>'
                    '<GlobalPose>.5 .5 .5 .5 0 0 0</GlobalPose><PxHeightFieldGeometry>'
                    '<RowScale>1000000</RowScale><ColumnScale>1000000</ColumnScale>'
                    '<HeightScale>1</HeightScale></PxHeightFieldGeometry></PxRigidStatic></root>')
                profile = root / 'synthetic-profile.bin'
                profile.write_bytes(struct.pack('>IIQI', 3, 1, 1, 12) + b'OfflineBot1\0' + POSITION_MARKER)
                argv.extend(['--gameplay-doors', '--world-populate','--world-extra-items', '--world-terrain', str(terrain),
                             '--world-bots', '1', '--world-bot-profile', str(profile)])
            if ai or blast:
                occlusion=root/'static.xml'
                occlusion.write_text('<r ObjName="x.eu_killzone_2048.ClientTable.RigidStaticInPxScene">'
                    '<mItems mID="1" mBoundingX="10000" mBoundingY="10000" mBoundingZ="6600" mBoundingRadius="500"/>'
                    '</r>',encoding='utf8')
                argv.extend(['--world-bot-occlusion',str(occlusion)])
                if ai:argv.append('--world-bot-ai')
                if blast:argv.append('--world-throwable-combat')
                if collision:
                    archive=root/'SFC';archive.mkdir()
                    model_path='Data/Scene/general/building/Own_Room_collision.xml'
                    (archive/'Scene_General_Building_Own_Room.sfc').write_bytes(sfc(collision_xml(),sfc_path_key(model_path)))
                    occlusion.write_text('<r ObjName="x.eu_killzone_2048.ClientTable.RigidStaticInPxScene">'
                        f'<mItems mID="1" mModelFullPath="{model_path}" mPosX="10000" mPosY="10000" mPosZ="6600" '
                        'mRotateX="0" mRotateY="0" mRotateZ="0" mScale="1" '
                        'mBoundingX="10000" mBoundingY="10000" mBoundingZ="6600" mBoundingRadius="200"/></r>')
                    argv.extend(['--world-collision-archives',str(archive)])
                    entity=root/'ENTITYSTATUSINPXSCENE.XML'
                    entity.write_text('<r ObjName="x.eu_killzone_2048.ClientTable.EntityStatusInPxScene">'
                        '<mTable mID="67" mEntityFullName="data.world.EU_KillZone_2048.Own_door_mesh123a" '
                        'mPosX="0" mPosY="0" mPosZ="7000" mRotateX="0" mRotateY="0" mRotateZ="0" mScale="1">'
                        '<mSwitcherStatus mType="EStatus_REVERSIBLE" mSwitcherType="ESwitcher_DOOR" mStatus="0">'
                        '<mDoorRelativeZRotation ArrayCount="3"><mDoorRelativeZRotation v="0"/>'
                        '<mDoorRelativeZRotation v="-1.68"/><mDoorRelativeZRotation v="1.68"/>'
                        '</mDoorRelativeZRotation></mSwitcherStatus></mTable></r>')
                    door_path='Data/Scene/general/building/Own_door_collision.xml'
                    (archive/'Own_door.sfc').write_bytes(sfc(collision_xml(),sfc_path_key(door_path)))
            if interface == '--ingame-overlay':
                world = root / 'world.bin'
                original_world = struct.pack('>III', 0, 1, 0) + bytes(18)
                world.write_bytes(original_world)
                argv.extend(['--environment-hour', '12', '--environment-ready-delay', '.05',
                             '--world-body-file', str(world), '--world-time-tail-bytes', '18'])
            if aircraft:
                plane = root / 'plane.bin'
                spawn = bytearray(plane_body())
                struct.pack_into('>Q', spawn, 0, JEEP_UID)
                plane.write_bytes(spawn)
                argv.extend(['--ingame-menu-collapsed', '--aircraft-align-heading', '--gameplay-motion-ack', '--gameplay-auto-seat',
                             '--gameplay-auto-board-delay', '.1', '--gameplay-initialize-vehicle',
                             '--gameplay-vehicle-config', '4', '--gameplay-aircraft-route-speed', '5000',
                             '--gameplay-aircraft-route-end', '409400', '204800', '75000',
                             '--push-after-map-load', f'0x654b:{plane}'])

            def serve():
                try:
                    local_server.main()
                except BaseException as error:
                    errors.put(error)

            games=[]
            combats=[]
            ais=[]
            views=[]
            def construct_visibility(*args):
                result=StaticVisibility.from_scene(*args);views.append(result);return result
            def construct_ai(*args):
                result=BotAI(*args)
                result.WARMUP=result.EQUIP_DELAY=0
                result.AIM_SECONDS=result.FIRE_INTERVAL=.1
                ais.append(result)
                return result
            def construct_combat(game,bots):
                result=BotCombat(game,bots)
                combats.append(result)
                return result
            def construct_game(**kwargs):
                game=OfflineGameplay(**kwargs)
                games.append(game)
                if throws:game.inventory.items[1,5]=Item(5,50001,0x100110,3)
                if attachments:
                    game.inventory.items[2,1]=Item(4,40305,0x100110,1)
                    game.inventory.items[2,2]=Item(4,40303,0x100111,1)
                    game.inventory.next_uid=max(game.inventory.next_uid,0x100113)
                    if extensions:game.inventory.items[2,3]=Item(4,40403,0x100112,1)
                if medicine:
                    game.inventory.items[2,3]=Item(7,70001,0x100110,2)
                    game.vitals.damage(600)
                return game

            with patch.object(local_server, '__file__', str(root / 'recovery/local_server.py')), \
                    patch('sys.argv', argv), \
                    (patch.object(local_server,'OfflineGameplay',side_effect=construct_game) if throws or medicine or hit_reports or combat or timed_reload or attachments else contextlib.nullcontext()), \
                    (patch.object(local_server,'BotCombat',side_effect=construct_combat) if combat else contextlib.nullcontext()), \
                    (patch.object(local_server,'BotAI',side_effect=construct_ai) if ai else contextlib.nullcontext()), \
                    (patch.object(local_server,'StaticVisibility',SimpleNamespace(from_scene=construct_visibility)) if collision else contextlib.nullcontext()), \
                    (patch.object(BotRoster,'tick',return_value=[]) if combat else contextlib.nullcontext()), \
                    patch.object(local_server, 'ControlServer', side_effect=AssertionError('Native mode must not start HTTP')), \
                    patch.object(local_server, 'OverlayProcess', return_value=contextlib.nullcontext()) as overlay, \
                    contextlib.redirect_stdout(output), contextlib.ExitStack() as cleanup:
                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                cleanup.callback(thread.join, 5)
                client = None
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline and thread.is_alive():
                    try:
                        client = socket.create_connection(('127.0.0.1', port), timeout=.2)
                        break
                    except OSError:
                        time.sleep(.02)
                if client is None and not errors.empty():
                    raise errors.get()
                self.assertIsNotNone(client, output.getvalue())
                with client:
                    client.settimeout(4)
                    client.sendall(frame(3, struct.pack('>IIII', 3, 0, 3, 1) + b'\0'))
                    _, extension, *_ = read_frame(client)
                    client.sendall(frame(9, extension))
                    self.assertEqual(read_frame(client)[0], 4)
                    self.assertEqual(read_frame(client)[0], 1)

                    def send(message, body):
                        packet = struct.pack('>IH', 26 + len(body), message) + bytes(16) + struct.pack('>I', message) + body
                        client.sendall(frame(0, body=encrypt(packet, bytes(16))))

                    startup, flight_packets = True, []
                    life_packets=[]

                    def receive_raw():
                        _, _, cipher, *_ = read_frame(client)
                        packet = decrypt(cipher, bytes(16))
                        return struct.unpack_from('>H', packet, 4)[0], packet[10:]

                    def receive():
                        while True:
                            message, body = receive_raw()
                            if ai and message==0x547:
                                self.assertEqual(struct.unpack_from('>Q',body)[0],next(iter(combats[0].bots.actors)))
                                continue
                            if vitals and message==0x1069:
                                life_packets.append(body)
                                continue
                            if population and message == 0x27:
                                continue
                            if population and message == 0x565:
                                self.assertEqual(receive_raw()[0],0xbe7)
                                self.assertEqual(receive_raw()[0],0x1069)
                                continue
                            if aircraft and (message == 0x6563 or startup and
                                             message in (0x6554, 0x656e, 0x656d, 0x6542, 0x6564, 0x6565)):
                                flight_packets.append((message, body))
                                continue
                            return message, body

                    if interface == '--ingame-overlay':
                        send(0x02e4, bytes(4))
                        world_id, world_body = receive()
                        self.assertEqual(world_id, 0x02ef)
                        world_time = struct.unpack_from('>I', world_body, len(world_body) - 18)[0]
                        self.assertLess(abs(world_time - time.time()), 3)
                        self.assertEqual(world.read_bytes(), original_world)
                    send(0x0dcd, bytes(4))
                    if aircraft:
                        send(0x0dcd, bytes(4))
                        spawn_id, spawn_body = receive()
                        self.assertEqual(spawn_id, 0x654b)
                        rotation = struct.unpack_from('>4f', spawn_body, 12 + len(b'Aircraft\0') + 25)
                        self.assertLess(rotation[2], -.7)
                    initial = (200, 204800, 75000) if aircraft else (325800, 271700, 6501)
                    send(0x002a, struct.pack('>I3i', 1, *initial))
                    self.assertEqual(receive()[0], 0x821)
                    if posture:
                        message,payload=receive()
                        self.assertEqual(message,0x516)
                        self.assertEqual(len(payload),83)
                        records=[struct.unpack_from('>BII',payload,i) for i in range(2,len(payload),9)]
                        self.assertEqual(records,[(i,280,280) for i in range(17,22)]
                                         +[(i,120,120) for i in range(24,28)])
                        send(0x002a,struct.pack('>I3i',1,325850,271700,6501))
                    if population:
                        generated=[]
                        while len(generated)<69:
                            row=receive_raw()
                            if vitals and row[0]==0x1069 and struct.unpack_from('>Q',row[1])[0]==256:
                                life_packets.append(row[1])
                            else:generated.append(row)
                        self.assertEqual([m for m, _ in generated],
                            [0x821]*56 + [0x654b, 0x6554, 0x656e]*3 + [0x565, 0xbe7, 0x1069, 0x27])
                        bot_uid = struct.unpack_from('>Q', generated[-3][1], 8)[0]
                        self.assertNotEqual(bot_uid, 256)
                        self.assertEqual(struct.unpack('>QBBBII',generated[-2][1]),(bot_uid,0,1,0,1000,1000))
                    if interface == '--ingame-overlay':
                        clock_id, clock_body = receive()
                        self.assertEqual(clock_id, 0x4816)
                        self.assertEqual(struct.unpack_from('>I', clock_body)[0], 12)
                        clock_time = struct.unpack_from('>I', clock_body, 4)[0]
                        self.assertLess(abs(clock_time - world_time), 3)
                    if population:
                        if collision:
                            geometry=views[0].doors
                            self.assertIs(geometry.states,games[0].doors.states)
                            ray=((0,-150,7000),(0,150,7000))
                            self.assertFalse(geometry.blocks(*ray))
                            send(0x6f57,struct.pack('>II',67,1))
                            self.assertEqual(receive(),(0x6f55,struct.pack('>5I',67,1,1,0,0)))
                            self.assertTrue(geometry.blocks(*ray))
                            send(0x6f57,struct.pack('>II',67,0))
                            self.assertEqual(receive(),(0x6f55,struct.pack('>5I',67,0,1,0,0)))
                            self.assertFalse(geometry.blocks(*ray))
                        send(0x6f57, struct.pack('>II', 17415, 1))
                        self.assertEqual(receive(), (0x6f55, struct.pack('>5I', 17415, 1, 1, 0, 0)))
                        send(0xbe6, struct.pack('>IIQ', 2, 1, bot_uid))
                        profile_id, queried_profile = receive()
                        self.assertEqual(profile_id, 0xbe7)
                        self.assertEqual(struct.unpack_from('>II',queried_profile),(3,1))
                        self.assertEqual(struct.unpack_from('>Q', queried_profile, 8)[0], bot_uid)
                        self.assertEqual(receive_raw(),(0x1069,struct.pack('>QBBBII',bot_uid,0,1,0,1000,1000)))
                    if vitals:
                        send(0x002a,struct.pack('>I3i',2,325850,271700,6501))
                    directory = next((root / 'recovery/private/ingame-control').glob('session-*'))
                    self.assertEqual((game / 'ROE_OfflineMenu.lua').exists(), interface == '--ingame-control')
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline:
                        try:
                            status = (directory / 'status.txt').read_text(encoding='utf-8')
                        except PermissionError:
                            time.sleep(.01)
                            continue
                        if 'ready=1\n' in status:
                            break
                        time.sleep(.05)
                    self.assertIn('ready=1\n', status)
                    menu = MailboxClient(directory)
                    packets = []
                    for command, count in ((dict(action='weather', weather_id=2, transition=30), 1),
                                           (dict(action='weapon', template=10202, ammo=60, distance=3, count=1), 2),
                                           (dict(action='vehicle', config=101, distance=6), 3)):
                        if aircraft and command['action'] == 'weapon':
                            self.assertIn(0x6542, [message for message, _ in flight_packets])
                            launch = next(body for message, body in flight_packets if message == 0x6564)
                            self.assertEqual(struct.unpack_from('>3i', launch, 8), (200, 204800, 75000))
                            startup = False
                            send(0x6566, b'\0')
                            self.assertEqual(receive()[0], 0x6544)
                            self.assertEqual(receive()[0], 0x656d)
                            send(0x002a, struct.pack('>I3i', 2, 325800, 271700, 6501))
                            for sequence in range(1, 81):
                                destination = (325800 + sequence * 100, 280000, 9000)
                                send(0x002a, move_body(sequence, [(325800, 271700, 6501), destination]))
                                ack_id, ack_body = receive()
                                self.assertEqual((ack_id, ack_body), (0x36, struct.pack('>I', sequence)))
                        seq = menu.send(command)
                        packets.extend(receive() for _ in range(count))
                        deadline = time.monotonic() + 3
                        while time.monotonic() < deadline:
                            try:
                                state = menu.state()
                            except PermissionError:
                                time.sleep(.01)
                                continue
                            if int(state['seq']) >= seq:
                                break
                            time.sleep(.02)
                        self.assertEqual(state['status'], 'sent')
                    self.assertEqual([message for message, _ in packets], [0x4817, 0x821, 0x821, 0x654b, 0x6554, 0x656e])
                    if vitals:
                        self.assertEqual(len(life_packets),1)
                        self.assertEqual(struct.unpack('>QBBBII',life_packets[0]),(256,0,1,0,400 if medicine else 1000,1000))
                    if aircraft:
                        jeep = packets[3][1]
                        name_length = struct.unpack_from('>I', jeep, 8)[0]
                        self.assertEqual(struct.unpack_from('>3i', jeep, 24 + name_length),
                                         (334400, 280000, 9100))
                    if attachments:
                        g=games[0];gun=g.inventory.items[1,1]
                        for source,src,src_slot,target,dst,dst_slot in (
                                (0,2,1,gun.uid,3,2),
                                (0x100111,2,2,gun.uid,3,2),
                                (gun.uid,3,2,0,2,1)):
                            send(0x3e80,struct.pack('>BQBHQBHHB',6,source,src,src_slot,target,dst,dst_slot,1,1))
                            self.assertEqual(receive_raw()[0],0x3e82)
                            self.assertEqual(receive_raw(),(0x3e81,struct.pack('>BIIB',6,0,40303 if source else 40305,1)))
                            self.assertEqual(g.magazine,30)
                        self.assertEqual(g.inventory.items[1,1].parts,())
                        self.assertEqual(g.inventory.items[2,1].template,40303)
                        self.assertEqual(g.inventory.items[2,2].template,40305)
                        if extensions:
                            send(0x3e80,struct.pack('>BQBHQBHHB',6,0,2,3,gun.uid,3,3,1,1))
                            self.assertEqual(receive_raw()[0],0x3e82)
                            self.assertEqual(receive_raw(),(0x3e81,struct.pack('>BIIB',6,0,40403,1)))
                            send(0x49c,struct.pack('>I',1))
                            self.assertEqual(receive_raw(),(0x49d,struct.pack('>II',1,0)))
                            self.assertEqual(receive_raw(),(0x4a0,struct.pack('>QII',256,1,40)))
                            self.assertEqual(receive_raw()[0],0x3e82)
                            self.assertEqual((g.magazine,g.inventory.reserve_for(30001)),(40,110))
                            send(0x3e80,struct.pack('>BQBHQBHHB',6,gun.uid,3,3,0,2,3,1,1))
                            self.assertEqual(receive_raw()[0],0x3e82)
                            self.assertEqual(receive_raw(),(0x3e81,struct.pack('>BIIB',6,0,40403,1)))
                            self.assertEqual((g.magazine,g.inventory.reserve_for(30001)),(30,120))
                        client.settimeout(.2)
                        with self.assertRaises(socket.timeout):read_frame(client)
                        client.settimeout(4)
                    if timed_reload:
                        shot=struct.pack('>6fIB',325800,271700,6600,327000,271700,6600,0,0)
                        send(0x11d3,shot)
                        send(0x49c,struct.pack('>I',1))
                        self.assertEqual(receive(),(0x49d,struct.pack('>II',1,0)))
                        self.assertEqual(games[0].magazine,29)
                        client.settimeout(.1)
                        with self.assertRaises(socket.timeout):read_frame(client)
                        client.settimeout(4)
                        self.assertEqual(receive_raw()[0],0x4a0)
                        self.assertEqual(receive_raw()[0],0x3e82)
                        self.assertEqual((games[0].magazine,games[0].inventory.reserve_for(30001)),(30,119))
                        send(0x11d3,shot);send(0x49c,struct.pack('>I',1))
                        self.assertEqual(receive(),(0x49d,struct.pack('>II',1,0)))
                        send(0x49e,bytes(4))
                        client.settimeout(2.1 if original_reload else .6)
                        with self.assertRaises(socket.timeout):read_frame(client)
                        client.settimeout(4)
                        self.assertEqual(games[0].inventory.weapon_magazines[0x100101],29)
                        self.assertEqual(games[0].inventory.reserve_for(30001),119)
                    if throws:
                        begin,end=throw_start(),throw_finish()
                        endpoint=(326000,271700,6500)
                        if blast:
                            endpoint=tuple(games[0].player_position)
                            begin,end=bytearray(begin),bytearray(end)
                            struct.pack_into('>3i',begin,4,*endpoint[:2],endpoint[2]+145)
                            struct.pack_into('>3i',end,8,*endpoint)
                            begin,end=bytes(begin),bytes(end)
                        send(0x1004,begin+b'\x18'*8)
                        self.assertEqual(receive(),(0x1005,struct.pack('>3I',50001,37,0)))
                        self.assertEqual(receive()[0],0x3e82)
                        send(0x1004,begin+b'\x29'*8)
                        self.assertEqual(receive(),(0x1005,struct.pack('>3I',50001,37,0)))
                        send(0x1007,end+b'\x37'*8)
                        self.assertEqual(receive(),(0x1008,struct.pack('>3I',50001,37,0)))
                        self.assertEqual(receive(),(0x1009,struct.pack('>II3iBQI',50001,37,*endpoint,0,256,0)))
                        if blast:
                            self.assertEqual(receive_raw(),(0x1069,struct.pack('>QBBBII',256,0,1,0,0,1000)))
                            self.assertEqual(receive_raw(),(0x533,struct.pack('>IQ',0,256)))
                            self.assertEqual(games[0].vitals.current,0)
                        send(0x1007,end)
                        self.assertEqual(receive(),(0x1008,struct.pack('>3I',50001,37,0)))
                        client.settimeout(.2)
                        with self.assertRaises(socket.timeout):read_frame(client)
                        client.settimeout(4)
                    if medicine:
                        started=time.monotonic()
                        send(0x3e80,medicine_request()+b'\x18'*8)
                        self.assertEqual(receive(),(0x3e81,struct.pack('>BIIB',3,0,70001,1)))
                        if cancel_medicine:
                            motion=bytearray(move_body(20,[(325850,271700,6501)]*2))
                            motion[17]=20
                            send(0x2a,bytes(motion))
                            client.settimeout(3.3)
                            with self.assertRaises(socket.timeout):read_frame(client)
                            client.settimeout(4)
                            self.assertEqual(games[0].vitals.current,400)
                            self.assertEqual(games[0].inventory.items[2,3].count,2)
                            self.assertIsNone(games[0].medicine.pending)
                            started=time.monotonic()
                            send(0x3e80,medicine_request())
                            self.assertEqual(receive(),(0x3e81,struct.pack('>BIIB',3,0,70001,1)))
                        send(0x3e80,medicine_request()+b'\x29'*8)
                        self.assertEqual(receive()[0],0x3e82)
                        self.assertGreaterEqual(time.monotonic()-started,2.8)
                        self.assertEqual(receive_raw(),(0x1069,struct.pack('>QBBBII',256,0,1,0,500,1000)))
                    if hit_reports:
                        before=(games[0].vitals.current,games[0].magazine)
                        send(0x11e9,hit_body()+b'\x18'*8)
                        send(0x11e9,hit_body()[:-1])
                        client.settimeout(.2)
                        with self.assertRaises(socket.timeout):read_frame(client)
                        client.settimeout(4)
                        self.assertEqual((games[0].vitals.current,games[0].magazine),before)
                    if combat and not ai:
                        roster=combats[0].bots
                        roster.actors[bot_uid]['position']=(326000,271700,6500)
                        roster.vitals[bot_uid].damage(960)
                        for sequence,current in ((37,20),(38,0)):
                            send(0x11d3,struct.pack('>6fIB',325800,271700,6600,327000,271700,6600,0,0)+bytes(8))
                            send(0x11e9,struct.pack('>I',sequence)+hit_body()[4:]+bytes(8))
                            self.assertEqual(receive_raw(),(0x1069,struct.pack('>QBBBII',bot_uid,0,1,0,current,1000)))
                            self.assertEqual(receive_raw(),(0x11eb,struct.pack('>QQ3iBBIB',256,bot_uid,0,0,100,0,2,20,int(current==0))))
                            if not current:self.assertEqual(receive_raw(),(0x533,struct.pack('>IQ',0,bot_uid)))
                        self.assertEqual(games[0].magazine,28)
                        self.assertEqual(roster.vitals[bot_uid].current,0)
                    if ai:
                        roster=combats[0].bots
                        roster.actors[bot_uid]['position']=(326000,271700,6500)
                        games[0].vitals.current=40
                        hp=[];firing=[];feedback=[];dead=None
                        deadline=time.monotonic()+5
                        client.settimeout(.5)
                        while time.monotonic()<deadline and dead is None:
                            games[0].accept_self_position((325850,271700,6501))
                            try:mid,body=receive_raw()
                            except socket.timeout:continue
                            if mid==0x11d4:
                                firing.append(body[-1])
                                self.assertEqual(struct.unpack_from('>Q',body)[0],bot_uid)
                            elif mid==0x1069:
                                self.assertEqual(struct.unpack_from('>Q',body)[0],256)
                                hp.append(struct.unpack_from('>I',body,11)[0])
                            elif mid==0x11eb:
                                self.assertEqual(struct.unpack_from('>QQ',body),(bot_uid,256))
                                feedback.append(body)
                            elif mid==0x533:dead=body
                            else:self.assertEqual(mid,0x547)
                        client.settimeout(4)
                        self.assertEqual(hp,[20,0])
                        self.assertEqual(firing,[0,1,0,1])
                        self.assertEqual(len(feedback),2)
                        self.assertEqual(dead,struct.pack('>IQ',0,256))
                        self.assertEqual(ais[0].brains[bot_uid].magazine,28)
                    client.sendall(frame(13))
                thread.join(5)
                self.assertFalse(thread.is_alive())
            if not errors.empty():
                raise errors.get()
            if hit_reports:
                rows=[json.loads(line) for line in output.getvalue().splitlines() if line.startswith('{')]
                reports=[r for r in rows if r.get('event')=='character_hit_report']
                rejected=[r for r in rows if r.get('event')=='character_hit_report_rejected']
                self.assertEqual(len(reports),1)
                self.assertEqual(reports[0]['target_uid'],0x1000000001100)
                self.assertEqual(reports[0]['ray_origin'],[325800,271700,6600])
                self.assertEqual(reports[0]['impact'],[326000.,271700.,6600.])
                self.assertIs(reports[0]['damage_applied'],False)
                self.assertEqual(len(rejected),1)
            if blast:
                rows=[json.loads(line) for line in output.getvalue().splitlines() if line.startswith('{')]
                hits=[r for r in rows if r.get('event')=='throwable_combat' and r.get('action')=='blast_hit']
                self.assertEqual([(r['target_uid'],r['current']) for r in hits],[(256,0)])
                if collision:
                    ready=[r for r in rows if r.get('event')=='world_collision_ready']
                    self.assertEqual([(r['models'],r['shapes'],r['fallback_models']) for r in ready],[(2,4,0)])
                    doors=[r for r in rows if r.get('event')=='world_door_collision_ready']
                    self.assertEqual([(r['doors'],r['unmatched']) for r in doors],[(1,0)])
            if combat and not ai:
                rows=[json.loads(line) for line in output.getvalue().splitlines() if line.startswith('{')]
                changes=[r for r in rows if r.get('event')=='bot_combat']
                self.assertEqual([r['current'] for r in changes],[20,0])
                self.assertTrue(all(r['accepted'] and r['damage_applied'] for r in changes))
            if ai:
                rows=[json.loads(line) for line in output.getvalue().splitlines() if line.startswith('{')]
                changes=[r for r in rows if r.get('event')=='bot_ai' and r.get('action')=='player_hit']
                self.assertEqual([r['current'] for r in changes],[20,0])
            if cancel_medicine:
                rows=[json.loads(line) for line in output.getvalue().splitlines() if line.startswith('{')]
                cancelled=[r for r in rows if r.get('event')=='medicine_cancelled']
                self.assertEqual(len(cancelled),1)
                self.assertEqual(cancelled[0]['action'],20)
            if posture:
                self.assertEqual(output.getvalue().count('"event": "posture_speed_delta_sent"'),1)
            if interface == '--ingame-overlay':
                overlay.assert_called_once_with(directory, start_collapsed=aircraft)
            else:
                overlay.assert_not_called()
            self.assertFalse((game / 'ROE_OfflineMenu.lua').exists())
            self.assertFalse((game / 'Data/ScriptCustom/ROE_OfflineMenu.lua').exists())
            self.assertFalse((game / 'Data/ScriptCustom/LoadConfig.lua').exists())
            self.assertFalse((game / 'FileDriven/_GM_CONTROL_').exists())
            self.assertIn('ready=0\n', (directory / 'status.txt').read_text(encoding='utf-8'))
            with self.assertRaisesRegex(RuntimeError, '进入地图'):
                menu.send(dict(action='weather', weather_id=2))


if __name__ == '__main__':
    unittest.main()
