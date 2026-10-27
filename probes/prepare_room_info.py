"""Encode one local room using this Thai client's own room serializer."""
from pathlib import Path
import hashlib
import json
import struct
from native_codec_probe import NativeCodec, OUT

c = NativeCodec()
actor = (OUT / 'actor-native-default.bin').read_bytes()
if len(actor) != 0x1597:
    raise ValueError('Expected the captured native local-create record')
room = bytearray(0x6e04)
struct.pack_into('<Q', room, 0, 1)
room[8:0x88] = actor[0xc:0x8c]
# Names established by QSUIInRoomPanel::InRoomDataRefreshed, not guesses:
struct.pack_into('<I', room, 0x88, 0)     # roomMode
struct.pack_into('<I', room, 0x8c, 0)     # roomStatus
struct.pack_into('<I', room, 0x90, 16006) # map id used by native local-create
struct.pack_into('<Q', room, 0x94, 256)   # owner id matches roster
struct.pack_into('<I', room, 0x9c, 1)     # playerMaxCount
struct.pack_into('<I', room, 0xa0, 1)     # playerCount (native bound 200)
struct.pack_into('<Q', room, 0xa4, 256)
room[0xac:0x12c] = actor[0xc:0x8c]
struct.pack_into('<I', room, 0x12c, 0)    # member's remaining field, meaning unproven
code, body = c.pack_type(0xddb0b0, bytes(room))
if code:
    raise ValueError(f'Native room serializer returned {code}')
decoded = c.decode_server(0x6ef7, body)
if decoded['code'] or decoded['consumed'] != decoded['bytes']:
    raise ValueError(f'Full native room packet failed: {decoded}')
roundtrip = bytes(c.uc.mem_read(c.ROOT_OBJECT + 10, 0x6e04))
if roundtrip != room:
    raise ValueError('Native full room DTO differs after roundtrip')
path = OUT / 'room-info-one.bin'
path.write_bytes(body)
report = {**decoded, 'body_bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
          'writer': '0xddb0b0', 'reader': '0xddb270', 'native_bytes': len(room),
          'roundtrip_equal': True, 'map_id_candidate': 16006,
          'status': 'native_codec_validated_ui_unverified'}
(OUT / 'room-info-validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))

# Negative fixture only: 0x128F0F0 -> 0x1113320 unconditionally reports
# body+0xC as an error. UI confirmed code 0 ALSO opens an error dialog.
# Never use this packet as a successful start response.
reply = struct.pack('>QII', 1, 0, 0)
reply_check = c.decode_server(0x6efc, reply)
if reply_check['code'] or reply_check['consumed'] != reply_check['bytes']:
    raise ValueError(f'Native room start reply failed: {reply_check}')
(OUT / 'room-start-error-zero.bin').write_bytes(reply)
print(json.dumps({'negative_room_start_error':reply_check, 'ui_result':'Server ErrorCode: 0',
                  'sha256':hashlib.sha256(reply).hexdigest()}))
