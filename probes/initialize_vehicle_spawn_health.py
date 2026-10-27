"""Set original initial HP in local generated vehicle DTOs, then roundtrip.

The 0x1289610 callback passes native +0x90 as current HP to the factory;
0xF35420 clamps it against EuVehicleTable's maximum. Sending zero here
creates zero-health objects before a later 0x6554 update can arrive.
"""
import json
import struct
from native_codec_probe import NativeCodec,ROOT,OUT

codec=NativeCodec()
defaults=json.loads((ROOT/'private/gameplay-catalog/vehicle-defaults.json').read_text(encoding='utf-8'))
health={r['id']:r['initial_hp'] for r in defaults if r['id'] in (3,4,101)}
if health!={3:100,4:100,101:24000}:
    raise ValueError('Unexpected original vehicle initial HP')
sources=[OUT/name for name in ('vehicle-jeep-candidate.bin','vehicle-glider-candidate.bin','vehicle-helicopter-candidate.bin')]
sources += [ROOT/'private/typed-gameplay'/name for name in
    ('vehicle-jeep.bin','vehicle-jeep-near.bin','vehicle-glider.bin','vehicle-helicopter.bin','vehicle-cross-map.bin')]
results=[]
for path in sources:
    decoded=codec.decode_server(0x654b,path.read_bytes())
    if decoded['code'] or decoded['consumed']!=decoded['bytes']:
        raise ValueError('Vehicle fixture did not decode')
    native=bytearray(codec.uc.mem_read(codec.ROOT_OBJECT+10,0x1259))
    config=struct.unpack_from('<I',native,0x88)[0]
    old=struct.unpack_from('<I',native,0x90)[0]
    struct.pack_into('<I',native,0x90,health[config])
    code,body=codec.pack_type(0xe11e50,bytes(native))
    decoded=codec.decode_server(0x654b,body)
    if code or decoded['code'] or decoded['consumed']!=decoded['bytes']:
        raise ValueError('Vehicle HP fixture failed original codec')
    if bytes(codec.uc.mem_read(codec.ROOT_OBJECT+10,len(native)))!=native:
        raise ValueError('Vehicle HP DTO roundtrip differs')
    path.write_bytes(body)
    results.append(dict(fixture=path.name,config=config,old_hp=old,initial_hp=health[config]))
report=dict(passed=True,results=results,
    scope='Original defaults and native codec only; rendered vehicle remains unverified')
(OUT/'vehicle-initial-health.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
