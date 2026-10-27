"""Build a west-to-east opening route from the original map/collision bounds."""
import hashlib
import json
import math
import struct
import xml.etree.ElementTree as ET


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
    text=(root/'start_offline_airdrop.cmd').read_text(encoding='utf-8')
    text=text.replace('--gameplay-auto-exit-seconds 40',f'--gameplay-auto-exit-seconds {duration:g}')
    text=text.replace('--gameplay-aircraft-route-speed 2000',
        f'--gameplay-aircraft-route-speed {speed} --gameplay-aircraft-route-end {endpoint[0]} {endpoint[1]} {endpoint[2]}')
    text=text.replace('scene-glider.bin','scene-cross-map.bin').replace('vehicle-helicopter.bin','vehicle-cross-map.bin')
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
    test=text.replace(f'--gameplay-auto-exit-seconds {duration:g}','--gameplay-auto-exit-seconds 12')
    test=test.replace('Native jump prompt after 3 seconds.','Self-test: auto-exit after 12 seconds near the west edge.')
    (root/'start_airdrop_selftest.cmd').write_text(test,encoding='utf-8')
    (target/'airdrop-route.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
