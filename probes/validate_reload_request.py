"""Thai E6A850 -> 128D5C0 reload request and 49D receipt, offline only."""
import json
import struct
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ESP,UC_X86_REG_EIP

c=NativeCodec()
actor,controller,state,fsm,vt=range(0x10900000,0x10905000,0x1000)
def put(p,*v):c.uc.mem_write(p,struct.pack('<'+'I'*len(v),*v))
def done(value=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EAX,value)
    c.uc.reg_write(UC_X86_REG_EIP,c.read32(sp));c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)
def hook(a,fn):c.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:fn(),begin=a,end=a)
captured=[];active_type=2;errors=[]
def send():
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    mid,body,size=struct.unpack('<3I',c.uc.mem_read(sp+4,12))
    captured.append((mid,bytes(c.uc.mem_read(body,size))));done(0,12)
hook(0xea4610,send)
hook(0xf5f9c0,lambda:done(1))  # Selected slot getter boundary.
hook(0x1090f000,lambda:done(active_type));c.external_hooks.add(0x1090f000)
put(actor+0x7c8,controller);put(controller+8,state);put(state+8,fsm);put(fsm,vt);put(vt+0x1c,0x1090f000)
checks=[]
for own,active_type,expected in ((1,2,True),(0,2,False),(1,3,False)):
    put(actor+0x2f8,own);captured.clear()
    c.invoke(0xe6a850,actor,[])
    if bool(captured)!=expected:raise ValueError(('Original reload gate differs',own,active_type,captured))
    if captured and captured!=[(0x49c,struct.pack('<I',1))]:raise ValueError(captured)
    checks.append(dict(own=own,active_type=active_type,sent=bool(captured)))
hook(0x1130200,lambda:done(actor))
def error():
    errors.append(c.read32(c.uc.reg_read(UC_X86_REG_ESP)+4));done()
hook(0x1136ec0,error)
for result in (0,1):
    decoded=c.decode_server(0x49d,struct.pack('>II',1,result))
    if decoded['code'] or decoded['consumed']!=decoded['bytes']:raise ValueError(decoded)
    c.invoke(0x128d5f0,0,[c.ROOT_OBJECT+6])
if errors!=[1]:raise ValueError(('Original receipt errors differ',errors))
report=dict(passed=True,checks=checks,receipt_errors=errors,
    request_caller='12D6667 in the state setup path, following EVENT_PLAYER_START_LOADING',
    limitation='Original gate/sender/receipt; synthetic controller/FSM type/slot getter; no reload animation or original per-gun duration proof')
(ROOT/'private/typed-gameplay/reload-request-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
