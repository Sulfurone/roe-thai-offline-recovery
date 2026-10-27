"""Find direct relative CALL/JMP references in the private mapped image."""
import argparse
import re
import struct
from native_codec_probe import NativeCodec

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('target',type=lambda x:int(x,0))
a = p.parse_args()
c = NativeCodec()
for m in re.finditer(b'[\xe8\xe9]',c.image):
    off = m.start()
    if off+5 <= len(c.image) and c.base+off+5+struct.unpack_from('<i',c.image,off+1)[0] == a.target:
        print(hex(c.base+off), 'call' if c.image[off] == 0xe8 else 'jmp', hex(a.target))
