"""Find bounded offline x86 instructions using a specified displacement."""
import argparse
import re
import struct
from native_codec_probe import NativeCodec
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('displacement', type=lambda x:int(x,0))
a = p.parse_args()
c = NativeCodec()
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True
seen = set()
for match in re.finditer(re.escape(struct.pack('<I', a.displacement)), c.image):
    off = match.start()
    for start in range(max(0,off-10), off):
        insn = next(md.disasm(c.image[start:off+12], c.base+start, count=1),None)
        if insn and insn.disp_size == 4 and start+insn.disp_offset == off and insn.address not in seen:
            seen.add(insn.address)
            print(f'{insn.address:#x} {insn.mnemonic} {insn.op_str}')
print('instruction_count',len(seen))
