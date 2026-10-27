"""Validate zero/default scene followups used by the native local-scene builder."""
import hashlib
import json
from native_codec_probe import NativeCodec, OUT

c = NativeCodec()
reports = []
# 0x127724D..0x1277294 zeroes these native callback buffers after scene entry.
# Their network codecs consume respectively three DWORDs and one DWORD when
# all variable counts are zero. Confirm exact root parsing before emission.
for message,size,native_size,name in (
    (0x349,12,0x12c10,'scene-followup-default'),
    (0x47a,4,4,'room-prepare-zero'),
):
    body = bytes(size)
    decoded = c.decode_server(message,body)
    if decoded['code'] or decoded['consumed']!=decoded['bytes']:
        raise ValueError(f'Native scene followup parser failed: {decoded}')
    native = bytes(c.uc.mem_read(c.ROOT_OBJECT+10,native_size))
    if any(native):
        raise ValueError('Zero/default scene followup changed native fields')
    (OUT/(name+'.bin')).write_bytes(body)
    reports.append(dict(message=hex(message),body_bytes=size,native_bytes=native_size,
                        sha256=hashlib.sha256(body).hexdigest(),**decoded))
(OUT/'scene-followup-validation.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
print(json.dumps(reports,indent=2))
