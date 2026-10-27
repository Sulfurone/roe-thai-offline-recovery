"""Offline x86 disassembly and bounded reference lookup in our private snapshot."""
from pathlib import Path
import argparse
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python-libs'))
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--start', type=lambda s: int(s, 0))
parser.add_argument('--bytes', type=lambda s: int(s, 0), default=512)
parser.add_argument('--string')
parser.add_argument('--xref', type=lambda s: int(s, 0))
parser.add_argument('--calls', type=lambda s: int(s, 0))
parser.add_argument('--constant', type=lambda s: int(s, 0))
args = parser.parse_args()
blob = (ROOT / 'private' / 'runtime-diag-1' / 'thai-self-image.bin').read_bytes()
base, size = struct.unpack_from('<II', blob, 8)
data = blob[16:]


def function_start(offset):
    lo = max(0, offset - 4096)
    prologue = data.rfind(b'\x55\x8b\xec', lo, offset)
    padding = data.rfind(b'\xcc\xcc\xcc', lo, offset)
    if padding >= 0:
        while padding < offset and data[padding] == 0xcc:
            padding += 1
    return base + max(prologue, padding, lo)


def references(address):
    hits = [match.start() for match in re.finditer(re.escape(struct.pack('<I', address)), data)]
    print(f'address {address:#x}, references {len(hits)}')
    for offset in hits[:80]:
        print(f'  ref {base + offset:#x} provisional_function {function_start(offset):#x}')


if args.string:
    needle = args.string.encode('ascii')
    for match in list(re.finditer(re.escape(needle), data))[:25]:
        address = base + match.start()
        print('string', repr(args.string), hex(address))
        references(address)
if args.xref is not None:
    references(args.xref)
if args.calls is not None:
    hits = []
    for match in re.finditer(b'\xe8', data[:0x18c1000]):
        offset = match.start()
        if offset + 5 <= len(data):
            target = base + offset + 5 + struct.unpack_from('<i', data, offset + 1)[0]
            if target == args.calls:
                hits.append(offset)
    for offset in hits[:100]:
        print(f'call {base + offset:#x} provisional_function {function_start(offset):#x}')
    print('call_count', len(hits))
if args.constant is not None:
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    seen = set()
    for match in re.finditer(re.escape(struct.pack('<I', args.constant)), data[:0x18c1000]):
        offset = match.start()
        for start in range(max(0, offset - 10), offset):
            decoded = list(md.disasm(data[start:offset + 8], base + start, count=1))
            if not decoded:
                continue
            insn = decoded[0]
            if (insn.imm_size == 4 and start + insn.imm_offset == offset
                    and insn.mnemonic in ('push', 'mov', 'cmp', 'sub', 'add', 'and', 'or')
                    and insn.address not in seen):
                seen.add(insn.address)
                print(f'{insn.address:#x} {insn.mnemonic} {insn.op_str} '
                      f'provisional_function {function_start(start):#x}')
if args.start is not None:
    if not base <= args.start < base + size or args.bytes > 16384:
        raise ValueError('Disassembly range out of bounds')
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for insn in md.disasm(data[args.start - base:args.start - base + args.bytes], args.start):
        print(f'{insn.address:08x} {insn.mnemonic:8s} {insn.op_str}')
