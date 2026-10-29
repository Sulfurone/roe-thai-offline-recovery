"""Experimental loopback TPDU handshake, not a playable game server."""
import argparse
from contextlib import ExitStack
import datetime
import hashlib
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import time
import webbrowser
from tpdu import auth_info, decrypt, encrypt, frame, read_frame
from thai_profile import save_submission
from offline_environment import (EnvironmentSchedule, NATIVE_WEATHER_IDS,
                                 WeatherSchedule, environment_clock, synchronize_lobby_clock)
from offline_gameplay import OfflineGameplay,ACTOR_UID,JEEP_UID,TYPED_ACTOR_UID,TYPED_VEHICLE_UID
from offline_control import ControlHub, ControlServer
from control_actions import ControlSession
from ingame_bridge import IngameMailbox, IngameInstallation
from ingame_overlay import OverlayProcess
from offline_motion import actor_motion, aircraft_spawn_heading
from offline_population import WorldPopulation
from offline_bots import BotRoster
from offline_hit_reports import character_hit
from offline_combat import BotCombat
from offline_bot_ai import BotAI
from offline_blast import BlastCombat
from offline_visibility import StaticVisibility
from offline_posture import posture_speed_delta,CROUCH_CM_PER_SECOND,PRONE_CM_PER_SECOND
from self_position import PositionInstallation,recover_previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-position-observer',action='store_true',
                        help='Opt-in reversible self-read coordinate DLL; requires a local build and closed game')
    parser.add_argument('--seconds', type=int, default=75)
    parser.add_argument('--port', type=int, default=8001,
                        help='Loopback port for this experiment (old clients use 8001)')
    parser.add_argument('--launch', action='store_true')
    parser.add_argument('--single-session',action='store_true',
                        help='Exit after the authenticated client disconnects, releasing the local port')
    parser.add_argument('--control-ui-port', type=int, metavar='PORT',
                        help='Enable the local weather/weapon/vehicle control panel (e.g. 8765)')
    parser.add_argument('--ingame-control', action='store_true',
                        help='Prepare the experimental native Lua menu and a local file mailbox')
    parser.add_argument('--ingame-overlay', action='store_true',
                        help='Show the native Windows F6 menu over the game window; no HTTP or client files')
    parser.add_argument('--ingame-menu-collapsed', action='store_true',
                        help='Start the overlay compact, keeping keyboard focus in the aircraft/game')
    parser.add_argument('--aircraft-align-heading', action='store_true',
                        help='Align the config-4 spawn quaternion with the horizontal route')
    parser.add_argument('--gameplay-motion-ack', action='store_true',
                        help='Reply to complete Thai movement DTOs with the native self receipt word')
    parser.add_argument('--control-open', action='store_true', help='Open the local control panel in a browser')
    parser.add_argument('--control-vehicle-template', type=Path,
                        help='Locally generated original-codec-validated config 101 Jeep spawn body')
    parser.add_argument('--environment-hour', type=int, choices=range(24), metavar='0..23',
                        help='Initialize the native day/weather clock (12 is noon)')
    parser.add_argument('--world-time-tail-bytes', type=int, choices=(10, 18),
                        help='Stamp the original-codec-verified 0x02EF server-time tail (10 canonical, 18 historical padded)')
    parser.add_argument('--environment-trigger',choices=('player-ready','load'),default='player-ready',
                        help='Safe default waits for the first valid player position; load preserves the old A/B probe')
    parser.add_argument('--environment-ready-delay',type=float,default=1.0,metavar='SECONDS',
                        help='Delay after the first valid player position before the one-shot clock (0..30)')
    parser.add_argument('--environment-weather',type=int,choices=sorted(NATIVE_WEATHER_IDS),
                        metavar='WEATHER_ID',
                        help='Select a native Thai weather preset after the player is ready (2 is clear)')
    parser.add_argument('--environment-weather-transition',type=int,default=30,metavar='SECONDS',
                        help='Native renderer transition duration for --environment-weather (0..600)')
    parser.add_argument('--environment-weather-ready-delay',type=float,default=2.0,metavar='SECONDS',
                        help='Delay after the first valid player position before weather delivery (0..30)')
    parser.add_argument('--environment-once', action='store_true',
                        help='Legacy load-trigger probe: send only on the second load notification')
    parser.add_argument('--gameplay-prototype', action='store_true',
                        help='Opt in to unverified Thai ammo and vehicle interaction handlers')
    parser.add_argument('--gameplay-doors', action='store_true',
                        help='Opt in to experimental Thai reversible-object state replies')
    parser.add_argument('--world-populate', action='store_true',
                        help='Generate finite random ground weapons/ammo and Jeeps as the player explores')
    parser.add_argument('--world-terrain', type=Path,
                        help='Own-client Thai collision REPX used for random ground placement')
    parser.add_argument('--world-client-ground', action='store_true',
                        help='Use small ground patches from actual walking reports instead of an unverified heightfield')
    parser.add_argument('--world-client-map', type=Path,
                        help='Privately extracted Thai QSHM, road mask and scene catalogues for indoor/roadside placement')
    parser.add_argument('--world-seed', type=int,
                        help='Population seed, 0..4294967295; default chooses a fresh seed per run')
    parser.add_argument('--world-loot-clusters',type=int,default=16,
                        help='Weapon/ammo pairs attempted per exploration region, 1..16 (default 8)')
    parser.add_argument('--world-vehicle-clusters',type=int,default=3,
                        help='Roadside cars attempted per exploration region, 1..4 (default 3)')
    parser.add_argument('--world-extra-items',action='store_true',
                        help='Experimental residential bags, throwables, attachments and mixed land vehicles')
    parser.add_argument('--control-client-boarding',action='store_true',
                        help='Single-player: trust local selection of loaded generated vehicles for boarding')
    parser.add_argument('--world-bots', type=int, default=0,
                        help='Experimental local peer count, 0..4; passive unless --world-bot-ai')
    parser.add_argument('--world-bot-profile', type=Path,
                        help='Locally prepared original-codec-validated basic peer profile')
    parser.add_argument('--gameplay-arsenal',action='store_true',
                        help='Seed recovered firearms/ammunition in a fresh ground-loot world')
    parser.add_argument('--gameplay-scatter-loot',action='store_true',
                        help='Spawn a weapon/ammo cluster every 600m of reported ground travel')
    parser.add_argument('--gameplay-auto-seat', action='store_true',
                        help='Diagnostic: board the test Jeep after its first physics report')
    parser.add_argument('--gameplay-auto-board-delay',type=float,default=0,
                        help='Wait this many seconds after vehicle spawn before automatic boarding (0..30)')
    parser.add_argument('--gameplay-vehicle-config',type=int,choices=[3,4,101],default=101,
                        help='Original Thai test vehicle: glider=3, helicopter=4, Jeep=101')
    parser.add_argument('--gameplay-typed-uids',action='store_true',
                        help='Candidate entity UID type bits; requires matching typed fixture set')
    parser.add_argument('--gameplay-vitals',action='store_true',help='Initialize original HP once and handle timed medicine-use candidates')
    parser.add_argument('--world-bot-combat',action='store_true',
                        help='Experimental consumed-shot/collision damage against local peers; no combat AI')
    parser.add_argument('--world-bot-ai',action='store_true',
                        help='Experimental local perception/chase/fire; requires explicit combat and static bounds')
    parser.add_argument('--world-throwable-combat',action='store_true',
                        help='Experimental native-range frag blast damage with terrain/static screening')
    parser.add_argument('--world-bot-occlusion',type=Path,
                        help='Thai static scene XML; defaults to the selected client map scene')
    parser.add_argument('--gameplay-throwables',action='store_true',help='Acknowledge native throws, consume one item and complete original effects')
    parser.add_argument('--gameplay-posture-speeds',action='store_true',
                        help='Sparse local crouch/prone tuning after player readiness; standing stays unchanged')
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
    parser.add_argument('--push-after-map-load', action='append', default=[], metavar='MSGID:FILE',
                        help='Once after the second 0x0DCD (map load, before the first actor MOVE_1), push these bodies')
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
    if args.ingame_menu_collapsed and not args.ingame_overlay:
        parser.error('--ingame-menu-collapsed requires --ingame-overlay')
    if args.aircraft_align_heading and args.gameplay_aircraft_route_end is None:
        parser.error('--aircraft-align-heading requires a route endpoint')
    if args.world_time_tail_bytes is not None and args.world_body_file is None:
        parser.error('--world-time-tail-bytes requires --world-body-file')
    if args.environment_hour is not None and args.world_body_file is not None and args.world_time_tail_bytes is None:
        parser.error('Daytime needs a matching lobby epoch: verify and specify --world-time-tail-bytes')
    if args.world_time_tail_bytes is not None:
        try:
            synchronize_lobby_clock(args.world_body_file.read_bytes(), args.world_time_tail_bytes, 0)
        except (OSError, ValueError) as error:
            parser.error(f'Cannot synchronize lobby clock: {error}')
    if args.control_ui_port is not None and not 0 <= args.control_ui_port <= 65535:
        parser.error('--control-ui-port must be from 0 to 65535')
    if args.ingame_control and args.ingame_overlay:
        parser.error('Choose either the Lua experiment or the Windows overlay')
    if (args.control_ui_port is not None or args.ingame_control or args.ingame_overlay) and not args.gameplay_prototype:
        parser.error('Control options require --gameplay-prototype')
    if args.control_open and args.control_ui_port is None:
        parser.error('--control-open requires --control-ui-port')
    if args.control_vehicle_template and args.control_ui_port is None and not (args.ingame_control or args.ingame_overlay):
        parser.error('Control vehicle requires a control interface')
    control_vehicle_body = None
    if args.control_vehicle_template:
        try:
            if args.control_vehicle_template.stat().st_size > 65536:
                raise ValueError('Vehicle sample exceeds wire bound')
            control_vehicle_body = args.control_vehicle_template.read_bytes()
            ControlSession(vehicle_template=control_vehicle_body)
        except (OSError, ValueError) as error:
            parser.error(f'Cannot prepare control vehicle: {error}')
    if not 0 <= args.environment_ready_delay <= 30:
        parser.error('--environment-ready-delay must be from 0 to 30 seconds')
    if not 0 <= args.environment_weather_ready_delay <= 30:
        parser.error('--environment-weather-ready-delay must be from 0 to 30 seconds')
    if not 0 <= args.environment_weather_transition <= 600:
        parser.error('--environment-weather-transition must be from 0 to 600 seconds')
    if args.environment_once and args.environment_trigger != 'load':
        parser.error('--environment-once is only valid with --environment-trigger load')
    opening_glider_body=None
    population_surface=None
    bot_profile=None
    if args.world_bots:
        if not args.world_populate or args.world_bot_profile is None:
            parser.error('Experimental peers require population and a local basic profile')
        try:
            bot_profile=args.world_bot_profile.read_bytes()
            BotRoster(bot_profile,args.world_bots)
        except (OSError,ValueError,TypeError) as error:
            parser.error(f'Cannot prepare experimental peers: {error}')
    if args.gameplay_doors and not args.gameplay_prototype:
        parser.error('Door replies require --gameplay-prototype')
    if args.world_populate:
        if not (args.gameplay_prototype and args.gameplay_ground_loot and (args.world_terrain or args.world_client_ground or args.world_client_map)
                and args.control_vehicle_template) or args.gameplay_world_file:
            parser.error('Population requires prototype, ground loot, terrain, Jeep template and a nonpersistent world')
        if args.world_seed is None:
            args.world_seed=int.from_bytes(os.urandom(4),'big')
        if not 0 <= args.world_seed < 2**32:
            parser.error('World seed must be 0..4294967295')
        if not 1<=args.world_loot_clusters<=16:
            parser.error('Loot density must be 1..16 pairs per region')
        if not 1<=args.world_vehicle_clusters<=4:
            parser.error('Vehicle density must be 1..4 per region')
        if sum(bool(value) for value in (args.world_client_ground,args.world_terrain,args.world_client_map)) != 1:
            parser.error('Choose exactly one population ground source')
        if args.world_client_map:
            from offline_client_map import ThaiClientMap
            try:
                population_surface=ThaiClientMap.from_folder(args.world_client_map)
            except (OSError,ValueError,TypeError) as error:
                parser.error(f'Cannot prepare client map placement: {error}')
        elif args.world_client_ground:
            if args.world_terrain is not None:
                parser.error('Choose either client walking survey or verified terrain, not both')
            from offline_ground_survey import GroundSurvey
            population_surface=GroundSurvey()
        else:
            from offline_terrain import TerrainSurface
            try:
                population_surface=TerrainSurface.from_repx(args.world_terrain)
            except (OSError,ValueError,TypeError) as error:
                parser.error(f'Cannot read population terrain: {error}')
    elif args.world_terrain is not None or args.world_client_ground or args.world_client_map:
        parser.error('World terrain requires --world-populate')
    bot_visibility=None
    if args.world_bot_ai or args.world_throwable_combat:
        if args.world_bot_ai and not args.world_bot_combat:
            parser.error('--world-bot-ai requires --world-bot-combat')
        if args.world_throwable_combat and not (args.gameplay_throwables and args.gameplay_vitals):
            parser.error('--world-throwable-combat requires --gameplay-throwables and --gameplay-vitals')
        occlusion=args.world_bot_occlusion or (args.world_client_map/'RIGIDSTATICINPXSCENE.XML' if args.world_client_map else None)
        if occlusion is None or population_surface is None:
            parser.error('Local combat needs a Thai static scene and population terrain')
        try:
            bot_visibility=StaticVisibility.from_scene(population_surface,occlusion)
        except (OSError,ValueError,TypeError) as error:
            parser.error(f'Cannot prepare local combat visibility: {error}')
    elif args.world_bot_occlusion is not None:
        parser.error('--world-bot-occlusion requires --world-bot-ai or --world-throwable-combat')
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
    if args.gameplay_vitals and not args.gameplay_prototype:
        parser.error('--gameplay-vitals requires --gameplay-prototype')
    if args.world_bot_combat and not (args.world_bots and args.gameplay_inventory and args.gameplay_vitals):
        parser.error('--world-bot-combat requires experimental peers, inventory and vitals')
    if args.gameplay_throwables and not (args.gameplay_prototype and args.gameplay_inventory):
        parser.error('--gameplay-throwables requires --gameplay-prototype and --gameplay-inventory')
    if args.gameplay_posture_speeds and not args.gameplay_prototype:
        parser.error('--gameplay-posture-speeds requires --gameplay-prototype')
    if args.self_position_observer and not args.gameplay_prototype:
        parser.error('--self-position-observer requires --gameplay-prototype')
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
    map_push_specs = []
    for spec in args.push_after_map_load:
        message, separator, path = spec.partition(':')
        if not separator or not path:
            parser.error(f'--push-after-map-load expects MSGID:FILE: {spec!r}')
        try:
            message_id = int(message, 16)
        except ValueError:
            parser.error(f'invalid --push-after-map-load message id: {spec!r}')
        map_push_specs.append((message_id, Path(path)))
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
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
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
    with socket.socket() as listener, ExitStack() as resources:
        listener.bind(('127.0.0.1', args.port))
        listener.listen(4)
        listener.settimeout(1)
        emit('listening', address=f'127.0.0.1:{args.port}',
             key_status='Unverified test session key')
        observer=None
        if args.self_position_observer:
            recover_previous(root/'32838',root/'recovery/private/self-position')
            observer=resources.enter_context(PositionInstallation(root/'32838',
                root/'recovery/private/self-position'/('session-'+stamp)))
            emit('self_position_observer_prepared',output=str(observer.output),
                 scope='Local self-memory reads only; original DataEngine exports forwarded')
        control = ControlHub() if args.control_ui_port is not None or args.ingame_control or args.ingame_overlay else None
        mailbox = None
        if args.ingame_control or args.ingame_overlay:
            mailbox = IngameMailbox(root / 'recovery/private/ingame-control')
            mailbox.publish(control.snapshot())
        if args.ingame_overlay:
            resources.enter_context(OverlayProcess(mailbox.directory, start_collapsed=args.ingame_menu_collapsed))
            emit('ingame_overlay_started', directory=str(mailbox.directory), hotkey='F6',
                 scope='Separate Windows overlay attached to the game window; no engine injection')
        if args.ingame_control:
            resources.enter_context(IngameInstallation(root / '32838', mailbox))
            emit('ingame_menu_prepared', directory=str(mailbox.directory),
                 fallback_command='/lua assert(loadstring(assert(io.open("ROE_OfflineMenu.lua")):read("*a")))()',
                 scope='Loader candidate prepared; native loading/visibility require live evidence')
        if args.control_ui_port is not None:
            panel = resources.enter_context(ControlServer(control, args.control_ui_port))
            emit('control_panel_listening', url=panel.url)
            if args.control_open:
                webbrowser.open(panel.url)
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
                map_load_count = 0
                map_pushes_sent = False
                player_pushes_sent = False
                environment = (EnvironmentSchedule(args.environment_hour,args.environment_ready_delay)
                               if args.environment_hour is not None
                               and args.environment_trigger == 'player-ready' else None)
                weather = (WeatherSchedule(args.environment_weather,
                                           args.environment_weather_transition,
                                           args.environment_weather_ready_delay)
                           if args.environment_weather is not None else None)
                gameplay = OfflineGameplay(vitals_enabled=args.gameplay_vitals,throwables_enabled=args.gameplay_throwables,auto_board=args.gameplay_auto_seat,
                    auto_board_delay=args.gameplay_auto_board_delay,
                    magazine=args.gameplay_starting_magazine,
                    inventory_enabled=args.gameplay_inventory,state_file=args.gameplay_state_file,
                    inventory_selftest=args.gameplay_inventory_selftest,
                    ground_loot_enabled=args.gameplay_ground_loot,
                    arsenal_enabled=args.gameplay_arsenal,
                    scatter_loot=args.gameplay_scatter_loot,
                    door_interactions=args.gameplay_doors,
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
                control_session = ControlSession(gameplay, control_vehicle_body,
                    client_boarding=args.control_client_boarding) if control or args.world_populate else None
                bots=BotRoster(bot_profile,args.world_bots) if bot_profile is not None else None
                combat=BotCombat(gameplay,bots) if args.world_bot_combat else None
                population = WorldPopulation(control_session,population_surface,args.world_seed,bots=bots,
                    clusters=args.world_loot_clusters,vehicle_clusters=args.world_vehicle_clusters,
                    extra_items=args.world_extra_items) if args.world_populate else None
                ai=BotAI(gameplay,bots,population,bot_visibility) if args.world_bot_ai else None
                blast=BlastCombat(gameplay,bots,bot_visibility) if args.world_throwable_combat else None
                if population is not None:
                    emit('world_population_ready',seed=args.world_seed,door_replies=args.gameplay_doors,
                         experimental_peers=args.world_bots,scope='Synthetic finite scenario, not original AI/collision')
                control_ready_after = None
                posture_delta_sent=False
                if control is not None:
                    control.disconnect()
                if gameplay is not None and gameplay.inventory is not None:
                    emit('gameplay_inventory_ready',magazine=gameplay.magazine,reserve=gameplay.reserve,
                         weapon_slot=gameplay.inventory.weapon_slot(),entries=len(gameplay.inventory.items),
                         restored=bool((args.gameplay_world_file and args.gameplay_world_file.exists())
                                       or (args.gameplay_state_file and args.gameplay_state_file.exists())),
                         world_profile=str(args.gameplay_world_file) if args.gameplay_world_file else None,
                         ground_stacks=len(gameplay.ground_loot.stacks) if gameplay.ground_loot else None)
                def send_gameplay_timers():
                    for response_id,response_body in gameplay.tick():
                        response=struct.pack('>IHI',1,response_id,response_id)+response_body
                        send(connection,0,body=encrypt(response,key))
                        emit('gameplay_timer_response_sent',message_id=response_id,
                             body_bytes=len(response_body),seated=gameplay.seated,
                             diagnostic=('initial life state' if response_id==0x1069
                                         else 'inventory self-test' if response_id in (0x3e82,0x3e81,0x4a0)
                                         else 'aircraft route update' if response_id==0x6563
                                         else 'automatic boarding' if response_id==0x6542
                                         else 'jump enabled' if response_id==0x6565
                                         else 'glider spawn' if response_id==0x654b else 'automatic exit'),
                             vehicle_position=gameplay.vehicle_position,
                             inventory_stage=gameplay.inventory_test_stage,
                             deployment_phase=gameplay.deployment_phase)
                def send_environment_timers():
                    if environment is None:
                        packet=None
                    else:
                        packet=environment.take()
                    if packet is not None:
                        clock_id,clock_body=packet
                        response=struct.pack('>IHI',1,clock_id,clock_id)+clock_body
                        send(connection,0,body=encrypt(response,key))
                        emit('environment_clock_sent',message_id=clock_id,
                             hour=args.environment_hour,trigger='player-ready',
                             ready_delay=args.environment_ready_delay,
                             position_reports=environment.position_reports,
                             timestamp=struct.unpack_from('>I',clock_body,4)[0])
                    if weather is None:
                        weather_packet=None
                    else:
                        weather_packet=weather.take()
                    if weather_packet is not None:
                        weather_id,weather_body=weather_packet
                        response=struct.pack('>IHI',1,weather_id,weather_id)+weather_body
                        send(connection,0,body=encrypt(response,key))
                        _,preset,transition,mode=struct.unpack('>4I',weather_body)
                        emit('environment_weather_sent',message_id=weather_id,
                             weather_id=preset,transition_seconds=transition,mode=mode,
                             trigger='player-ready',
                             ready_delay=args.environment_weather_ready_delay,
                             position_reports=weather.position_reports)
                def send_control_commands():
                    if control is None:
                        return
                    snapshot = control_session.snapshot()
                    snapshot['connected'] = state == 'transport_ready'
                    snapshot['ready'] = bool(snapshot['connected'] and snapshot['ready']
                                             and control_ready_after is not None
                                             and time.monotonic() >= control_ready_after)
                    control.update(**snapshot)
                    if mailbox is not None:
                        mailbox.poll(control)
                    if not snapshot['ready']:
                        if mailbox is not None:
                            mailbox.publish(control.snapshot())
                        return
                    for _ in range(4):
                        item = control.take()
                        if item is None:
                            break
                        try:
                            replies, description = control_session.execute(item)
                            for response_id, response_body in replies:
                                response = struct.pack('>IHI', 1, response_id, response_id) + response_body
                                send(connection, 0, body=encrypt(response, key))
                            if item['action'] == 'weather' and weather is not None:
                                weather.sent = True
                            control.finish(item['id'], 'sent', description)
                            emit('control_command_sent', action=item['action'], replies=len(replies),
                                 actor_position=gameplay.player_position)
                        except (ValueError, OSError) as error:
                            control.finish(item['id'], 'failed', str(error))
                            emit('control_command_failed', action=item['action'], reason=str(error))
                    control.update(**control_session.snapshot())
                    if mailbox is not None:
                        mailbox.publish(control.snapshot())
                try:
                    while time.monotonic() < deadline:
                        if observer is not None and gameplay is not None and loaded_pushes_sent:
                            gameplay.require_self_position_for_drop=True
                            current_position=observer.feed.take()
                            if current_position is not None and gameplay.accept_self_position(current_position):
                                if time.monotonic()-getattr(observer,'last_report',0)>=1:
                                    emit('self_position_updated',position=current_position,
                                         sequence=observer.feed.sequence,client_pid=observer.feed.pid)
                                    observer.last_report=time.monotonic()
                        send_control_commands()
                        if population is not None and state == 'transport_ready' and loaded_pushes_sent:
                            population_replies=population.tick()
                            for response_id,response_body in population_replies:
                                response=struct.pack('>IHI',1,response_id,response_id)+response_body
                                send(connection,0,body=encrypt(response,key))
                            if population_replies:
                                emit('world_population_sent',messages=len(population_replies),
                                     actor_position=gameplay.player_position,cells=len(population.visited),
                                     ground_items=len(gameplay.ground_loot.stacks),vehicles=population.auto_vehicles,
                                     peers=len(bots.actors) if bots is not None else 0)
                            if ai is not None:
                                for response_id,response_body in ai.tick():
                                    response=struct.pack('>IHI',1,response_id,response_id)+response_body
                                    send(connection,0,body=encrypt(response,key))
                                    emit('bot_ai_response_sent',message_id=response_id,body_bytes=len(response_body))
                                for event in ai.events:
                                    emit('bot_ai',**event)
                        # Advance timers when the client is quiet. Socket reads
                        # still use the original framed reader; a partial frame
                        # remains subject to its existing connection timeout.
                        gameplay_timers=(gameplay is not None and loaded_pushes_sent
                                         and state=='transport_ready')
                        if (gameplay_timers and args.gameplay_posture_speeds
                                and gameplay.actor_ready and not posture_delta_sent):
                            payload=posture_speed_delta()
                            response=struct.pack('>IHI',1,0x516,0x516)+payload
                            send(connection,0,body=encrypt(response,key))
                            posture_delta_sent=True
                            emit('posture_speed_delta_sent',crouch_cm_per_second=CROUCH_CM_PER_SECOND,
                                 prone_cm_per_second=PRONE_CM_PER_SECOND,records=9,
                                 scope='Offline posture calibration; not recovered server defaults')
                        environment_schedules=tuple(schedule for schedule in (environment,weather)
                                                    if schedule is not None
                                                    and schedule.armed_at is not None
                                                    and not schedule.sent)
                        environment_timer=bool(environment_schedules and state=='transport_ready')
                        if gameplay_timers or environment_timer or control is not None or population is not None:
                            wait=min(.25,max(0,deadline-time.monotonic()))
                            if environment_timer:
                                wait=min(wait,max(0,min(schedule.armed_at
                                                      for schedule in environment_schedules)
                                                   - time.monotonic()))
                            readable,_,_=select.select([connection],[],[],wait)
                            if not readable:
                                if gameplay_timers:
                                    send_gameplay_timers()
                                send_environment_timers()
                                continue
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
                            if gameplay is not None and message_id==0x11e9 and combat is None:
                                hit=character_hit(application[26:])
                                if hit is None:
                                    emit('character_hit_report_rejected',body_bytes=len(application[26:]))
                                else:
                                    emit('character_hit_report',sequence=hit.sequence,
                                         target_uid=hit.target_uid,impact=hit.impact,
                                         ray_origin=hit.ray_origin,part=hit.part,
                                         damage_applied=False)
                            if args.gameplay_motion_ack and gameplay is not None and loaded_pushes_sent and message_id == 0x002a:
                                motion = actor_motion(application[26:])
                                if motion is not None and motion[1] is not None:
                                    position, sequence = motion
                                    response = struct.pack('>IHI', 1, 0x0036, 0x0036) + struct.pack('>I', sequence)
                                    send(connection, 0, body=encrypt(response, key))
                                    emit('actor_motion_ack_sent', sequence=sequence, position=position)
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
                                    if gameplay is not None:
                                        gameplay.observe_spawn(push_id,push_body)
                                    emit('player_ready_push_sent',message_id=push_id,
                                         body_bytes=len(push_body),
                                         body_sha256=hashlib.sha256(push_body).hexdigest(),source=str(push_path),
                                         generated_from=('offline inventory state' if gameplay is not None
                                                         and gameplay.inventory is not None
                                                         and push_id in (0x05fb,0x04a0) else 'file'))
                            if gameplay is not None and loaded_pushes_sent:
                                previous_saves=gameplay.state_save_count
                                previous_magazine=gameplay.magazine
                                bot_replies=bots.handle(message_id,application[26:]) if bots is not None else None
                                if ai is not None and bot_replies is not None:
                                    for reply_id,reply_body in list(bot_replies):
                                        if reply_id==0xbe7:
                                            uid=struct.unpack_from('>Q',reply_body,8)[0]
                                            equipped=ai.equipment(uid)
                                            if equipped is not None and bots.vitals[uid].current:
                                                bot_replies.append(equipped)
                                control_replies=bot_replies
                                if control_replies is None and control_session is not None:
                                    control_replies=control_session.handle(message_id,application[26:])
                                    if control_session.last_board_event is not None:
                                        emit('vehicle_board_request',**control_session.last_board_event)
                                gameplay_replies=(gameplay.handle(message_id,application[26:])
                                                  if control_replies is None else control_replies)
                                if blast is not None and message_id==0x1007:
                                    gameplay_replies.extend(blast.complete(gameplay.throws.take_completion()))
                                    for event in blast.events:emit('throwable_combat',**event)
                                if message_id==0x2a and gameplay.last_medicine_cancel:
                                    emit('medicine_cancelled',source='native_movement_action',action=20)
                                if combat is not None and message_id==0x11d3:
                                    combat.record_shot(application[26:],previous_magazine)
                                if combat is not None and message_id==0x11e9:
                                    gameplay_replies.extend(combat.handle(application[26:]))
                                    if combat.last_event is not None:
                                        emit('bot_combat',**combat.last_event)
                                if (message_id==0x3b63 and gameplay.ground_loot is not None
                                        and gameplay.ground_loot.last_rejection is not None):
                                    emit('pickup_rejected',**gameplay.ground_loot.last_rejection)
                                if message_id==0x3e80 and gameplay.last_drop_event:
                                    emit('ground_drop_created' if gameplay.last_drop_event.get('accepted',True)
                                         else 'ground_drop_rejected',**gameplay.last_drop_event)
                                if (control is not None and control_ready_after is None
                                        and gameplay.actor_ready):
                                    control_ready_after = time.monotonic() + 2
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
                                if population is not None:
                                    population.observe(message_id,application[26:])
                                send_gameplay_timers()
                                try:
                                    if gameplay.save_state():
                                        emit('gameplay_state_saved',path=str(gameplay.world_file or gameplay.state_file),
                                             magazine=gameplay.magazine,reserve=gameplay.reserve)
                                except OSError as error:
                                    emit('gameplay_state_save_error',error=str(error))
                            if environment is not None and environment.observe(message_id,application[26:]):
                                emit('environment_clock_armed',hour=args.environment_hour,
                                     trigger='player-ready',ready_delay=args.environment_ready_delay,
                                     position_reports=environment.position_reports)
                            if weather is not None and weather.observe(message_id,application[26:]):
                                emit('environment_weather_armed',weather_id=args.environment_weather,
                                     transition_seconds=args.environment_weather_transition,
                                     trigger='player-ready',
                                     ready_delay=args.environment_weather_ready_delay,
                                     position_reports=weather.position_reports)
                            # Legacy A/B path only. Real-client evidence showed
                            # that even the second-DCD-only clock can stop the
                            # game loop after one MOVE_1, so normal launchers use
                            # the player-ready scheduler above.
                            if message_id == 0x0DCD:
                                map_load_count += 1
                            clock_due = (args.environment_hour is not None
                                and args.environment_trigger == 'load' and (
                                    not args.environment_once or map_load_count >= 2))
                            if message_id == 0x0DCD and clock_due:
                                clock_id, clock_body = environment_clock(args.environment_hour)
                                response = struct.pack('>IHI', 1, clock_id, clock_id) + clock_body
                                send(connection, 0, body=encrypt(response, key))
                                emit('environment_clock_sent', message_id=clock_id,
                                     hour=args.environment_hour,
                                     trigger='load',
                                     load_notification=map_load_count,
                                     timestamp=struct.unpack_from('>I', clock_body, 4)[0])
                            if message_id == 0x0DCD and map_load_count == 2 and not map_pushes_sent:
                                map_pushes_sent = True
                                for push_id, push_path in map_push_specs:
                                    push_body = push_path.read_bytes()
                                    if args.aircraft_align_heading and push_id == 0x654b:
                                        push_body = aircraft_spawn_heading(push_body, args.gameplay_aircraft_route_end)
                                    if len(push_body) > 65536:
                                        raise ValueError('Map-load candidate exceeds validated wire bound')
                                    response = struct.pack('>IHI', 1, push_id, push_id) + push_body
                                    send(connection, 0, body=encrypt(response, key))
                                    if gameplay is not None:
                                        gameplay.observe_spawn(push_id, push_body)
                                    emit('map_loaded_push_sent', message_id=push_id,
                                         body_bytes=len(push_body),
                                         body_sha256=hashlib.sha256(push_body).hexdigest(),
                                         source=str(push_path), load_notification=map_load_count)
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
                                reply_world_body = world_body
                                if args.world_time_tail_bytes is not None:
                                    reply_world_body = synchronize_lobby_clock(world_body, args.world_time_tail_bytes)
                                    emit('world_time_synchronized',
                                         timestamp=struct.unpack_from('>I', reply_world_body, len(reply_world_body) - args.world_time_tail_bytes)[0],
                                         field_offset=len(reply_world_body) - args.world_time_tail_bytes)
                                packet = struct.pack('>IHI', 1, 0x02EF, 0x02EF) + reply_world_body
                                send(connection, 0, body=encrypt(packet, key))
                                emit('world_body_response_sent', body_bytes=len(reply_world_body),
                                     body_sha256=hashlib.sha256(reply_world_body).hexdigest(),
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
                            send_environment_timers()
                            # Game-specific application replies are not implemented yet.
                        elif command == 13:
                            emit('client_closed')
                            break
                        else:
                            emit('unhandled_command', command=command)
                except (EOFError, OSError, ValueError) as error:
                    emit('connection_ended', state=state, reason=str(error))
                if control is not None:
                    control.disconnect()
                    if mailbox is not None:
                        mailbox.publish(control.snapshot())
                if args.single_session and state=='transport_ready':
                    break
        emit('finished', connections=number)
    log.close()


if __name__ == '__main__':
    main()
