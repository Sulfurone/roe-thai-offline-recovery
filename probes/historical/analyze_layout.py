from pathlib import Path
import struct

ref = Path(r'F:\roe\recovery\references\lobby-default-0.bin').read_bytes()
body = ref[10:]
req = Path(r'F:\roe\recovery\logs\latest-create-request.bin').read_bytes()
app = req[42:]
print('thai appearance len', len(app), 'body len', len(body))

scores = []
for off in range(0, 200):
    seg = body[off:off + len(app)]
    if len(seg) < len(app):
        continue
    diffs = [i for i, (x, y) in enumerate(zip(app, seg)) if x != y]
    scores.append((len(diffs), off, diffs[:8]))
for s in sorted(scores)[:5]:
    print('offset', s[1], 'diffs', s[0], 'first', s[2])

# locate other appearances (signature) in body
sig = app[:12]
starts = []
pos = 0
while True:
    i = body.find(sig, pos)
    if i < 0:
        break
    starts.append(i)
    pos = i + 1
print('signature', sig.hex(' '), 'at', starts)

# dump record header region and trailer
print('body[0:70]', body[:70].hex(' '))
print('body[1260:1340]', body[1260:1340].hex(' '))
print('body[-120:]', body[-120:].hex(' '))
print('u32 count guess:', struct.unpack_from('>I', body, 0)[0])
print('u16 at 4:', hex(struct.unpack_from('>H', body, 4)[0]))
print('bytes 4..12:', body[4:12].hex(' '))
