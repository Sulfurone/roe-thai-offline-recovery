"""Run this client's pure codecs offline in bounded x86 emulation.

No operating-system callbacks, network or live-game memory access. The only
external function simulated is memcpy/memmove for local emulator buffers.
"""
from pathlib import Path
import base64
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'private' / 'runtime-diag-1'
OUT = ROOT / 'private' / 'native-roster'
sys.path.insert(0, str(ROOT / 'python-libs'))
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX,
    UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP,
    UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EFLAGS, UC_X86_REG_CR0,
    UC_X86_REG_CR4)


class NativeCodec:
    OBJECT = 0x10000000
    READER = 0x10100000
    WIRE = 0x10200000
    ROOT_OBJECT = 0x10600000
    STACK = 0x20100000
    RETURN = 0x30000000

    def __init__(self):
        blob = (WORK / 'thai-self-image.bin').read_bytes()
        if blob[:8] != b'ROETHAI1':
            raise ValueError('Not our bounded diagnostic image')
        base, size = struct.unpack_from('<II', blob, 8)
        self.base, self.size = base, size
        self.image = blob[16:]
        if len(self.image) != size or base != 0x400000:
            raise ValueError('Wrong image range')
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.uc.mem_map(base, size)
        self.uc.mem_write(base, self.image)
        self.uc.mem_map(0x10000000, 0x1000000)
        self.uc.mem_map(0x20000000, 0x200000)
        self.uc.mem_map(self.RETURN, 0x1000)
        self.uc.mem_write(self.RETURN, b'\xf4')
        self.invalid = None
        self.uc.hook_add(UC_HOOK_MEM_INVALID, self._invalid)
        copy_pointer = struct.unpack_from('<I', self.image, 0x1cc16a4 - base)[0]
        self.external_hooks = {copy_pointer}
        page = copy_pointer & ~4095
        if not base <= page < base + size:
            self.uc.mem_map(page, 0x1000)
            self.uc.mem_write(page, b'\xcc' * 4096)
            self.uc.mem_write(copy_pointer, b'\xc3')
        self.uc.hook_add(UC_HOOK_CODE, self._copy, begin=copy_pointer, end=copy_pointer)
        for address in [0x1428e28]:
            self.uc.hook_add(UC_HOOK_CODE, self._copy, begin=address, end=address)
        self.uc.hook_add(UC_HOOK_CODE, self._set, begin=0x1428e3a, end=0x1428e3a)
        self.uc.hook_add(UC_HOOK_CODE, self._code_guard)
        self.uc.reg_write(UC_X86_REG_CR0, self.uc.reg_read(UC_X86_REG_CR0) & ~4)
        self.uc.reg_write(UC_X86_REG_CR4, self.uc.reg_read(UC_X86_REG_CR4) | 0x200)

    def _invalid(self, uc, access, address, size, value, user):
        self.invalid = {'access': access, 'address': hex(address), 'size': size,
                        'eip': hex(uc.reg_read(UC_X86_REG_EIP))}
        return False

    def _code_guard(self, uc, address, size, user):
        if not self.base <= address < self.base + self.size and address not in self.external_hooks:
            raise ValueError(f'Unprovided offline executable dependency: {address:#x}')

    def read32(self, address):
        return struct.unpack('<I', bytes(self.uc.mem_read(address, 4)))[0]

    def _copy(self, uc, address, size, user):
        stack = uc.reg_read(UC_X86_REG_ESP)
        ret, destination, source, count = struct.unpack('<4I', bytes(uc.mem_read(stack, 16)))
        if count > 1024 * 1024:
            raise ValueError('Copy exceeds offline limit')
        if count:
            uc.mem_write(destination, bytes(uc.mem_read(source, count)))
        uc.reg_write(UC_X86_REG_EAX, destination)
        uc.reg_write(UC_X86_REG_ESP, stack + 4)
        uc.reg_write(UC_X86_REG_EIP, ret)

    def _set(self, uc, address, size, user):
        stack = uc.reg_read(UC_X86_REG_ESP)
        ret, destination, value, count = struct.unpack('<4I', bytes(uc.mem_read(stack, 16)))
        if count > 1024 * 1024:
            raise ValueError('Fill exceeds offline limit')
        if count:
            uc.mem_write(destination, bytes([value & 255]) * count)
        uc.reg_write(UC_X86_REG_EAX, destination)
        uc.reg_write(UC_X86_REG_ESP, stack + 4)
        uc.reg_write(UC_X86_REG_EIP, ret)

    def invoke(self, address, this, arguments):
        self.invalid = None
        for reg in [UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_EDX,
                    UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP]:
            self.uc.reg_write(reg, 0)
        self.uc.reg_write(UC_X86_REG_ECX, this)
        self.uc.reg_write(UC_X86_REG_EFLAGS, 2)
        self.uc.reg_write(UC_X86_REG_ESP, self.STACK)
        self.uc.mem_write(self.STACK, struct.pack('<' + 'I' * (len(arguments) + 1),
                                                self.RETURN, *arguments))
        try:
            self.uc.emu_start(address, self.RETURN, timeout=10_000_000, count=2_000_000)
        except Exception as error:
            raise RuntimeError(f'{address:#x}: {error}; invalid={self.invalid}; '
                               f'eip={self.uc.reg_read(UC_X86_REG_EIP):#x}') from error
        if self.uc.reg_read(UC_X86_REG_EIP) != self.RETURN:
            raise ValueError('Offline instruction/time limit reached')
        result = self.uc.reg_read(UC_X86_REG_EAX)
        return result if result < 0x80000000 else result - 0x100000000

    def decode_create(self, body):
        self.uc.mem_write(self.OBJECT, bytes(0x6bc))
        self.uc.mem_write(self.WIRE, body)
        self.uc.mem_write(self.READER, struct.pack('<4I', self.WIRE, 0, len(body), 0))
        result = self.invoke(0xd75350, self.OBJECT, [self.READER, 1])
        return result, self.read32(self.READER + 4), bytes(self.uc.mem_read(self.OBJECT, 0x6bc))

    def pack_record(self, native):
        if len(native) != 0x1597:
            raise ValueError('Wrong native record size')
        return self.pack_type(0xd74580, native)

    def pack_type(self, address, native):
        # The original 0x05FB inventory DTO reserves 397 * 0x144 bytes,
        # although a small inventory still serializes to a tiny wire body.
        # Keep well within OBJECT's 1 MiB separation from READER.
        if not 0 < len(native) <= 262144:
            raise ValueError('Native DTO outside offline bounds')
        self.uc.mem_write(self.OBJECT, native)
        self.uc.mem_write(self.WIRE, bytes(65536))
        self.uc.mem_write(self.READER, struct.pack('<4I', self.WIRE, 0, 65536, 0))
        result = self.invoke(address, self.OBJECT, [self.READER, 1])
        used = self.read32(self.READER + 4)
        return result, bytes(self.uc.mem_read(self.WIRE, used))

    def decode_record(self, wire):
        self.uc.mem_write(self.OBJECT, bytes(0x1597))
        self.uc.mem_write(self.WIRE, wire)
        self.uc.mem_write(self.READER, struct.pack('<4I', self.WIRE, 0, len(wire), 0))
        result = self.invoke(0xd747c0, self.OBJECT, [self.READER, 1])
        return result, self.read32(self.READER + 4), bytes(self.uc.mem_read(self.OBJECT, 0x1597))

    def decode_server(self, message_id, body):
        packet = struct.pack('>IHI', 1, message_id, message_id) + body
        self.uc.mem_write(self.ROOT_OBJECT, bytes(0xf42c4))
        self.uc.mem_write(self.WIRE, packet)
        self.uc.mem_write(self.READER, bytes(16))
        result = self.invoke(0xe194c0, self.ROOT_OBJECT,
                             [self.WIRE, len(packet), self.READER, 2])
        return {'code': result, 'consumed': self.read32(self.READER), 'bytes': len(packet)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    profile = json.loads((ROOT / 'profiles' / 'uid-1-submission.json').read_text(encoding='utf-8'))
    application = base64.b64decode(profile['request_base64'], validate=True)
    body = application[26:]
    codec = NativeCodec()
    result, used, request = codec.decode_create(body)
    report = {'native_create_request': {'code': result, 'consumed': used, 'bytes': len(body)}}
    if result or used != len(body) - 8:
        raise ValueError(f'Unexpected native request decode: {report}')
    name = request[4:132].split(b'\0', 1)[0] + b'\0'
    native = bytearray(0x1597)
    struct.pack_into('<Q', native, 0, 256)
    native[8:12] = request[:4]
    native[12:140] = request[4:132]
    native[0x90:0x5cc] = request[0x84:0x5c0]
    result, record = codec.pack_record(bytes(native))
    check, consumed, decoded = codec.decode_record(record)
    report['actor_record'] = {'pack_code': result, 'decode_code': check,
                              'wire_bytes': len(record), 'consumed': consumed,
                              'native_bytes': len(native), 'roundtrip_equal': decoded == native,
                              'name_bytes': len(name), 'synthetic_actor_uid': 256}
    if result or check or consumed != len(record) or decoded != native:
        raise ValueError(f'Native record roundtrip failed: {report}')
    # Login subtype tail fields, followed by the two DWORD wrapper fields.
    world = struct.pack('>III', 0, 1, 1) + record + bytes(18)
    create = bytes(4) + record + bytes(8)
    enter = struct.pack('>IQIB', 1, 256, 0, 1) + bytes(8)
    for name_on_disk, code, payload in [('world-one.bin', 0x2ef, world),
                                       ('create-success.bin', 0x303, create),
                                       ('enter-game.bin', 0x32b, enter)]:
        check = codec.decode_server(code, payload)
        report[name_on_disk] = {**check, 'sha256': hashlib.sha256(payload).hexdigest()}
        if check['code'] or check['consumed'] != check['bytes']:
            raise ValueError(f'Native full-packet decode failed: {name_on_disk}: {check}')
        (OUT / name_on_disk).write_bytes(payload)
    # Demonstrate why a status/UID-only reply could not decode as a character.
    report['old_status_uid_probe'] = codec.decode_server(0x303, struct.pack('>IQ', 0, 1) + bytes(2048))
    (OUT / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (OUT / 'actor-record.bin').write_bytes(record)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
