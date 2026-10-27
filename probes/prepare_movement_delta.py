"""Validate Thai 0x516 speed updates without clearing other attributes."""
import argparse
import hashlib
import json
import struct
from native_codec_probe import NativeCodec, OUT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EBP, UC_X86_REG_XMM2

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--with-fall-limit', action='store_true',
               help='Also initialize record 46, the native downward velocity limit')
args = p.parse_args()

c = NativeCodec()
matrix = struct.unpack('<27I', bytes(c.uc.mem_read(0x28fb4e0, 108)))
triples = [matrix[i:i+3] for i in range(0, 27, 3)]
triples += [[30, 33, 32], [34, 38, 36], [51, 53, 52]]
values = {}
for indices in triples:
    for index, value in zip(indices, (560, 120, 560)):
        if not 0 <= index < 55 or (index in values and values[index] != value):
            raise ValueError('Invalid/conflicting speed attribute')
        values[index] = value
if args.with_fall_limit:
    # Diagnostic 60 m/s cap, not claimed to reproduce the original server.
    # Native 13C1AEA negates record 46; 13C1DF7..13C1E15 clamps downward
    # velocity to this bound. A zero record prevents falling altogether.
    values[46] = 6000

# The 0x516 native DTO has a count and up to 55 indexed 9-byte records.
# Actual callback 12787D0 -> 12D6F10 writes only these records to props+C29.
native = bytearray(2 + 55*9)
struct.pack_into('<H', native, 0, len(values))
for ordinal, (index, value) in enumerate(sorted(values.items())):
    struct.pack_into('<BII', native, 2+ordinal*9, index, value, value)
code, body = c.pack_type(0xdc6580, bytes(native))
if code:
    raise ValueError('Native delta writer failed')
decoded = c.decode_server(0x516, body)
actual = bytes(c.uc.mem_read(c.ROOT_OBJECT+10, len(native)))
if decoded['code'] or decoded['consumed'] != decoded['bytes'] or actual != native:
    raise ValueError(f'Delta round trip failed: {decoded}')
code, again = c.pack_type(0xdc6580, actual)
if code or again != body:
    raise ValueError('Non-canonical delta wire')

# Execute the real sparse updater against a patterned synthetic property block.
# Assert every byte outside the target records and change counter is preserved.
entity, vt, props, state, out = 0x10a00000, 0x10a02000, 0x10a04000, 0x10a08000, 0x10a10000
before = bytes((i*37+13) % 256 for i in range(0x3000))
expected = bytearray(before)
struct.pack_into('<I', expected, 4, (struct.unpack_from('<I', before, 4)[0]+1) & 0xffffffff)
for index, value in values.items():
    struct.pack_into('<BII', expected, 0xc29+index*9, index, value, value)
c.uc.mem_write(props, before)
c.uc.mem_write(c.OBJECT, bytes(native))
c.invoke(0x12d6f10, props, [c.OBJECT])
after = bytes(c.uc.mem_read(props, len(before)))
if after != expected:
    raise ValueError('Sparse update altered unrelated property bytes')

# Exercise the original calculator using only synthetic local entity lookups.
c.uc.mem_write(entity+0x10, struct.pack('<I', vt))
c.uc.mem_write(vt+0x54, struct.pack('<I', 0xe515a0))
c.uc.mem_write(entity+0x7c8, struct.pack('<I', state))
state_active = False
def support(uc, address, size, _):
    esp = uc.reg_read(UC_X86_REG_ESP)
    ret = c.read32(esp)
    if address == 0xe515a0:
        value = 256
        uc.reg_write(UC_X86_REG_EDX, 0)
    elif address == 0x113e2c0:
        if bytes(uc.mem_read(esp+4, 8)) != struct.pack('<Q', 256):
            raise ValueError('Wrong actor lookup')
        value = props
    elif address == 0x12ac680:
        value = int(state_active)
    else:
        raise ValueError('Unexpected synthetic support hook')
    uc.reg_write(UC_X86_REG_EAX, value)
    uc.reg_write(UC_X86_REG_ESP, esp+4)
    uc.reg_write(UC_X86_REG_EIP, ret)
for address in (0xe515a0, 0x113e2c0, 0x12ac680):
    c.uc.hook_add(UC_HOOK_CODE, support, begin=address, end=address)
calculated = []
cases = [(row, col, 0, 0, False) for row in range(3) for col in range(3)]
cases += [(0, 0, 1, 0, False), (0, 0, 0, 1, False), (0, 0, 0, 0, True)]
for row, col, flag1, flag2, state_active in cases:
    c.invoke(0x106fb20, 0, [entity, row, col, flag1, flag2, out, out+4, out+8])
    result = struct.unpack('<3f', bytes(c.uc.mem_read(out, 12)))
    if result != (560., 560., 120.):
        raise ValueError(f'Unexpected speed calculation: {result}')
    calculated.append(dict(row=row, col=col, flag1=flag1, flag2=flag2,
                           state_active=state_active, values=result))

# Execute that actual bounded clamp fragment with synthetic stack inputs.
# The endpoint precedes the remainder of the physics/game routine.
clamped = []
for limit, velocity, wanted in ((0, -500., 0.), (6000, -500., -500.), (6000, -7000., -6000.)):
    frame = c.STACK-0x10000
    c.uc.reg_write(UC_X86_REG_EBP, frame)
    c.uc.mem_write(frame-0x20, struct.pack('<f', velocity))
    c.uc.mem_write(frame-0x2c, struct.pack('<f', -float(limit)))
    c.uc.emu_start(0x13c1def, 0x13c1e15, timeout=1_000_000, count=1000)
    if c.uc.reg_read(UC_X86_REG_EIP) != 0x13c1e15:
        raise ValueError('Physics clamp did not reach the bounded endpoint')
    result = struct.unpack('<f', (c.uc.reg_read(UC_X86_REG_XMM2) & 0xffffffff).to_bytes(4, 'little'))[0]
    if result != wanted:
        raise ValueError(f'Unexpected native downward velocity clamp: {result}')
    clamped.append(dict(limit=limit, input=velocity, output=result))

prefix = 'movement-grounded-delta' if args.with_fall_limit else 'movement-delta'
(OUT/f'{prefix}.bin').write_bytes(body)
(OUT/f'{prefix}.native.bin').write_bytes(native)
report = dict(message='0x516', writer='0xDC6580', reader='0xDC6640',
              callback='0x12787D0', updater='0x12D6F10',
              body_bytes=len(body), native_bytes=len(native),
              sha256=hashlib.sha256(body).hexdigest(), decode=decoded,
              updated_indices=values, calculator='0x106FB20', calculated=calculated,
              downward_velocity_clamp=clamped,
              unrelated_property_bytes_preserved=True,
              status='live_confirmed_landing_and_basic_movement' if args.with_fall_limit else 'rejected_live_suspended_and_cannot_move',
              live_run='handshake-20261027-001723' if args.with_fall_limit else 'handshake-20261027-000108',
              limitation='Uniform native local speed baseline; diagnostic fall cap 6000; pose-specific tuning and combat unverified')
(OUT/f'{prefix}-validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('calculated','updated_indices')}, indent=2))
