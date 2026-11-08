"""Compare own and remote Thai appearance property consumers offline.

Uses original instruction slices with synthetic context/configuration lookup;
no game process or renderer. Checks the field projection, not asset validity.
"""
import json
import struct
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_EDI,UC_X86_REG_ESI,UC_X86_REG_EBP,UC_X86_REG_ESP,UC_X86_REG_EIP

c=NativeCodec()
record,peer,own_props,peer_props,manager,config=range(0x10900000,0x10906000,0x1000)
frame=0x20110000
fields=(0x2a4,0x2a8,0x2b8,0x2bc,0x2c4,0x2cc,0x2c8,0x2ec)

def put(a,*v):c.uc.mem_write(a,struct.pack('<'+'I'*len(v),*v))
def lookup(*_):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EAX,config)
    c.uc.reg_write(UC_X86_REG_EIP,c.read32(sp));c.uc.reg_write(UC_X86_REG_ESP,sp+8)
c.uc.hook_add(UC_HOOK_CODE,lookup,begin=0xcd99d0,end=0xcd99d0)
put(0x2eedb58,manager)

def consume(source,basic):
    c.uc.mem_write(record,source);c.uc.mem_write(peer,basic)
    c.uc.mem_write(own_props,bytes(0x400));c.uc.mem_write(peer_props,bytes(0x400))
    c.uc.reg_write(UC_X86_REG_EDI,record);c.uc.reg_write(UC_X86_REG_ESI,own_props)
    c.uc.reg_write(UC_X86_REG_EBX,1);c.uc.reg_write(UC_X86_REG_EAX,0xa59cf5b6)
    c.uc.emu_start(0x127c65e,0x127c7c1,count=200)
    c.uc.mem_write(frame-0x100,bytes(0x200))
    c.uc.reg_write(UC_X86_REG_EBP,frame);c.uc.reg_write(UC_X86_REG_ESP,frame-0x80)
    c.uc.reg_write(UC_X86_REG_EDI,1);c.uc.reg_write(UC_X86_REG_ESI,peer);c.uc.reg_write(UC_X86_REG_EBX,peer_props)
    c.uc.emu_start(0x127bf35,0x127c174,count=2000)
    return {hex(o):dict(own=c.read32(own_props+o)^0xa59cf5b6,
                       peer=c.read32(peer_props+o)^0xa59cf5b6) for o in fields}

world=(ROOT/'private/typed-gameplay/world-clothed.bin').read_bytes()
code,used,source=c.decode_record(world[12:-18])
if code or used!=len(world)-30:raise ValueError('Invalid own source record')
result=c.decode_server(0xbe7,(ROOT/'private/typed-gameplay/bot-basic-profile-appearance.bin').read_bytes())
if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
basic=bytes(c.uc.mem_read(c.ROOT_OBJECT+10+0x48,0x4b74))
checks=consume(source,basic)
if any(row['own']!=row['peer'] for row in checks.values()):raise ValueError(checks)
# Distinct sentinels ensure this checks mapping, not coincident zero defaults.
synthetic=bytearray(source)
for i in range(12):struct.pack_into('<I',synthetic,0x8c+4*i,100+i)
candidate=bytearray(basic);candidate[0x80:0xb0]=synthetic[0x8c:0xbc]
sentinels=consume(bytes(synthetic),bytes(candidate))
if any(row['own']!=row['peer'] for row in sentinels.values()):raise ValueError(sentinels)
old=bytearray(candidate);old[0x80:0xb0]=synthetic[0x90:0xc0]
negative=consume(bytes(synthetic),bytes(old))
if not all(row['own']!=row['peer'] for row in negative.values()):raise ValueError('Old shifted copy was not rejected')
report=dict(passed=True,source_properties=checks,sentinel_properties=sentinels,
            old_projection_mismatches=list(negative),
            limitation='Original property slices, synthetic config lookup; no resource or render proof')
(ROOT/'private/typed-gameplay/peer-appearance-projection-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
