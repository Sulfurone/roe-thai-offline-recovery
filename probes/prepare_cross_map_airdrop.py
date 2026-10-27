"""Build a west-to-east opening route from the original map/collision bounds."""
import hashlib
import json
import math
import re
import struct
import xml.etree.ElementTree as ET


def set_vehicle_push_phase(text, phase):
    """Move the one 0x654B fixture to a precise map lifecycle phase."""
    if phase not in ('load-success', 'map-load', 'player-ready'):
        raise ValueError(f'Unknown vehicle push phase: {phase}')
    pattern = r'--push-after-(?:load-success|map-load|player-ready) 0x654b:'
    text, replacements = re.subn(pattern, f'--push-after-{phase} 0x654b:', text)
    if replacements != 1 or text.count('0x654b:') != 1:
        raise ValueError('Expected exactly one staged 0x654B vehicle push')
    return text


def remove_environment_clock(text):
    """Keep aircraft phase tests on the verified no-clock loading baseline."""
    text = re.sub(r'\s+--environment-hour\s+\d+', '', text)
    text = re.sub(r'\s+--environment-trigger\s+(?:player-ready|load)', '', text)
    text = re.sub(r'\s+--environment-ready-delay\s+[0-9.]+', '', text)
    text = text.replace(' --environment-once', '')
    return text


