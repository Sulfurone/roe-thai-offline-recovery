"""Experimental loopback TPDU server with incomplete offline gameplay."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
from tpdu import auth_info, decrypt, encrypt, frame, read_frame
from thai_profile import save_submission
from offline_environment import environment_clock
from offline_gameplay import OfflineGameplay,ACTOR_UID,JEEP_UID,TYPED_ACTOR_UID,TYPED_VEHICLE_UID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=75)
    parser.add_argument('--port', type=int, default=8001,
                        help='Loopback port for this experiment (old clients use 8001)')
    parser.add_argument('--launch', action='store_true')
    parser.add_argument('--single-session',action='store_true',
                        help='Exit after the authenticated client disconnects, releasing the local port')
    parser.add_argument('--environment-hour', type=int, choices=range(24), metavar='0..23',
                        help='Initialize the native environment clock after map load (12 is noon)')
    parser.add_argument('--gameplay-prototype', action='store_true',
                        help='Opt in to unverified Thai ammo and vehicle interaction handlers')
    parser.add_argument('--gameplay-arsenal',action='store_true',
                        help='Seed recovered firearms/ammunition in a fresh ground-loot world')
    parser.add_argument('--gameplay-scatter-loot',action='store_true',
                        help='Spawn a weapon/ammo cluster every 600m of reported ground travel')
    parser.add_argument('--gameplay-auto-seat', action='store_true',
                        help='Diagnostic: board the test Jeep after its first physics report')
    parser.add_argument('--gameplay-vehicle-config',type=int,choices=[3,4,101],default=101,
                        help='Original Thai test vehicle: glider=3, helicopter=4, Jeep=101')
    parser.add_argument('--gameplay-typed-uids',action='store_true',
                        help='Candidate entity UID type bits; requires matching typed fixture set')
    parser.add_argument('--gameplay-initialize-vehicle',action='store_true',
                        help='Diagnostic health/status and oil initialization before boarding')
    parser.add_argument('--gameplay-auto-exit-seconds',type=float,default=0,
                        help='Diagnostic only: force exit after this many seconds seated; zero disables')
    parser.add_argument('--gameplay-aircraft-route-speed',type=int,choices=range(0,5001),default=0,
                        metavar='CM_PER_SECOND',help='Diagnostic helicopter route speed; zero disables')
    parser.add_argument('--gameplay-starting-magazine',type=int,choices=range(31),default=30,
                        metavar='0..30',help='Initial M4A1 magazine for the opt-in offline loadout')
    parser.add_argument('--gameplay-inventory',action='store_true',
                        help='Enable verified own-inventory transfers/splits for the offline loadout')
    parser.add_argument('--gameplay-state-file',type=Path,
                        help='Opt-in local inventory/ammunition profile, written atomically')
    parser.add_argument('--gameplay-inventory-selftest',action='store_true',
                        help='Diagnostic: split ammo and move the gun between primary slots once')
    parser.add_argument('--gameplay-ground-loot',action='store_true',
                        help='Fresh ground test: finite 5.56 stack, pickup and ammunition drop')
    parser.add_argument('--gameplay-world-file',type=Path,
                        help='Atomic combined inventory and finite ground-loot profile')
    parser.add_argument('--gameplay-opening-airdrop',action='store_true',
                        help='Opening aircraft route: native jump prompt after 3 seconds and exit at route end')
    parser.add_argument('--gameplay-opening-glider-file',type=Path,
                        help='Original config-3 spawn body: unfold a separate glider after aircraft exit')
    parser.add_argument('--gameplay-landing-terrain',type=Path,
                        help='Original RigidTerrain.repx for near-ground glider release')
    parser.add_argument('--gameplay-aircraft-route-end',type=int,nargs=3,metavar=('X','Y','Z'),
                        help='Optional finite aircraft endpoint in original world centimetres')
    parser.add_argument('--client-arg', action='append', default=[],
                        help='Extra argument passed to the launched client (repeatable)')
    parser.add_argument('--probe-auth-response', action='store_true',
                        help='Try an explicitly unverified default-field 0x02F1 response')
    parser.add_argument('--probe-world-response', action='store_true',
                        help='Try an empty/default-field 0x02EF character roster response')
    parser.add_argument('--roster-file', type=Path,
                        help='Send this captured compact 0x02EF frame unchanged (experimental)')
    parser.add_argument('--world-body-file', type=Path,
                        help='Send this exact 0x02EF body behind a compact >IHI header (experimental)')
    parser.add_argument('--enter-body-file', type=Path,
                        help='Send this exact 0x032B body after native ENTER_GAME (experimental)')
    parser.add_argument('--team-body-file', type=Path,
                        help='Send this exact 0x7030 body after TEAM_MSGID_PULL_INFO_REQ (experimental)')
    parser.add_argument('--ready-body-file', type=Path,
                        help='Send this exact 0x7038 body after TEAM_MSGID_READY_REQ 0x7037 (experimental)')
    parser.add_argument('--match-body-file', type=Path,
                        help='Send this exact 0x6E2A body after MATCH_MSGID_START_REQ 0x6E29 (experimental)')
    parser.add_argument('--team-sync-file', type=Path,
                        help='Push this exact 0x7025 body right after each 0x7038 ready reply (experimental)')
    parser.add_argument('--match-push-file', type=Path,
                        help='Push this exact 0x6E2A body right after the 0x7030 team reply (experimental)')
    parser.add_argument('--room-start-file', type=Path,
                        help='Push this 0x6F02 after match start or ROOM_START_REQ 0x6EFB (experimental)')
    parser.add_argument('--match-sync-file', type=Path,
                        help='Push this exact 0x6E2D body right before --room-start-file on every ready/team trigger (experimental)')
    parser.add_argument('--push-after-team', action='append', default=[], metavar='MSGID:FILE',
                        help='After the 0x7030 team reply, push MSGID (hex) with body FILE, in order (repeatable)')
    parser.add_argument('--push-after-load-success', action='append', default=[], metavar='MSGID:FILE',
                        help='Once per connection after Thai CLIENT_LOAD_SUCCESS 0x0DCD, push these candidate bodies')
    parser.add_argument('--push-after-player-ready',action='append',default=[],metavar='MSGID:FILE',
                        help='Once after map-load notification and the first actor MOVE_1, push these bodies')
    parser.add_argument('--push-delay', type=float, default=1.0,
                        help='Seconds between --push-after-team packets')
    parser.add_argument('--compact-responses', action='store_true',
                        help='Use the compact server envelope documented by community research')
    parser.add_argument('--probe-create-response', action='store_true',
                        help='Try a Thai create-character reply; schema remains experimental')
    parser.add_argument('--create-body-file', type=Path,
                        help='0x0303 body sent verbatim behind a compact >IHI header')
    parser.add_argument('--create-response-mode', default='zeros',
                        choices=['zeros', 'zeros64', 'zeros64-uid4', 'zeros64-uid12',
                                 'echo', 'ret-echo', 'ret-uid-echo',
                                 'ret1-echo', 'ret1-uid', 'ret1-uid-echo'],
                        help='Experimental 0x0303 body shape derived from the received request')
    parser.add_argument('--create-mode-file', type=Path,
                        help='Re-read this file before every 0x02F9; its content overrides '
                             '--create-response-mode ("file:<path>" sends that file raw)')
    parser.add_argument('--create-sweep-dir', type=Path,
                        help='Send every *.bin in this directory as a 0x0303 body in order')
    parser.add_argument('--create-sweep-delay', type=float, default=2.0,
                        help='Seconds between sweep bodies')
    parser.add_argument('--create-zeros', type=int, default=0,
                        help='Send this many zero bytes as the 0x0303 body')
    parser.add_argument('--loose-scripts', action='store_true',
                        help='Test the native -useallfiles switch for a temporary ScriptCustom diagnostic')
    parser.add_argument('--key-hex', default='00' * 16,
                        help='Test session key; not yet established for this client')
    args = parser.parse_args()
    opening_glider_body=None
    landing_height=None
    if args.gameplay_opening_glider_file is not None:
        if not args.gameplay_opening_airdrop or args.gameplay_landing_terrain is None:
            parser.error('Opening glider requires opening-airdrop and landing-terrain')
        from offline_terrain import TerrainSurface
        try:
            if args.gameplay_opening_glider_file.stat().st_size>65536:
                raise ValueError('Glider spawn exceeds the wire size bound')
            opening_glider_body=args.gameplay_opening_glider_file.read_bytes()
            landing_height=TerrainSurface.from_repx(args.gameplay_landing_terrain).height_at
            OfflineGameplay(vehicle_config=4,auto_board=True,opening_airdrop=True,
                            aircraft_route_speed=2000,auto_exit_after=40,
                            opening_glider_body=opening_glider_body)
        except (OSError,ValueError,TypeError) as error:
            parser.error(f'Cannot prepare opening glider: {error}')
    elif args.gameplay_landing_terrain is not None:
        parser.error('Landing terrain requires the opening glider option')
    if args.gameplay_state_file and not (args.gameplay_prototype and args.gameplay_inventory):
        parser.error('--gameplay-state-file requires --gameplay-prototype and --gameplay-inventory')
    if args.gameplay_inventory_selftest and (not args.gameplay_prototype or not args.gameplay_inventory or args.gameplay_state_file):
        parser.error('Inventory self-test requires the prototype/inventory options and no state file')
    if args.gameplay_arsenal and not args.gameplay_ground_loot:
        parser.error('--gameplay-arsenal requires --gameplay-ground-loot')
    if args.gameplay_scatter_loot and not args.gameplay_ground_loot:
        parser.error('--gameplay-scatter-loot requires --gameplay-ground-loot')
    if args.gameplay_ground_loot and (not args.gameplay_prototype or not args.gameplay_inventory
            or args.gameplay_state_file):
        parser.error('Ground loot requires the prototype/inventory options without an inventory-only profile')
    if args.gameplay_world_file and (not args.gameplay_ground_loot or args.gameplay_state_file or args.gameplay_inventory_selftest):
        parser.error('World persistence requires ground loot and a separate combined profile')
    if args.gameplay_aircraft_route_end and any(abs(x)>=2000000 for x in args.gameplay_aircraft_route_end):
        parser.error('Aircraft route endpoint is outside the validated coordinate bound')
    maximum_speed=5000 if args.gameplay_aircraft_route_end is not None else 2500
    maximum_duration=180 if args.gameplay_aircraft_route_end is not None else 40
    if args.gameplay_opening_airdrop and (not args.gameplay_prototype or args.gameplay_vehicle_config!=4
            or not args.gameplay_auto_seat or not 0<args.gameplay_aircraft_route_speed<=maximum_speed
            or not 3<args.gameplay_auto_exit_seconds<=maximum_duration):
        parser.error('Opening airdrop requires aircraft auto-seat and a bounded route/speed/duration')
    if args.gameplay_state_file:
        try:
            OfflineGameplay(inventory_enabled=True,state_file=args.gameplay_state_file)
        except (OSError,ValueError) as error:
            parser.error(f'Offline inventory profile was preserved; cannot load it: {error}')
    if args.gameplay_world_file:
        try:
            OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,world_file=args.gameplay_world_file)
        except (OSError,ValueError) as error:
            parser.error(f'Offline world profile was preserved; cannot load it: {error}')
    if args.roster_file and args.world_body_file:
        parser.error('use either --roster-file or --world-body-file, not both')
    world_body = None
    enter_body = args.enter_body_file.read_bytes() if args.enter_body_file else None
    team_body = args.team_body_file.read_bytes() if args.team_body_file else None
    ready_body = args.ready_body_file.read_bytes() if args.ready_body_file else None
    match_body = args.match_body_file.read_bytes() if args.match_body_file else None
    team_sync_body = args.team_sync_file.read_bytes() if args.team_sync_file else None
    match_push_body = args.match_push_file.read_bytes() if args.match_push_file else None
    room_start_body = args.room_start_file.read_bytes() if args.room_start_file else None
    match_sync_body = args.match_sync_file.read_bytes() if args.match_sync_file else None
    if args.world_body_file:
        world_body = args.world_body_file.read_bytes()
        if len(world_body) < 26:
            parser.error('world body file is too short for an application envelope')
    roster = None
    if args.roster_file:
        roster = args.roster_file.read_bytes()
        # Canonical compact frame: BE32 stamp | BE16 0x02EF | BE32 tag whose low
        # half is 0x02EF. Files that are not in this exact form must be passed as
        # a bare body through --world-body-file; rewriting headers was shown to
        # corrupt the body (lobby-default-0.bin is already a compact frame).
        if len(roster) < 10 or roster[4:6] != b'\x02\xef' or roster[8:10] != b'\x02\xef':
            parser.error('roster file is not a compact 0x02EF frame; '
                         'pass the bare body via --world-body-file instead')
    key = bytes.fromhex(args.key_hex)
    if len(key) != 16:
        parser.error('key must contain 16 bytes')
    push_specs = []
    for spec in args.push_after_team:
        message, separator, path = spec.partition(':')
        if not separator or not path:
            parser.error(f'--push-after-team expects MSGID:FILE, got {spec!r}')
        try:
            push_specs.append((int(message, 16), Path(path)))
        except ValueError:
            parser.error(f'--push-after-team message id is not hexadecimal: {spec!r}')
    loaded_push_specs = []
    for spec in args.push_after_load_success:
        message, separator, path = spec.partition(':')
        if not separator or not path:
            parser.error(f'--push-after-load-success expects MSGID:FILE, got {spec!r}')
        try:
            message_id = int(message, 16)
            if not 0 <= message_id <= 0xffff:
                raise ValueError('message id out of range')
        except ValueError:
            parser.error(f'invalid --push-after-load-success message id: {spec!r}')
        loaded_push_specs.append((message_id, Path(path)))
    player_push_specs = []
    for spec in args.push_after_player_ready:
        message, separator, path = spec.partition(':')
        try:
            message_id = int(message,16)
            if not separator or not path or not 0<=message_id<=0xffff:
                raise ValueError('invalid spec')
        except ValueError:
            parser.error(f'--push-after-player-ready expects MSGID:FILE: {spec!r}')
        player_push_specs.append((message_id,Path(path)))
    if args.create_body_file and args.create_zeros:
        parser.error('use either --create-body-file or --create-zeros, not both')
    create_body = None
    if args.create_body_file:
        create_body = args.create_body_file.read_bytes()
    elif args.create_zeros:
        create_body = bytes(args.create_zeros)
    root = Path(__file__).resolve().parent.parent
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    folder = root / 'recovery' / 'logs' / ('handshake-' + stamp)
    folder.mkdir(parents=True)
    log = (folder / 'server.jsonl').open('w', encoding='utf-8')

    def emit(event, **fields):
        record = {'time': datetime.datetime.now().astimezone().isoformat(), 'event': event, **fields}
        log.write(json.dumps(record) + '\n')
        log.flush()
        print(json.dumps(record), flush=True)

    def send(connection, command, extension=b'', body=b''):
        packet = frame(command, extension, body)
        connection.sendall(packet)
        emit('sent', command=command, bytes=len(packet))

    deadline = time.monotonic() + args.seconds
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', args.port))
        listener.listen(4)
        listener.settimeout(1)
        emit('listening', address=f'127.0.0.1:{args.port}',
             key_status='Unverified test session key')
        if args.launch:
            executable = str(root / '32838' / 'Europa_Client.exe')
            arguments = ['-garena', '-uid=1', '-language=en',
                         f'-server=127.0.0.1:{args.port}']
            arguments.extend(args.client_arg)
            if args.loose_scripts:
                arguments.append('-useallfiles')
            os.startfile(executable, arguments=subprocess.list2cmdline(arguments),
                         cwd=str(root / '32838'))
            emit('shell_launch_requested', arguments=arguments)
        number = 0
        while time.monotonic() < deadline:
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            number += 1
            with connection:
                connection.settimeout(min(45, max(1, deadline - time.monotonic())))
                challenge = os.urandom(16)
                state = 'await_auth'
                loaded_pushes_sent = False
                player_pushes_sent = False
                gameplay = OfflineGameplay(auto_board=args.gameplay_auto_seat,
                    magazine=args.gameplay_starting_magazine,
                    inventory_enabled=args.gameplay_inventory,state_file=args.gameplay_state_file,
                    inventory_selftest=args.gameplay_inventory_selftest,
                    ground_loot_enabled=args.gameplay_ground_loot,
                    arsenal_enabled=args.gameplay_arsenal,
                    scatter_loot=args.gameplay_scatter_loot,
                    world_file=args.gameplay_world_file,
                    opening_airdrop=args.gameplay_opening_airdrop,
                    opening_glider_body=opening_glider_body,landing_height=landing_height,
                    aircraft_route_end=tuple(args.gameplay_aircraft_route_end) if args.gameplay_aircraft_route_end else None,
                    vehicle_config=args.gameplay_vehicle_config,
                    actor_uid=TYPED_ACTOR_UID if args.gameplay_typed_uids else ACTOR_UID,
                    vehicle_uid=TYPED_VEHICLE_UID if args.gameplay_typed_uids else JEEP_UID,
                    initialize_vehicle=args.gameplay_initialize_vehicle,
                    aircraft_route_speed=args.gameplay_aircraft_route_speed,
                    auto_exit_after=args.gameplay_auto_exit_seconds) if args.gameplay_prototype else None
                if gameplay is not None and gameplay.inventory is not None:
                    emit('gameplay_inventory_ready',magazine=gameplay.magazine,reserve=gameplay.reserve,
                         weapon_slot=gameplay.inventory.weapon_slot(),entries=len(gameplay.inventory.items),
                         restored=bool((args.gameplay_world_file and args.gameplay_world_file.exists())
                                       or (args.gameplay_state_file and args.gameplay_state_file.exists())),
                         world_profile=str(args.gameplay_world_file) if args.gameplay_world_file else None,
                         ground_stacks=len(gameplay.ground_loot.stacks) if gameplay.ground_loot else None)
                try:
                    while time.monotonic() < deadline:
                        command, extension, body, encrypted_length, packet = read_frame(connection)
                        with (folder / f'{number}-received.bin').open('ab') as raw:
                            raw.write(packet)
                        emit('received', connection=number, command=command, bytes=len(packet), state=state)
                        if command == 3 and state == 'await_auth':
                            info = auth_info(extension)
                            emit('auth_header', **info)
                            if info['uid'] != 1 or info['encryption_method'] != 3:
                                raise ValueError('Only the synthetic uid=1 AES test client is accepted')
                            payload = encrypt(challenge, key)
                            send(connection, 8, bytes([len(payload)]) + payload)
                            state = 'await_synack'
                        elif command == 9 and state == 'await_synack':
                            if not extension or extension[0] != len(extension) - 1:
                                raise ValueError('Invalid SYNACK length')
                            returned = decrypt(extension[1:], key)
                            if returned != challenge:
                                raise ValueError('SYNACK challenge mismatch')
                            emit('handshake_challenge_verified')
                            identity = encrypt(struct.pack('>I', 1) + bytes(16), key)
                            send(connection, 4, struct.pack('>I', len(identity)) + identity)
                            new_key = bytes(16)
                            wrapped = encrypt(new_key, key)
                            send(connection, 1, struct.pack('>HH', 0, len(wrapped)) + wrapped)
                            key = new_key
                            state = 'transport_ready'
                        elif command == 0 and state == 'transport_ready':
                            plain = decrypt(body, key)
                            if len(plain) < encrypted_length:
                                raise ValueError('Decrypted body is shorter than its header')
                            application = plain[encrypted_length:]
                            with (folder / f'{number}-application.bin').open('ab') as raw:
                                raw.write(application)
                            message_id = struct.unpack_from('>H', application, 4)[0] if len(application) >= 6 else None
                            emit('application_message', bytes=len(application), message_id=message_id)
                            if message_id == 0x002a and loaded_pushes_sent and not player_pushes_sent:
                                player_pushes_sent = True
                                for push_id,push_path in player_push_specs:
                                    push_body=push_path.read_bytes()
                                    if gameplay is not None and gameplay.inventory is not None and push_id==0x05fb:
                                        push_body=gameplay.inventory.full_body()
                                    if gameplay is not None and push_id==0x04a0:
                                        push_body=gameplay.ammo_sync()[1]
                                    if len(push_body)>65536:
                                        raise ValueError('Player candidate exceeds validated wire bound')
                                    response=struct.pack('>IHI',1,push_id,push_id)+push_body
                                    send(connection,0,body=encrypt(response,key))
                                    emit('player_ready_push_sent',message_id=push_id,
                                         body_bytes=len(push_body),
                                         body_sha256=hashlib.sha256(push_body).hexdigest(),source=str(push_path),
                                         generated_from=('offline inventory state' if gameplay is not None
                                                         and gameplay.inventory is not None
                                                         and push_id in (0x05fb,0x04a0) else 'file'))
                            if gameplay is not None and loaded_pushes_sent:
                                previous_saves=gameplay.state_save_count
                                gameplay_replies=gameplay.handle(message_id,application[26:])
                                if gameplay.world_file is not None and gameplay.state_save_count!=previous_saves:
                                    emit('gameplay_world_committed',request_id=message_id,
                                         path=str(gameplay.world_file),magazine=gameplay.magazine,
                                         reserve=gameplay.reserve,ground_stacks=len(gameplay.ground_loot.stacks))
                                for response_id, response_body in gameplay_replies:
                                    response = struct.pack('>IHI',1,response_id,response_id)+response_body
                                    send(connection,0,body=encrypt(response,key))
                                    emit('gameplay_response_sent', request_id=message_id,
                                         message_id=response_id, body_bytes=len(response_body),
                                         magazine=gameplay.magazine, reserve=gameplay.reserve,
                                         seated=gameplay.seated,deployment_phase=gameplay.deployment_phase,
                                         ground_stacks=len(gameplay.ground_loot.stacks) if gameplay.ground_loot else None,
                                         vehicle_position=gameplay.vehicle_position)
                                for response_id,response_body in gameplay.tick():
                                    response=struct.pack('>IHI',1,response_id,response_id)+response_body
                                    send(connection,0,body=encrypt(response,key))
                                    emit('gameplay_timer_response_sent',message_id=response_id,
                                         body_bytes=len(response_body),seated=gameplay.seated,
                                         diagnostic=('inventory self-test' if response_id in (0x3e82,0x3e81,0x4a0)
                                                     else 'aircraft route update' if response_id==0x6563 else 'automatic exit'),
                                         vehicle_position=gameplay.vehicle_position,
                                         inventory_stage=gameplay.inventory_test_stage,
                                         deployment_phase=gameplay.deployment_phase)
                                try:
                                    if gameplay.save_state():
                                        emit('gameplay_state_saved',path=str(gameplay.world_file or gameplay.state_file),
                                             magazine=gameplay.magazine,reserve=gameplay.reserve)
                                except OSError as error:
                                    emit('gameplay_state_save_error',error=str(error))
                            # The original client reports lobby load and later map
                            # load separately. Its environment manager may reset
                            # between them, so initialize the clock on each load.
                            if message_id == 0x0DCD and args.environment_hour is not None:
                                clock_id, clock_body = environment_clock(args.environment_hour)
                                response = struct.pack('>IHI', 1, clock_id, clock_id) + clock_body
                                send(connection, 0, body=encrypt(response, key))
                                emit('environment_clock_sent', message_id=clock_id,
                                     hour=args.environment_hour,
                                     timestamp=struct.unpack_from('>I', clock_body, 4)[0])
                            if message_id == 0x0DCD and not loaded_pushes_sent:
                                loaded_pushes_sent = True
                                for push_id, push_path in loaded_push_specs:
                                    push_body = push_path.read_bytes()
                                    if len(push_body) > 65536:
                                        raise ValueError('Scene candidate exceeds the validated wire bound')
                                    response = struct.pack('>IHI', 1, push_id, push_id) + push_body
                                    send(connection, 0, body=encrypt(response, key))
                                    if gameplay is not None:
                                        gameplay.observe_spawn(push_id,push_body)
                                    emit('scene_loaded_push_sent', message_id=push_id,
                                         body_bytes=len(push_body),
                                         body_sha256=hashlib.sha256(push_body).hexdigest(),
                                         source=str(push_path))
                            if enter_body is not None and message_id == 0x0320:
                                response = struct.pack('>IHI', 1, 0x032B, 0x032B) + enter_body
                                send(connection, 0, body=encrypt(response, key))
                                emit('enter_body_response_sent', body_bytes=len(enter_body),
                                     body_sha256=hashlib.sha256(enter_body).hexdigest(),
                                     source=str(args.enter_body_file))
                            if team_body is not None and message_id == 0x702F:
                                response = struct.pack('>IHI', 1, 0x7030, 0x7030) + team_body
                                send(connection, 0, body=encrypt(response, key))
                                emit('team_body_response_sent', body_bytes=len(team_body),
                                     body_sha256=hashlib.sha256(team_body).hexdigest(),
                                     source=str(args.team_body_file))
                                for push_id, push_path in push_specs:
                                    push_body = push_path.read_bytes()
                                    response = struct.pack('>IHI', 1, push_id, push_id) + push_body
                                    send(connection, 0, body=encrypt(response, key))
                                    emit('team_chain_push_sent', message_id=push_id,
                                         body_bytes=len(push_body),
                                         body_sha256=hashlib.sha256(push_body).hexdigest(),
                                         source=str(push_path))
                                    time.sleep(args.push_delay)
                            if room_start_body is not None and message_id == 0x6EFB:
                                # 0x6EFC is an error report: even code 0 opens an
                                # error dialog. Successful start uses 0x6F02.
                                room_start_body = args.room_start_file.read_bytes()
                                response = struct.pack('>IHI', 1, 0x6F02, 0x6F02) + room_start_body
                                send(connection, 0, body=encrypt(response, key))
                                emit('room_start_requested_push_sent', body_bytes=len(room_start_body),
                                     body_sha256=hashlib.sha256(room_start_body).hexdigest(),
                                     source=str(args.room_start_file))
                            if ready_body is not None and message_id == 0x7037:
                                ready_body = args.ready_body_file.read_bytes()
                                response = struct.pack('>IHI', 1, 0x7038, 0x7038) + ready_body
                                send(connection, 0, body=encrypt(response, key))
                                emit('ready_body_response_sent', body_bytes=len(ready_body),
                                     body_sha256=hashlib.sha256(ready_body).hexdigest(),
                                     source=str(args.ready_body_file))
                                if team_sync_body is not None:
                                    team_sync_body = args.team_sync_file.read_bytes()
                                    response = struct.pack('>IHI', 1, 0x7025, 0x7025) + team_sync_body
                                    send(connection, 0, body=encrypt(response, key))
                                    emit('team_sync_push_sent', body_bytes=len(team_sync_body),
                                         body_sha256=hashlib.sha256(team_sync_body).hexdigest(),
                                         source=str(args.team_sync_file))
                            if match_body is not None and message_id == 0x6E29:
                                match_body = args.match_body_file.read_bytes()
                                response = struct.pack('>IHI', 1, 0x6E2A, 0x6E2A) + match_body
                                send(connection, 0, body=encrypt(response, key))
                                emit('match_body_response_sent', body_bytes=len(match_body),
                                     body_sha256=hashlib.sha256(match_body).hexdigest(),
                                     source=str(args.match_body_file))
                                if match_sync_body is not None:
                                    match_sync_body = args.match_sync_file.read_bytes()
                                    response = struct.pack('>IHI', 1, 0x6E2D, 0x6E2D) + match_sync_body
                                    send(connection, 0, body=encrypt(response, key))
                                    emit('match_sync_push_sent', body_bytes=len(match_sync_body),
                                         body_sha256=hashlib.sha256(match_sync_body).hexdigest(),
                                         source=str(args.match_sync_file))
                                if room_start_body is not None:
                                    room_start_body = args.room_start_file.read_bytes()
                                    response = struct.pack('>IHI', 1, 0x6F02, 0x6F02) + room_start_body
                                    send(connection, 0, body=encrypt(response, key))
                                    emit('room_start_push_sent', body_bytes=len(room_start_body),
                                         body_sha256=hashlib.sha256(room_start_body).hexdigest(),
                                         source=str(args.room_start_file))
                            if message_id == 0x02F9:
                                submission = save_submission(application, root / 'recovery' / 'profiles')
                                emit('thai_character_submission_saved', request_sha256=submission['request_sha256'],
                                     appearance_bytes=submission['appearance_bytes'])
                                if args.create_sweep_dir:
                                    files = sorted(Path(args.create_sweep_dir).glob('*.bin'))
                                    emit('create_sweep_begin', files=[p.name for p in files],
                                         delay=args.create_sweep_delay)
                                    sent = 0
                                    for index, path in enumerate(files):
                                        sweep_body = path.read_bytes()
                                        packet = (struct.pack('>IHI', 1, 0x0303, 0x0303)
                                                  + sweep_body)
                                        try:
                                            send(connection, 0, body=encrypt(packet, key))
                                        except OSError as error:
                                            emit('create_sweep_aborted', index=index,
                                                 error=str(error))
                                            break
                                        sent += 1
                                        emit('experimental_create_response_sent',
                                             message_id=0x0303, actor_uid=1, mode='sweep',
                                             index=index, source=path.name,
                                             body_bytes=len(sweep_body),
                                             body_sha256=hashlib.sha256(sweep_body).hexdigest())
                                        time.sleep(args.create_sweep_delay)
                                    emit('create_sweep_end', sent=sent)
                                elif args.probe_create_response:
                                    if args.create_body_file:
                                        body = args.create_body_file.read_bytes()
                                        mode = 'body-file'
                                    elif create_body is not None:
                                        body = create_body
                                        mode = f'zeros:{args.create_zeros}'
                                    else:
                                        request_body = application[26:]
                                        mode = args.create_response_mode
                                        if args.create_mode_file:
                                            try:
                                                override = args.create_mode_file.read_text(encoding='utf-8').strip()
                                            except OSError:
                                                override = ''
                                            if override:
                                                mode = override
                                        if mode.startswith('file:'):
                                            body = Path(mode[5:].strip()).read_bytes()
                                        elif mode == 'echo':
                                            body = request_body
                                        elif mode == 'zeros64':
                                            body = bytes(64)
                                        elif mode == 'zeros64-uid4':
                                            body = struct.pack('>IQ', 0, 1) + bytes(52)
                                        elif mode == 'zeros64-uid12':
                                            body = (struct.pack('>I', 0) + bytes(8)
                                                    + struct.pack('>Q', 1) + bytes(44))
                                        elif mode == 'ret-echo':
                                            body = struct.pack('>I', 0) + request_body
                                        elif mode == 'ret-uid-echo':
                                            body = struct.pack('>IQ', 0, 1) + request_body
                                        elif mode == 'ret1-echo':
                                            body = struct.pack('>I', 1) + request_body
                                        elif mode == 'ret1-uid':
                                            body = struct.pack('>IQ', 1, 1)
                                        elif mode == 'ret1-uid-echo':
                                            body = struct.pack('>IQ', 1, 1) + request_body
                                        else:
                                            body = struct.pack('>I', 0) + bytes(2048)
                                    packet = struct.pack('>IHI', 1, 0x0303, 0x0303) + body
                                    (folder / 'create-response-body.bin').write_bytes(body)
                                    send(connection, 0, body=encrypt(packet, key))
                                    emit('experimental_create_response_sent', message_id=0x0303, actor_uid=1,
                                         mode=mode,
                                         body_bytes=len(body),
                                         body_sha256=hashlib.sha256(body).hexdigest())
                            if world_body is not None and message_id == 0x02E4:
                                packet = struct.pack('>IHI', 1, 0x02EF, 0x02EF) + world_body
                                send(connection, 0, body=encrypt(packet, key))
                                emit('world_body_response_sent', body_bytes=len(world_body),
                                     body_sha256=hashlib.sha256(world_body).hexdigest(),
                                     source=str(args.world_body_file))
                            elif roster is not None and message_id == 0x02E4:
                                send(connection, 0, body=encrypt(roster, key))
                                emit('roster_capture_response_sent', bytes=len(roster),
                                     source=str(args.roster_file))
                            if (args.probe_auth_response and message_id == 0x02F0) or (
                                    args.probe_world_response and message_id == 0x02E4
                                    and world_body is None and roster is None):
                                if len(application) < 26 or application[4:6] != application[24:26]:
                                    raise ValueError('Unexpected user authentication envelope')
                                # A bounded schema-discovery experiment, NOT a verified
                                # successful login response. Keep disabled by default.
                                response_id = 0x02F1 if message_id == 0x02F0 else 0x02EF
                                if args.compact_responses:
                                    response = struct.pack('>IHI', 1, response_id, response_id) + bytes(64)
                                else:
                                    response = bytearray(application[:26] + bytes(64))
                                    struct.pack_into('>I', response, 0, len(response))
                                    struct.pack_into('>H', response, 4, response_id)
                                    struct.pack_into('>H', response, 24, response_id)
                                send(connection, 0, body=encrypt(bytes(response), key))
                                emit('default_field_response_probe_sent', message_id=response_id)
                            # Game-specific application replies are not implemented yet.
                        elif command == 13:
                            emit('client_closed')
                            break
                        else:
                            emit('unhandled_command', command=command)
                except (EOFError, OSError, ValueError) as error:
                    emit('connection_ended', state=state, reason=str(error))
                if args.single_session and state=='transport_ready':
                    break
        emit('finished', connections=number)
    log.close()


if __name__ == '__main__':
    main()
