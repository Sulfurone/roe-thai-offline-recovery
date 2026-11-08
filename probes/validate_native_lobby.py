"""Execute Thai lobby mode/start and container mapping consumers offline.

UI and connection dependencies are synthetic. This proves field semantics,
not visible button operation, clothing assets or original matchmaking rules.
"""
import json
import struct
from native_codec_probe import NativeCodec, ROOT
import sys
sys.path.insert(0, str(ROOT))
from offline_lobby import NativeLobby, POSITIONS, CRATES
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP

c = NativeCodec()
manager, context, output = 0x10900000, 0x10920000, 0x10921000

def finish(value=0, cleanup=0):
    sp = c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EAX, value)
    c.uc.reg_write(UC_X86_REG_EIP, c.read32(sp))
    c.uc.reg_write(UC_X86_REG_ESP, sp + 4 + cleanup)

def hook(address, fn):
    c.uc.hook_add(UC_HOOK_CODE, lambda *_: fn(), begin=address, end=address)

requests = []
def capture():
    sp = c.uc.reg_read(UC_X86_REG_ESP)
    command, pointer, length = struct.unpack('<III', c.uc.mem_read(sp + 4, 12))
    requests.append((command, bytes(c.uc.mem_read(pointer, length)).hex()))
    finish(1, 12)

c.uc.mem_write(0x2eed5b0, struct.pack('<I', context))
hook(0x12933a0, lambda: finish(manager))
hook(0xea4610, capture)
# Stop before unrelated movie/window work; original getter and sender execute.
hook(0xef0324, lambda: c.uc.reg_write(UC_X86_REG_EIP, c.RETURN))
rows = []
for mode, expected in ((0, []), (1, [(0x6e29, '00000002')]),
                       (2, [(0x6e29, '00000003')])):
    requests.clear()
    c.uc.mem_write(manager + 0x13560, struct.pack('<I', mode))
    c.invoke(0xef0300, 0, [])
    # Captured native DTO is little endian; wire encoding is tested separately.
    actual = [(mid, struct.pack('>I', int.from_bytes(bytes.fromhex(body), 'little')).hex())
              for mid, body in requests]
    if actual != expected:
        raise ValueError((mode, actual, expected))
    rows.append(dict(mode=mode, start_requests=actual))

containers = []
for wire, internal in ((1, 1), (2, 2), (4, 8), (5, 9), (6, 0)):
    c.uc.mem_write(output, bytes(0x40))
    c.invoke(0xf614a0, 0, [output, wire, 17, 0xffffffff, 0xffffffff])
    actual = c.read32(output)
    # Equipped slots below 10 use the separate weapon category (3).
    if actual != internal:
        raise ValueError((wire, actual, internal))
    containers.append(dict(wire=wire, ui_container=actual))

team = (ROOT / 'private/typed-gameplay/team.bin').read_bytes()
result = c.decode_server(0x7030, team)
if result['code'] or result['consumed'] != result['bytes']:
    raise ValueError(result)
team_mode = c.read32(c.ROOT_OBJECT + 14 + 8)
lobby = NativeLobby(team)
inventory = lobby.inventory.full_body()
packets = [(0x7030, lobby.team_body()), (0x701e, lobby.team_body()),
           (0x702c, struct.pack('>II', 0, 2)), (0x7022, bytes(8)),
           (0x5fb, inventory)]
transfer = struct.pack('>BBHBHHB', 1, 2, 0, 1, 15, 1, 0)
packets.extend(lobby.handle(0x3e80, transfer))
codec_rows = []
for mid, body in packets:
    result = c.decode_server(mid, body)
    if result['code'] or result['consumed'] != result['bytes']:
        raise ValueError((hex(mid), result))
    codec_rows.append(dict(message=hex(mid), **result))
catalog = json.loads((ROOT / 'private/gameplay-catalog/original-item-defaults.json').read_text(encoding='utf8'))
definitions = {row['dwStringID']: row for table in catalog['tables'] for row in table['rows']}
for template, slot in POSITIONS.items():
    row = definitions[template]
    if row['mCategory'] != 20 or row['szPositionArray'] != [slot] or not row['szAvatar3D_b']:
        raise ValueError(('Wrong original clothing metadata', template))
for template in CRATES:
    if definitions[template]['mCategory'] != 8:
        raise ValueError(('Wrong original warehouse metadata', template))
report = dict(passed=True, template_team_mode=team_mode, modes=rows,
              containers=containers, packets=codec_rows,
              original_clothing_definitions=len(POSITIONS),
              limitation='Synthetic connection/UI boundary; no pixels or matchmaking service')
(ROOT / 'private/typed-gameplay/native-lobby-validation.json').write_text(
    json.dumps(report, indent=2), encoding='utf8')
print(json.dumps(report))
