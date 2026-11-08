"""Original Thai profile selector consumption on synthetic properties.

Checks world->peer selector preservation; stops at the next configuration
lookup. No resource loader, scene factory or renderer is simulated as working.
"""
import json
import struct
from native_codec_probe import NativeCodec, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_EDX,UC_X86_REG_EIP,UC_X86_REG_ESP,UC_X86_REG_EDI,UC_X86_REG_ESI,UC_X86_REG_EBX

c=NativeCodec();c.uc.mem_map(0,4096)
props=0x10900000
c.uc.mem_write(0x2eedb58,struct.pack('<I',0x10903000))

def done(value=0,high=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EAX,value);c.uc.reg_write(UC_X86_REG_EDX,high)
    c.uc.reg_write(UC_X86_REG_EIP,c.read32(sp));c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)

def hook(a,fn):c.uc.hook_add(UC_HOOK_CODE,lambda *_:fn(),begin=a,end=a)
hook(0x113e310,lambda:done(props))
hook(0x1130670,lambda:done(0x100,0x10000))
hook(0x401330,lambda:done(0,cleanup=4))
hook(0x409120,lambda:done(1))
# Deliberately stop before table lookup/resource construction.
hook(0xcd99d0,lambda:c.uc.reg_write(UC_X86_REG_EIP,c.RETURN))
folder=ROOT/'private/typed-gameplay'
world=c.decode_server(0x2ef,(folder/'world.bin').read_bytes())
if world['code'] or world['consumed']!=world['bytes']:raise ValueError(world)
selector=c.read32(c.ROOT_OBJECT+10+0x98)
variant=c.read32(c.ROOT_OBJECT+22+0x5c8)
body=(folder/'bot-basic-profile-selector.bin').read_bytes()
result=c.decode_server(0xbe7,body)
if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
basic=bytearray(c.uc.mem_read(c.ROOT_OBJECT+10+0x48,0x4b74))
if struct.unpack_from('<I',basic,0x80)[0]!=selector or basic[0xb0]!=variant:
    raise ValueError('Candidate loses world selectors')
rows=[]
for value in (0,selector,127,255):
    struct.pack_into('<I',basic,0x80,value)
    c.uc.mem_write(c.OBJECT,bytes(basic));c.uc.mem_write(props,bytes(0x2500))
    c.invoke(0x127bd70,0,[0x1100,0x10000,0,c.OBJECT,0])
    actual=(c.uc.mem_read(props+0x160,1)[0]+0x25)&255
    expected=value
    if actual!=expected:raise ValueError((value,actual,expected))
    if (c.read32(props+0x164)^0xa59cf5b6)!=variant:raise ValueError('Variant differs')
    rows.append(dict(wire_selector=value,property_selector=actual))
# Execute the self-record consumer's exact property slice, with the same
# selector; no engine dependency is reached in this six-instruction slice.
self_record=0x10905000
c.uc.mem_write(self_record+0x8c,struct.pack('<I',selector))
c.uc.reg_write(UC_X86_REG_EDI,self_record);c.uc.reg_write(UC_X86_REG_ESI,props)
c.uc.reg_write(UC_X86_REG_EBX,1)
c.uc.emu_start(0x127c3e3,0x127c3f4,count=20)
if (c.uc.mem_read(props+0x160,1)[0]+0x25)&255!=selector:
    raise ValueError('Original own selector consumer differs')
report=dict(passed=True,source_selector=selector,checks=rows,
            limitation='Original property consumer only; actual resource selection and model rendering pending')
(folder/'peer-avatar-selector-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
