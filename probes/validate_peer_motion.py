"""Exercise the original Thai 0x27 registration, handler and waypoint queue."""
import json
import struct
import sys

from native_codec_probe import NativeCodec, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EFLAGS,
                              UC_X86_REG_EIP, UC_X86_REG_ESP)

sys.path.insert(0, str(ROOT))
from offline_bots import peer_motion


def main():
    codec = NativeCodec()
    uc = codec.uc
    registered = []

    def registration(uc, *_):
        sp = uc.reg_read(UC_X86_REG_ESP)
        registered.append(struct.unpack('<II', uc.mem_read(sp + 4, 8)))
        uc.emu_stop()

    hook = uc.hook_add(UC_HOOK_CODE, registration, begin=0xd56600, end=0xd56600)
    uc.reg_write(UC_X86_REG_ESP, codec.STACK)
    uc.reg_write(UC_X86_REG_EFLAGS, 2)
    uc.emu_start(0x3415b37, codec.RETURN, count=3000)
    uc.hook_del(hook)
    if registered != [(0x27, 0x12783c0)]:
        raise ValueError(f'Unexpected native registration: {registered}')

    actor, controller, ride, nodes = 0x10900000, 0x10901000, 0x10902000, 0x10903000
    queue = controller + 0x80 + 0xc0 + 0xb8
    uid = 0x0001000000001100
    uc.mem_map(0, 4096)  # Native handler uses the x86 SEH head.
    for address, value in ((actor + 0x10, 0x25a3780), (actor + 0x348, controller),
                           (actor + 0x7c8, ride), (actor + 0x2f8, 0x402),
                           (controller, 0x261e788), (controller + 8, actor),
                           (queue, queue), (queue + 4, queue)):
        uc.mem_write(address, struct.pack('<I', value))

    allocated = []

    def dependency(uc, address, *_):
        sp = uc.reg_read(UC_X86_REG_ESP)
        ret = codec.read32(sp)
        if address == 0x1130320:
            if struct.unpack('<Q', uc.mem_read(sp + 4, 8))[0] != uid:
                raise ValueError('Actor lookup received a different UID')
            result = actor
        else:
            if codec.read32(sp + 4) != 0xa0 or len(allocated) >= 2:
                raise ValueError('Unexpected waypoint allocation')
            result = nodes + len(allocated) * 0x100
            allocated.append(result)
        uc.reg_write(UC_X86_REG_EAX, result)
        uc.reg_write(UC_X86_REG_ESP, sp + 4)
        uc.reg_write(UC_X86_REG_EIP, ret)

    for address in (0x1130320, 0x65ae50):
        uc.hook_add(UC_HOOK_CODE, dependency, begin=address, end=address)

    def deliver(message, body):
        result = codec.decode_server(message, body)
        if result['code'] or result['consumed'] != result['bytes']:
            raise ValueError(result)
        dto = bytes(uc.mem_read(codec.ROOT_OBJECT + 10, len(body)))
        uc.mem_write(codec.OBJECT, struct.pack('<I', message) + dto)
        codec.invoke(registered[0][1], 0, [codec.OBJECT])

    waypoints = [((46323, 204001, 9631), 17), ((46370, 204025, 9641), 18)]
    message, body = peer_motion(uid, *waypoints[0])
    legacy = bytearray(body)
    legacy[21] = 0
    deliver(message, bytes(legacy))
    if codec.read32(queue + 8) or allocated:
        raise ValueError('The previous mode unexpectedly queued a waypoint')
    for point, sequence in waypoints:
        deliver(*peer_motion(uid, point, sequence))

    actual = [(struct.unpack('<3f', uc.mem_read(node + 8, 12)), codec.read32(node + 0x64))
              for node in allocated]
    if (actual != waypoints or codec.read32(queue + 8) != len(waypoints)
            or codec.read32(queue) != nodes or codec.read32(queue + 4) != nodes + 0x100):
        raise ValueError(f'Native waypoint queue differs: {actual}')
    report = dict(passed=True, handler=hex(registered[0][1]), legacy_waypoints=0,
                  new_waypoints=actual, limitation='Synthetic actor lookup and allocator; no live renderer')
    target = ROOT / 'private/typed-gameplay/peer-motion-validation.json'
    target.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
