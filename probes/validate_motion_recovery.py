"""Own-client codecs/callbacks for trajectory, receipt and spawn rotation.

No live process, renderer, network or original-resource redistribution.
"""
import json
from pathlib import Path
import struct
import sys
from native_codec_probe import NativeCodec, ROOT
sys.path.insert(0, str(ROOT))
from offline_motion import actor_motion, aircraft_spawn_heading
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP, UC_X86_REG_EIP

data = Path(sys.argv[1]).read_bytes()
samples, offset = [], 0
while offset + 26 <= len(data):
    size, message = struct.unpack_from('>IH', data, offset)
    if not 26 <= size <= 65536 or offset + size > len(data):
        break
    if message == 0x2a:
        samples.append(data[offset + 26:offset + size])
    offset += size
if not samples:
    raise ValueError('Expected own captured movement')
codec = NativeCodec()
bases = []
codec.uc.hook_add(UC_HOOK_CODE, lambda uc, *_: bases.append(uc.reg_read(UC_X86_REG_ECX)),
                 begin=0xdde540, end=0xdde540)
checks = []
for body in samples:
    bases.clear()
    result = codec.decode_server(0x2a, body)
    if result['code'] or result['consumed'] != result['bytes'] or len(bases) != 1:
        raise ValueError('Original movement decoder differs')
    base = bases[0]
    count = codec.read32(base)
    native_position = struct.unpack('<3i', codec.uc.mem_read(base + 4 + 19 * (count - 1), 12))
    native_sequence = codec.read32(base + 0x180)
    if actor_motion(body) != (native_position, native_sequence):
        raise ValueError('Python latest point / sequence differs from native DTO')
    checks.append(native_sequence)

actor, actor_vtable, avatar, avatar_vtable = 0x10800000, 0x10801000, 0x10802000, 0x10803000
getter, receiver = 0x10900000, 0x10900020
seen = []

def stub(uc, address, size, _):
    stack = uc.reg_read(UC_X86_REG_ESP)
    ret = codec.read32(stack)
    consumed = 0
    if address == 0x1130200:
        uc.reg_write(UC_X86_REG_EAX, actor)
    elif address == getter:
        uc.reg_write(UC_X86_REG_EAX, avatar)
    else:
        seen.append(codec.read32(codec.read32(stack + 4)))
        consumed = 4
    uc.reg_write(UC_X86_REG_ESP, stack + 4 + consumed)
    uc.reg_write(UC_X86_REG_EIP, ret)

for address in (0x1130200, getter, receiver):
    if address in (getter, receiver):
        codec.external_hooks.add(address)
        codec.uc.mem_write(address, b'\xc3')
    codec.uc.hook_add(UC_HOOK_CODE, stub, begin=address, end=address)
for address, value in ((actor + 16, actor_vtable), (actor_vtable + 0x108, getter),
                       (avatar, avatar_vtable), (avatar_vtable + 0xc4, receiver)):
    codec.uc.mem_write(address, struct.pack('<I', value))
for sequence in (1, 59, 80, 65536):
    result = codec.decode_server(0x36, struct.pack('>I', sequence))
    if result['code'] or result['consumed'] != result['bytes']:
        raise ValueError('Movement receipt DTO rejected')
    native = bytes(codec.uc.mem_read(codec.ROOT_OBJECT + 10, 4))
    codec.uc.mem_write(codec.OBJECT, struct.pack('<I', 0x36) + native)
    codec.invoke(0x1278450, 0, [codec.OBJECT])
if seen != [1, 59, 80, 65536]:
    raise ValueError('Native self-avatar callback does not receive receipt words')

source = (ROOT / 'private/typed-gameplay/vehicle-cross-map.bin').read_bytes()
body = aircraft_spawn_heading(source, (409400, 204800, 75000))
result = codec.decode_server(0x654b, body)
if result['code'] or result['consumed'] != result['bytes']:
    raise ValueError('Oriented aircraft DTO rejected')
dto = bytes(codec.uc.mem_read(codec.ROOT_OBJECT + 10, 0x1259))
rotations = []

def factory(uc, address, size, _):
    stack = uc.reg_read(UC_X86_REG_ESP)
    arguments = struct.unpack('<10I', uc.mem_read(stack, 40))
    rotations.append(struct.unpack('<4f', uc.mem_read(arguments[6], 16)))
    uc.reg_write(UC_X86_REG_EIP, codec.RETURN)

codec.uc.hook_add(UC_HOOK_CODE, factory, begin=0x10999d0, end=0x10999d0)
codec.uc.mem_write(codec.OBJECT, struct.pack('<I', 0x654b) + dto + bytes(64))
codec.invoke(0x1289610, 0, [codec.OBJECT])
if len(rotations) != 1 or not -.708 < rotations[0][2] < -.706:
    raise ValueError('Original factory quaternion differs')
report = dict(passed=True, native_motion_samples=len(checks), final_sequence=checks[-1],
              receipt_callback_words=seen, factory_quaternion=rotations[0],
              scope='DTOs and callback routing; queue lifetime and rendered orientation need live verification')
target = ROOT / 'private/native-roster/motion-recovery-validation.json'
target.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
