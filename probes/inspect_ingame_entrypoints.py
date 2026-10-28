"""Bounded read-only string/xref hints for this user's native UI research."""
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python-libs'))
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

blob = (ROOT / 'private/runtime-diag-1/thai-self-image.bin').read_bytes()
if blob[:8] != b'ROETHAI1':
    raise ValueError('Expected a user-owned Thai diagnostic image')
base, size = struct.unpack_from('<II', blob, 8)
image = blob[16:]
if len(image) != size:
    raise ValueError('Truncated image')
md = Cs(CS_ARCH_X86, CS_MODE_32)
terms = sys.argv[1:] or ['OnReportButtonClick', 'Preload.lua', 'ScriptCustom', '_GM_CONTROL_', '/lua', 'QSDir', 'LoadSingleLua']
for term in terms:
    needle = term.encode('ascii')
    cursor = 0
    for _ in range(8):
        offset = image.find(needle, cursor)
        if offset < 0:
            break
        cursor = offset + len(needle)
        address = base + offset
        print(f'{term!r} string={address:#x}')
        reference = struct.pack('<I', address)
        position = 0
        for _ in range(12):
            position = image.find(reference, position)
            if position < 0:
                break
            print(f'  xref={base + position:#x}')
            if position + 16 <= len(image):
                print('    words:', ' '.join(hex(v) for v in struct.unpack_from('<4I', image, position)))
            start = max(0, position - 12)
            for insn in md.disasm(image[start:position + 28], base + start):
                print(f'    {insn.address:#x}: {insn.mnemonic} {insn.op_str}')
            position += 4
