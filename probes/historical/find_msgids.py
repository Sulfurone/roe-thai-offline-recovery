"""Locate message-id immediate constants in a 32-bit PE and disassemble context."""
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32


def main():
    path = sys.argv[1]
    ids = [int(x, 0) for x in sys.argv[2:]]
    pe = pefile.PE(path, fast_load=True)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for section in pe.sections:
        name = section.Name.rstrip(b'\0').decode('latin1')
        data = section.get_data()
        base = pe.OPTIONAL_HEADER.ImageBase + section.VirtualAddress
        for mid in ids:
            needle = mid.to_bytes(4, 'little')
            pos = 0
            while True:
                pos = data.find(needle, pos)
                if pos < 0:
                    break
                # Only report hits inside executable-looking code areas
                start = max(0, pos - 32)
                chunk = data[start:pos + 16]
                addr = base + start
                insns = list(md.disasm(chunk, addr))
                print(f'=== {name} {mid:#x} file_offset={pos:#x} va={base + pos:#x}')
                for insn in insns:
                    marker = '  <<<' if insn.address == base + pos else ''
                    print(f'  {insn.address:#x}: {insn.mnemonic} {insn.op_str}{marker}')
                pos += 1


if __name__ == '__main__':
    main()
