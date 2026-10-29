"""Execute original 047D decoder and survivor-number event consumer offline.

String construction, UI lookup/removal and context lookup are synthetic.
No actual HUD, match result, renderer or live connection is executed.
"""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP
sys.path.insert(0,str(ROOT))
from offline_match_status import survivor_number

c=NativeCodec();c.uc.mem_map(0,4096)
context=0x10a00000
events=[];strings=[]

def args(n):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    return struct.unpack('<'+'I'*n,c.uc.mem_read(sp+4,n*4))

def done(value=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EAX,value)
    c.uc.reg_write(UC_X86_REG_EIP,c.read32(sp))
    c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)

def hook(address,fn):c.uc.hook_add(UC_HOOK_CODE,lambda *unused:fn(),begin=address,end=address)

def string():
    address=args(1)[0]
    strings.append(bytes(c.uc.mem_read(address,96)).split(b'\0',1)[0].decode('ascii'))
    done(c.uc.reg_read(UC_X86_REG_ECX),4)

def event():
    _,value=args(2)
    events.append(c.read32(value))
    done()

hook(0x401330,string)
hook(0xd55160,event)
hook(0x12933a0,lambda:done(context))
hook(0xf23610,lambda:done(0))
hook(0xe7b0a0,lambda:done(0,4))
checks=[]
for count in (100,5,2,1,0):
    mid,wire=survivor_number(count)
    decoded=c.decode_server(mid,wire)
    if decoded['code'] or decoded['consumed']!=decoded['bytes']:raise ValueError(decoded)
    native=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,8))
    if native!=struct.pack('<II',count,0):raise ValueError('Original survivor DTO differs')
    c.uc.mem_write(context+0x137c8,b'\0')
    strings.clear();events.clear()
    c.invoke(0x128df00,0,[c.ROOT_OBJECT+6])
    if strings!=['EVENT_SET_SURVIVE_NUMBER'] or events!=[count]:
        raise ValueError(f'Original survivor event differs: {strings}, {events}')
    if c.uc.mem_read(context+0x137c8,1)!=b'\1':raise ValueError('Original survivor context flag differs')
    checks.append(dict(count=count,body_bytes=len(wire),event=events[0]))
short=c.decode_server(0x47d,survivor_number(2)[1][:-1])
if short['code']==0:raise ValueError('Original reader unexpectedly accepted a truncated DWORD')
report=dict(passed=True,message='0x047d',reader='0xdd1610',callback='0x128df00',checks=checks,
    limitation='Original decode and event payload only; synthetic string/UI/context dependencies, no actual HUD, fixed round participant pool, evacuation or match result')
(ROOT/'private/typed-gameplay/survivor-status-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report))
