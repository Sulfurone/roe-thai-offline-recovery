"""Read-only references to this Thai client's server-time offset field."""
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python-libs'))
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

blob = (ROOT / 'private/runtime-diag-1/thai-self-image.bin').read_bytes()
if blob[:8] != b'ROETHAI1':
    raise ValueError('Expected user-owned ROETHAI1 image')
base, size = struct.unpack_from('<II', blob, 8)
image = blob[16:]
if len(image) != size:
    raise ValueError('Truncated image')
md = Cs(CS_ARCH_X86, CS_MODE_32)
needle = struct.pack('<I', 0xacc4)
cursor = 0
for _ in range(48):
    cursor = image.find(needle, cursor)
    if cursor < 0:
        break
    address = base + cursor
    print(f'offset_reference={address:#x}')
    start = max(0, cursor - 20)
    for instruction in md.disasm(image[start:cursor + 45], base + start):
        print(f' {instruction.address:#x}: {instruction.mnemonic} {instruction.op_str}')
    cursor += 4
