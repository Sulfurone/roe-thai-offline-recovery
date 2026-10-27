"""Read bounded GliderInfo prefixes from the user's original Thai table.

The prefix layout is checked against reflection at 0x1100F70. This does
not deserialize the remaining effect/camera/mode lists or render assets.
"""
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'extracted/tablebin/57962c80fe2b4d75.bin'
blob=source.read_bytes()
if not len(blob)<65536 or not blob.startswith(b'\x13QSGliderConfigTable'*2):
    raise ValueError('Unexpected original Thai glider configuration table')

rows=[]
for config,label in ((3,'STR_LOCALIZE_1'),(4,'STR_LOCALIZE_2')):
    encoded=label.encode('ascii')
    marker=struct.pack('<HI',13,config)+bytes([0xc0+len(encoded)])+encoded
    start=blob.find(marker)
    if start<0 or blob.find(marker,start+1)>=0:
        raise ValueError('Expected one unambiguous version-13 GliderInfo prefix')
    cursor=start+len(marker)

    def value(fmt):
        global cursor
        values=struct.unpack_from('<'+fmt,blob,cursor)
        cursor+=struct.calcsize('<'+fmt)
        return values[0] if len(values)==1 else values

    def version(expected):
        if value('H')!=expected:
            raise ValueError('Original table prefix version differs')

    force_height,auto_height,angle=value('3f')
    version(24)
    movement=value('24f')
    version(5) # GliderMotionBlurConfig
    version(2) # Vector2 blur centre
    blur=value('6f')
    version(5) # GliderAppearanceConfig
    avatar=value('I')
    if avatar!={3:117,4:124}[config]:
        raise ValueError('Unexpected original appearance category')
    rows.append(dict(config=config,avatar_category=avatar,start=start,prefix_end=cursor,
        force_pull_height_cm=force_height,auto_leave_height_cm=auto_height,
        speed_angle=angle,vertical_acceleration=movement[0],horizontal_speed=movement[2]))

report=dict(table='QSGliderConfigTable',source_sha256=hashlib.sha256(blob).hexdigest(),
    original_reflection='0x1100F70',appearance_native_offset='0x8C',rows=rows,
    scope='Validated record prefixes only; no factory, asset loading or graphics execution')
destination=ROOT/'private/native-roster/aircraft-appearance-prefixes.json'
destination.parent.mkdir(parents=True,exist_ok=True)
destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
