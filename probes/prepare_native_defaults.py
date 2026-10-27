"""Capture this client's own local-create defaults in offline emulation."""
import base64
import hashlib
import json
import struct
from native_codec_probe import NativeCodec, ROOT, OUT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP

profile = json.loads((ROOT / 'profiles' / 'uid-1-submission.json').read_text('utf-8'))
c = NativeCodec()
code, used, request = c.decode_create(base64.b64decode(profile['request_base64'])[26:])
assert code == 0
c.uc.mem_write(c.OBJECT, request)
c.uc.mem_write(0x290ddb8, struct.pack('<Q', 256))
captured = []

def capture(uc, address, size, user):
    stack = uc.reg_read(UC_X86_REG_ESP)
    pointer = struct.unpack('<I', bytes(uc.mem_read(stack + 4, 4)))[0]
    assert c.read32(pointer + 4) == 0
    captured.append(bytes(uc.mem_read(pointer + 8, 0x1597)))
    # The builder's output has been captured. Do not dispatch events or write
    # its local character map; finish at our emulator sentinel instead.
    uc.reg_write(UC_X86_REG_EIP, c.RETURN)

hook = c.uc.hook_add(UC_HOOK_CODE, capture, begin=0x1122ff0, end=0x1122ff0)
c.invoke(0x12773b0, 0, [c.OBJECT])
c.uc.hook_del(hook)
assert len(captured) == 1
native = captured[0]
assert struct.unpack_from('<Q', native)[0] == 256
assert native[0xc:0x8c] == request[4:0x84]
assert native[0x90:0x5cc] == request[0x84:0x5c0]
code, record = c.pack_record(native)
check, consumed, decoded = c.decode_record(record)
assert code == check == 0 and consumed == len(record) and decoded == native
previous_code, _, previous = c.decode_record((OUT / 'actor-record.bin').read_bytes())
assert previous_code == 0
report = {'builder': '0x12773b0', 'capture_before_callback': '0x1122ff0',
          'changed_native_bytes': [{'offset': hex(i), 'old': a, 'native_default': b}
                                   for i, (a, b) in enumerate(zip(previous, native)) if a != b],
          'record_wire_bytes': len(record)}
payloads = [('world-native-default.bin', 0x2ef, struct.pack('>III', 0, 1, 1) + record + bytes(18)),
            ('create-native-default.bin', 0x303, bytes(4) + record + bytes(8))]
for name, message, body in payloads:
    result = c.decode_server(message, body)
    assert result['code'] == 0 and result['consumed'] == result['bytes']
    (OUT / name).write_bytes(body)
    report[name] = {**result, 'sha256': hashlib.sha256(body).hexdigest()}
(OUT / 'native-default-validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
(OUT / 'actor-native-default.bin').write_bytes(native)
print(json.dumps(report, indent=2))
