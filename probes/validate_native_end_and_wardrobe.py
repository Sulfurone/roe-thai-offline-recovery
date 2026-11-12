"""Check Thai 32838 result and wardrobe packets using the original offline codecs.

Requires the player's own diagnostic image and world templates. GUI and
inventory entry points are observed at their native call boundaries.
"""
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native_codec_probe import NativeCodec
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP

from offline_inventory import OfflineInventory
from offline_lobby import NativeLobby, world_with_wardrobe
from offline_round_result import LocalRoundResult
from offline_vitals import Vitals


def main():
    codec = NativeCodec()
    codec.uc.mem_map(0, 4096)
    payload = codec.ROOT_OBJECT + 10
    events = []

    def hook(address, action, arguments=0):
        def intercept(uc, *_):
            stack = uc.reg_read(UC_X86_REG_ESP)
            result = action(stack)
            uc.reg_write(UC_X86_REG_EAX, result or 0)
            uc.reg_write(UC_X86_REG_EIP, codec.read32(stack))
            uc.reg_write(UC_X86_REG_ESP, stack + 4 * (arguments + 1))
        codec.uc.hook_add(UC_HOOK_CODE, intercept, begin=address, end=address)

    def decode(mid, body):
        result = codec.decode_server(mid, body)
        assert result['code'] == 0 and result['consumed'] == result['bytes'], (mid, result)

    team = (ROOT / 'private/typed-gameplay/team.bin').read_bytes()
    room = (ROOT / 'private/native-roster/room-start-h.bin').read_bytes()
    room_uid = struct.unpack_from('>Q', room)[0]
    name_size = struct.unpack_from('>I', team, 40)[0]
    name = team[44:44 + name_size]
    game = SimpleNamespace(actor_ready=True, actor_uid=256, vitals=Vitals(current=0))
    result = LocalRoundResult(game, SimpleNamespace(count=63, vitals={}))
    assert result.tick()
    packets = dict(result.native_messages(room_uid, name, killer_uid=500, killer_name=b'OfflineBot1'))

    manager, panel, vtable = 0x10900000, 0x10920000, 0x10930000
    codec.uc.mem_write(panel, struct.pack('<I', vtable))
    codec.uc.mem_write(vtable + 0xb0, struct.pack('<I', 0x401000))
    hook(0x12933a0, lambda _: manager)
    hook(0xea4610, lambda stack: events.append(codec.read32(stack + 4)), 3)
    hook(0xebc650, lambda _: 1)
    hook(0x10ea020, lambda _: 2)
    hook(0xe7d080, lambda _: None, 2)
    hook(0xe79690, lambda _: panel, 1)
    hook(0xebcd50, lambda stack: events.append(struct.unpack('<4I', bytes(codec.uc.mem_read(
        codec.read32(stack + 4) + 0x90, 16)))), 1)
    hook(0x401000, lambda _: events.append('show original result panel'), 1)

    decode(0x0d77, packets[0x0d77])
    codec.invoke(0x1278ae0, 0, [payload - 4])
    assert struct.unpack('<Q', bytes(codec.uc.mem_read(manager + 0x137c0, 8)))[0] == room_uid
    decode(0x106e, packets[0x106e])
    assert codec.read32(payload) == 500
    decode(0x0d62, packets[0x0d62])
    codec.invoke(0x128d6d0, 0, [payload - 4])
    assert events == [0x0d75, (64, 64, 64, 64), 'show original result panel'], events
    print('Native Thai callback accepted the match id and reached the original outcome-panel display call.')

    lobby = NativeLobby(team)
    transfer = struct.pack('>BBHBHHB', 1, 2, 0, 1, 15, 1, 0)
    assert lobby.handle(0x3e80, transfer)
    clothes = lobby.inventory.worn_clothes()
    world = (ROOT / 'private/typed-gameplay/world.bin').read_bytes()
    dressed_world = world_with_wardrobe(world, clothes)
    decode(0x02ef, dressed_world)
    code, used, actor = codec.decode_record(dressed_world[12:-18])
    assert code == 0 and used == len(dressed_world) - 30 and actor[6] == 0
    for (_, slot), item in clothes:
        assert struct.unpack_from('<4I', actor, 0x5e1 + slot * 0x78 + 0x14) == (1, item.template, 1, 0)
    inventory = OfflineInventory(0)
    inventory.items.clear()
    decode(0x05fb, inventory.full_body(clothes))
    assert codec.uc.mem_read(payload + 0x1f680, 1) == b'\1'
    for index, ((container, slot), item) in enumerate(clothes):
        row = payload + 4 + index * 0x144
        assert bytes(codec.uc.mem_read(row, 2)) == bytes((container, slot))
        assert codec.read32(row + 4) == item.template

    equipped = []
    hook(0x1130200, lambda _: manager)
    hook(0x11302f0, lambda _: panel)
    hook(0x10eac20, lambda _: None)
    hook(0xf618f0, lambda _: None)
    hook(0xf61d60, lambda stack: equipped.append((codec.read32(stack + 4),
                                                 codec.read32(codec.read32(stack + 8) + 2))), 2)
    def stop_after_inventory(uc, *_):
        uc.reg_write(UC_X86_REG_EIP, codec.RETURN)
    codec.uc.hook_add(UC_HOOK_CODE, stop_after_inventory, begin=0x128c813, end=0x128c813)
    codec.invoke(0x128c740, 0, [payload - 4])
    assert equipped == [(slot, item.template) for (_, slot), item in clothes], equipped
    print('Native Thai client reached its match equipment update with the selected garments.')


if __name__ == '__main__':
    main()