def prepare(root,target,codec):
    source=root/'private/terrain-collision/RigidTerrain.repx'
    if not source.exists() or source.stat().st_size>64*1024*1024:
        raise ValueError('Expected bounded original map collision extraction')
    xml=ET.parse(source).getroot()
    field=xml.find('PxHeightField')
    rigid=xml.find('PxRigidStatic')
    rows,columns=int(field.findtext('NbRows')),int(field.findtext('NbColumns'))
    geometry=rigid.find('.//PxHeightFieldGeometry')
    if geometry is None:
        geometry=rigid.find('.//Geometry')[0]
    row_scale=float(geometry.findtext('RowScale'))
    column_scale=float(geometry.findtext('ColumnScale'))
    height_scale=float(geometry.findtext('HeightScale'))
    pose=tuple(float(x) for x in rigid.findtext('GlobalPose').split())
    if (rows,columns)!=(2049,2049) or pose[:4]!=(.5,.5,.5,.5) or pose[4:6]!=(0.,0.):
        raise ValueError('Unrecognized original terrain coordinate mapping')
    width,height=round((columns-1)*column_scale),round((rows-1)*row_scale)
    candidates=[]
    for filename in ('4cb34086e137e475.bin','60a7426da20a1759.bin'):
        blob=(root/'extracted/tablebin'/filename).read_bytes()
        marker=struct.pack('<HI',29,16006)
        start=blob.find(marker)
        if start<0 or blob.find(marker,start+1)>=0:
            raise ValueError('Missing or ambiguous map 16006 row')
        cursor=start+6
        strings=[]
        for _ in range(3):
            size=blob[cursor]-0xc0
            if not 0<=size<=63:
                raise ValueError('Unknown map table string encoding')
            cursor+=1
            strings.append(blob[cursor:cursor+size].decode('utf-8'))
            cursor+=size
        map_width,map_height=struct.unpack_from('<II',blob,cursor)
        candidates.append(dict(file=filename,row_offset=start,name=strings[0],
            root_dir=strings[1],sub_dir=strings[2],width_m=map_width,height_m=map_height,
            sha256=hashlib.sha256(blob).hexdigest()))
    matching=[x for x in candidates if (x['width_m']*100,x['height_m']*100)==(width,height)]
    if len(matching)!=1 or matching[0]['root_dir']!='EU_KillZone_2048':
        raise ValueError('Map table and original collision extent disagree')
    # The original quaternion permutes local height Y to world Z, local
    # columns Z to world X, and local rows X to world Y.
    samples=field.findtext('samples').split()
    if len(samples)!=rows*columns:
        raise ValueError('Heightfield sample count differs')
    centre_row=rows//2
    raw_line=[int(x)&0xffff for x in samples[centre_row*columns:(centre_row+1)*columns]]
    line=[(x-65536 if x&32768 else x)*height_scale+pose[6] for x in raw_line]
    maximum=max(line)
    altitude=max(50000,math.ceil((maximum+15000)/5000)*5000)
    if altitude>150000:
        raise ValueError('Crossing altitude exceeds the tested coordinate envelope')
    origin=(200,round(height/2),altitude)
    endpoint=(width-200,round(height/2),altitude)
    speed=5000
    duration=math.dist(origin,endpoint)/speed
    if not 3<duration<=180:
        raise ValueError('Crossing duration exceeds opening route envelope')
    report={'map_id':16006,'world_units':'centimetres',
            'map_bounds_xy_cm':[0,0,width,height], 'start_cm':origin,'end_cm':endpoint,
            'direction':[1.,0.,0.],'speed_cm_per_second':speed,'flight_seconds':duration,
            'centreline_max_terrain_z_cm':maximum,'minimum_vertical_clearance_cm':altitude-maximum,
            'map_table':matching[0],'alternate_map_tables':candidates,
            'terrain_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'limitation':'Original terrain bounds; local straight crossing, not recovered official route selection'}
    for name,message,writer,source_name,native_size,position_offset in (
        ('scene-cross-map.bin',0xdcf,0xdd2090,'scene-glider.bin',0xaa1,0x65c),
        ('vehicle-cross-map.bin',0x654b,0xe11e50,'vehicle-helicopter.bin',0x1259,0x94)):
        codec.decode_server(message,(target/source_name).read_bytes())
        native=bytearray(codec.uc.mem_read(codec.ROOT_OBJECT+10,native_size))
        struct.pack_into('<3i',native,position_offset,*origin)
        code,body=codec.pack_type(writer,bytes(native))
        result=codec.decode_server(message,body)
        if code or result['code'] or result['consumed']!=len(body)+10:
            raise ValueError(f'Cross-map fixture codec failed: {name}')
        if bytes(codec.uc.mem_read(codec.ROOT_OBJECT+10,native_size))!=native:
            raise ValueError(f'Cross-map fixture native roundtrip failed: {name}')
        (target/name).write_bytes(body)
        report[name]={'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
    text=remove_environment_clock((root/'start_offline_airdrop.cmd').read_text(encoding='utf-8'))
    text=text.replace('--gameplay-auto-exit-seconds 40',f'--gameplay-auto-exit-seconds {duration:g}')
    text=text.replace('--gameplay-aircraft-route-speed 2000',
        f'--gameplay-aircraft-route-speed {speed} --gameplay-aircraft-route-end {endpoint[0]} {endpoint[1]} {endpoint[2]}')
    text=text.replace('scene-glider.bin','scene-cross-map.bin').replace('vehicle-helicopter.bin','vehicle-cross-map.bin')
    # Thai sends one DCD for the lobby and a second for the actual map. Spawn
    # in the second-DCD window: the map exists, but the first actor MOVE_1 has
    # not yet started the live camera/physics loop. Player-ready creation was
    # observed to race that loop and is kept out of all opening-airdrop stages.
    text=set_vehicle_push_phase(text,'map-load')
    if '--gameplay-auto-board-delay' not in text:
        text=text.replace('--gameplay-auto-seat','--gameplay-auto-seat --gameplay-auto-board-delay 2')
    text=text.replace('Thai opening airdrop: board, fly, native jump prompt after 3 seconds. Auto-exit at 40 seconds.',
        f'Thai opening airdrop: west edge to east edge across {width/100:g} metres, {duration:g} seconds. Native jump prompt after 3 seconds.')
    (root/'start_offline_airdrop.cmd').write_text(text,encoding='utf-8')
    combined=text.replace('--gameplay-state-file "%~dp0profiles\\uid-1-offline-inventory.json"',
        '--gameplay-ground-loot --gameplay-arsenal --gameplay-world-file "%~dp0profiles\\uid-1-offline-drop-arsenal.json"')
    if combined==text:
        raise ValueError('Expected independent air-drop inventory option')
    combined=combined.replace('Thai opening airdrop:',
        'Thai airdrop and arsenal test:')
    (root/'start_offline_airdrop_arsenal.cmd').write_text(combined,encoding='utf-8')
    parachute=combined.replace('--gameplay-opening-airdrop',
        '--gameplay-opening-airdrop --gameplay-opening-glider-file "%~dp0private\\typed-gameplay\\vehicle-glider.bin" '
        '--gameplay-landing-terrain "%~dp0private\\terrain-collision\\RigidTerrain.repx"')
    parachute=parachute.replace('uid-1-offline-drop-arsenal.json','uid-1-offline-parachute.json')
    parachute=parachute.replace('--seconds 43200','--seconds 43200 --port 8002 --single-session')
    parachute=parachute.replace('Thai airdrop and arsenal test:','Thai daylight parachute test:')
    parachute=parachute.replace('echo Thai daylight parachute test:',
        'tasklist /FI "IMAGENAME eq Europa_Client.exe" /NH | find /I "Europa_Client.exe" >nul\n'
        'if not errorlevel 1 (\n  echo Close the current game window before starting the parachute session.\n'
        '  pause\n  exit /b 1\n)\n\necho Thai daylight parachute test:')
    parachute=parachute.replace('Native jump prompt after 3 seconds.',
        'Native jump prompt after 3 seconds. A separate Thai glider unfolds after exit and releases near terrain or after 8 seconds.')
    (root/'start_parachute_glider_experimental.cmd').write_text(parachute,encoding='utf-8')
    parachute_test=parachute.replace(f'--gameplay-auto-exit-seconds {duration:g}',
        '--gameplay-auto-exit-seconds 12').replace('uid-1-offline-parachute.json',
        'uid-1-offline-parachute-selftest.json')
    parachute_test=parachute_test.replace('Native jump prompt after 3 seconds.',
        'Self-test: automatic aircraft exit after 12 seconds.')
    (root/'start_parachute_selftest.cmd').write_text(parachute_test,encoding='utf-8')
    test=text.replace(f'--gameplay-auto-exit-seconds {duration:g}','--gameplay-auto-exit-seconds 12')
    test=test.replace('Native jump prompt after 3 seconds.','Self-test: auto-exit after 12 seconds near the west edge.')
    (root/'start_airdrop_selftest.cmd').write_text(test,encoding='utf-8')
    # Explicit phase gates keep aircraft creation, seating, route movement and
    # parachute transfer independently testable in the real client. They all
    # reuse the same map-load spawn body and deliberately omit the environment
    # clock until the remaining daytime-clock freeze is solved separately.
    staged_base=text
    for option in (
        '--gameplay-auto-seat', '--gameplay-auto-board-delay 2',
        '--gameplay-initialize-vehicle',
        f'--gameplay-auto-exit-seconds {duration:g}',
        '--gameplay-opening-airdrop',
        f'--gameplay-aircraft-route-speed {speed}',
        f'--gameplay-aircraft-route-end {endpoint[0]} {endpoint[1]} {endpoint[2]}'):
        staged_base=staged_base.replace(' '+option,'')
    staged_base=staged_base.replace(
        '--gameplay-inventory --gameplay-state-file "%~dp0profiles\\uid-1-offline-inventory.json"','')
    staged_base='\n'.join(line for line in staged_base.splitlines()
        if '--push-after-player-ready 0x05fb:' not in line
        and '--push-after-player-ready 0x04a0:' not in line)+'\n'
    staged_base=staged_base.replace('--seconds 43200 --launch','--seconds 43200 --port 8002 --single-session --launch')

    board=staged_base.replace('--gameplay-prototype',
        '--gameplay-prototype --gameplay-auto-seat --gameplay-auto-board-delay 2 --gameplay-initialize-vehicle')
    board=board.replace(
        f'Thai opening airdrop: west edge to east edge across {width/100:g} metres, {duration:g} seconds. Native jump prompt after 3 seconds.',
        'Thai aircraft phase B: spawn at map-load and board after 2 seconds; no route or forced exit.')
    (root/'start_aircraft_phase_b_board.cmd').write_text(board,encoding='utf-8')

    route=board.replace('--gameplay-initialize-vehicle',
        f'--gameplay-initialize-vehicle --gameplay-aircraft-route-speed {speed} '
        f'--gameplay-aircraft-route-end {endpoint[0]} {endpoint[1]} {endpoint[2]}')
    route=route.replace(
        'Thai aircraft phase B: spawn at map-load and board after 2 seconds; no route or forced exit.',
        'Thai aircraft phase C: spawn, board and fly the bounded route; no forced exit or glider transfer.')
    (root/'start_aircraft_phase_c_route.cmd').write_text(route,encoding='utf-8')

    # The real client accepted its native jump request and completed landing in
    # the phase-C live test. Make that minimal, user-controlled path the normal
    # parachute entry. Keep synthetic glider creation under an explicitly named
    # experimental launcher so it cannot silently replace the working path.
    manual=route.replace(
        'Thai aircraft phase C: spawn, board and fly the bounded route; no forced exit or glider transfer.',
        'Thai offline parachute: board at the west edge, fly east, then use the native jump control and land normally.')
    manual=manual.replace('echo Thai offline parachute:',
        'tasklist /FI "IMAGENAME eq Europa_Client.exe" /NH | find /I "Europa_Client.exe" >nul\n'
        'if not errorlevel 1 (\n  echo Close the current game window before starting the parachute session.\n'
        '  pause\n  exit /b 1\n)\n\necho Thai offline parachute:')
    (root/'start_offline_parachute.cmd').write_text(manual,encoding='utf-8')

    # Keep the proven parachute launcher unchanged until this isolated
    # environment gate has passed a real-client run.  It sends the native
    # clock only after the first valid player position; the Thai client's own
    # time/weather tables then select daytime and weather resources.
    day_weather=manual.replace('--launch --gameplay-prototype',
        '--launch --environment-hour 12 --environment-trigger player-ready '
        '--environment-ready-delay 1 --gameplay-prototype')
    day_weather=day_weather.replace(
        'Thai offline parachute: board at the west edge, fly east, then use the native jump control and land normally.',
        'Thai daytime/weather probe: the clock starts at noon after world readiness; native weather tables remain active.')
    (root/'start_offline_day_weather.cmd').write_text(day_weather,encoding='utf-8')

    for staged in (board,route,manual):
        if staged.count('--push-after-map-load 0x654b:') != 1:
            raise ValueError('Aircraft phase launcher lost the map-load spawn gate')
        if any(flag in staged for flag in ('--gameplay-opening-airdrop','--gameplay-opening-glider-file',
                                            '--gameplay-inventory','--gameplay-ground-loot',
                                            '--push-after-player-ready','--environment-hour','--environment-trigger',
                                            '--environment-ready-delay','--environment-once')):
            raise ValueError('Aircraft phase launcher contains a later-stage or clock option')
    if day_weather.count('--environment-hour 12') != 1 or '--environment-trigger player-ready' not in day_weather:
        raise ValueError('Day/weather launcher lost its player-ready environment gate')
    (target/'airdrop-route.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
