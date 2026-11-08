"""Execute Thai lobby mode/start and container mapping consumers offline.

UI and connection dependencies are synthetic. This proves field semantics,
not visible button operation, clothing assets or original matchmaking rules.
"""
import json
import struct
from native_codec_probe import NativeCodec, ROOT
import sys
sys.path.insert(0, str(ROOT))
from offline_lobby import NativeLobby, POSITIONS, CRATES, lobby_item_wire
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
packets.extend(lobby.inventory.snapshot()[1:])
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
c.uc.mem_map(0, 4096)
actor_value, inventory_value = 0, 0
accepted = []
hook(0x1130200, lambda: finish(actor_value))
hook(0x1130310, lambda: finish(inventory_value))
def reached_inventory():
    accepted.append(True)
    c.uc.reg_write(UC_X86_REG_EIP, c.RETURN)
hook(0xf618f0, reached_inventory)
readiness = []
for actor_value, inventory_value, expected in ((0, 0x10950000, False),
                                             (0x10940000, 0, False),
                                             (0x10940000, 0x10950000, True)):
    c.decode_server(0x5fb, inventory)
    accepted.clear()
    c.invoke(0x128c740, 0, [c.ROOT_OBJECT + 6])
    if bool(accepted) != expected:
        raise ValueError(('Original inventory readiness branch differs', actor_value, inventory_value))
    readiness.append(dict(actor_present=bool(actor_value), inventory_present=bool(inventory_value),
                          reached_inventory_update=bool(accepted)))
report = dict(passed=True, template_team_mode=team_mode, modes=rows,
              containers=containers, packets=codec_rows,
              original_clothing_definitions=len(POSITIONS),
              inventory_readiness=readiness,
              limitation='Synthetic connection/UI boundary; no pixels or matchmaking service')
# Actual FE8200 expiration-display branches, with only clock/text lookup
# boundaries replaced. Keep game inventory encoding outside this change.
item = next(iter(lobby.inventory.items.values()))
for body, expected in ((item.wire(), 1), (lobby_item_wire(item), 0)):
    c.uc.mem_write(c.OBJECT, bytes(0x142))
    # Decode an item through the complete full-snapshot wrapper.
    payload = struct.pack('>I', 1) + b'\2\0' + body + bytes(9)
    result = c.decode_server(0x5fb, payload)
    if result['code'] or result['consumed'] != result['bytes']:
        raise ValueError(result)
    if c.read32(c.ROOT_OBJECT + 16 + 0xe) != expected:
        raise ValueError('Original DTO expiration field differs')
expiration_labels = []
hook(0x129ce50, lambda: finish(1700000000))
def capture_label():
    sp = c.uc.reg_read(UC_X86_REG_ESP)
    text = bytes(c.uc.mem_read(c.read32(sp + 4), 100)).split(b'\0', 1)[0].decode('ascii')
    expiration_labels.append(text)
    c.uc.reg_write(UC_X86_REG_EIP, c.RETURN)
hook(0x1130910, capture_label)
for expiry in (1, 0):
    c.uc.mem_write(0x10970000, bytes(0x100))
    c.uc.mem_write(0x10970038, struct.pack('<I', expiry))
    c.invoke(0xfe8200, 0x10970000, [0x10971000])
if expiration_labels != ['ITEM_USE_TIME_OUT', 'ITEM_USE_TIME_PERMANENT']:
    raise ValueError(expiration_labels)
report['old_and_corrected_expiration_labels'] = expiration_labels
slot_branches = []
lookup_value = 0
hook(0x793e90, lambda: finish(0x10981000, 4))
def factory_boundary():
    slot_branches[-1]['factory_reached'] = True
    c.uc.reg_write(UC_X86_REG_EIP, c.RETURN)
def removal_boundary():
    sp = c.uc.reg_read(UC_X86_REG_ESP)
    slot_branches[-1]['removal_object'] = c.read32(sp + 8)
    c.uc.reg_write(UC_X86_REG_EIP, c.RETURN)
hook(0xfe87b0, factory_boundary)
hook(0xf61840, removal_boundary)
for slot in (255, 256, 764):
    c.decode_server(0x5fb, struct.pack('>I', 1) + b'\2\0' + lobby_item_wire(item) + bytes(9))
    native = bytes(c.uc.mem_read(c.ROOT_OBJECT + 16, 0x142))
    c.uc.mem_write(c.OBJECT, native)
    c.uc.mem_write(0x10981000, bytes(4))
    slot_branches.append(dict(slot=slot, factory_reached=False))
    c.invoke(0xf61c40, 0x10980000, [slot, c.OBJECT])
    if not slot_branches[-1]['factory_reached']:
        raise ValueError('Original nonempty large-slot update did not reach its factory')
for slot, expected in ((255, 0x10982000), (256, 0)):
    c.uc.mem_write(c.OBJECT, bytes(0x142))
    c.uc.mem_write(0x10981000, struct.pack('<I', 0x10982000))
    slot_branches.append(dict(slot=slot, empty=True))
    c.invoke(0xf61c40, 0x10980000, [slot, c.OBJECT])
    if slot_branches[-1].get('removal_object') != expected:
        raise ValueError('Original empty large-slot removal boundary differs')
report['slot_update_boundaries'] = slot_branches
(ROOT / 'private/typed-gameplay/native-lobby-validation.json').write_text(
    json.dumps(report, indent=2), encoding='utf8')
print(json.dumps(report))
