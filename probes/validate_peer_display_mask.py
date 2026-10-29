"""Observe original Thai display-mask writes and appearance virtual arguments.

Appearance virtual methods are recording boundaries. No renderer executes and
the booleans are deliberately not renamed 'visible' or 'hidden'.
"""
import json
import struct
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ESP,UC_X86_REG_EIP

c=NativeCodec();actor,vt,ivt,visual,vvt=range(0x10900000,0x10905000,0x1000)
calls=[]


def put(p,*values):c.uc.mem_write(p,struct.pack('<'+'I'*len(values),*values))


def done(value=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EAX,value);c.uc.reg_write(UC_X86_REG_EIP,c.read32(sp))
    c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)


def record(name,count):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    args=list(struct.unpack('<'+'I'*count,c.uc.mem_read(sp+4,count*4)))
    calls.append([name,args]);done(0,count*4)


for address,name,count in ((0x1090f000,'AC',2),(0x1090f010,'1B8',1),(0x1090f020,'A8',1)):
    c.external_hooks.add(address)
    c.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u,name=name,count=count:
        done(1,4) if name=='A8' else record(name,count),begin=address,end=address)
put(actor,vt);put(actor+0x10,ivt);put(actor+0x104,visual);put(visual,vvt)
put(vt+0xf8,0x10f3690);put(ivt+0x154,0x10f27e0)
put(vvt+0xac,0x1090f000);put(vvt+0x1b8,0x1090f010);put(vvt+0xa8,0x1090f020)
checks=[]
for initial,flag,value,expected in ((0xffffffff,2,0,0xfffffffd),(0xfffffffd,2,1,0xffffffff),
                                     (0xfffffffd,2,0,0xfffffffd)):
    put(actor+0x340,initial);calls.clear()
    c.invoke(0x10f3630,actor+0x10,[flag,value])
    actual=c.read32(actor+0x340)
    if actual!=expected:raise ValueError('Original display mask differs')
    expected_calls=[] if initial==expected else [['AC',[int(expected==0xffffffff),0]],['1B8',[1]]]
    if calls!=expected_calls:raise ValueError((actual,calls,expected_calls))
    checks.append(dict(before=hex(initial),bit=flag,value=value,after=hex(actual),appearance_calls=list(calls)))
report=dict(passed=True,checks=checks,limitation='Raw mask and virtual arguments only; recording appearance object, no actual rendering or visibility conclusion')
# Follow the real appearance flag writer/getter and aggregate three-byte gate.
# Stop only at model-update notifications; never execute the renderer.
d=NativeCodec()
d.uc.mem_write(actor,struct.pack('<I',vt));d.uc.mem_write(actor+0x10,struct.pack('<I',ivt))
d.uc.mem_write(actor+0x104,struct.pack('<I',visual));d.uc.mem_write(visual,struct.pack('<I',vvt))
for address,value in ((vt+0xf8,0x10f3690),(ivt+0x154,0x10f27e0),
                       (vvt+0xa8,0xcf1300),(vvt+0xb0,0xcf1330),(vvt+0xac,0xd08bb0),
                       (vvt+0x1c4,0xd0d2b0),(vvt+0x1b8,0x1090f010)):
    d.uc.mem_write(address,struct.pack('<I',value))
d.external_hooks.add(0x1090f010)


def dreturn(cleanup=0):
    sp=d.uc.reg_read(UC_X86_REG_ESP)
    d.uc.reg_write(UC_X86_REG_EIP,d.read32(sp));d.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)


d.uc.hook_add(UC_HOOK_CODE,lambda *args:dreturn(),begin=0xd066b0,end=0xd066b0)
d.uc.hook_add(UC_HOOK_CODE,lambda *args:dreturn(4),begin=0x1090f010,end=0x1090f010)
gates=[]
for profile_byte,mask,set_value,expected in ((1,0xffffffff,0,0),(0,0xfffffffd,1,1)):
    d.uc.mem_write(actor+0x340,struct.pack('<I',mask));d.uc.mem_write(visual+0xc,bytes((1-expected,1,1)))
    d.invoke(0x10f3630,actor+0x10,[2,set_value])
    actual=d.invoke(0xcf1330,visual,[])&255
    if actual!=expected or bytes(d.uc.mem_read(visual+0xc,3))!=bytes((expected,1,1)):
        raise ValueError('Original appearance aggregate gate differs')
    gates.append(dict(profile_106a=profile_byte,appearance_bytes=list(d.uc.mem_read(visual+0xc,3)),aggregate_gate=actual))
report['appearance_gates']=gates
report['limitation']='Original flag setter/getter and aggregate gate execute; model-update notification is synthetic, no renderer/pixels proof'
(ROOT/'private/typed-gameplay/peer-display-mask-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
