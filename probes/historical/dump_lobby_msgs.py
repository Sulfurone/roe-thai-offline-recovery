from pathlib import Path
import struct

roots = sorted(Path(r'F:\roe\recovery\logs').glob('handshake-20261026-1*'))
for folder in roots[-4:]:
    print('==', folder.name)
    for p in sorted(folder.glob('*-application.bin')):
        data = p.read_bytes()
        pos = 0
        while pos + 6 <= len(data):
            size = struct.unpack_from('>I', data, pos)[0]
            if size < 26 or pos + size > len(data):
                print(' ', p.name, 'unparsed rest', len(data) - pos)
                break
            code = struct.unpack_from('>H', data, pos + 4)[0]
            body = data[pos + 26:pos + size]
            if code not in (0x1F6A,):
                print(' ', p.name, hex(code), 'size', size, 'body', body[:80].hex(' '))
            pos += size
