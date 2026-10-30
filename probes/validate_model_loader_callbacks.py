"""Run original Thai model-loader dispatcher with bounded synthetic resources.

Callback targets are recording stubs; no client process, actual assets or
rendering is touched. Requires the privately supplied original image.
"""
import json
import struct
from native_codec_probe import NativeCodec, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP

c=NativeCodec()
loader,actor,callback,resource=0x10900000,0x10901000,0x10902000,0x10903000
c.external_hooks.add(callback)
c.uc.mem_write(callback,b"\xc3")
seen=[]
def record(uc,address,size,user):
    sp=uc.reg_read(UC_X86_REG_ESP)
    ret,actor_arg,item=struct.unpack("<III",uc.mem_read(sp,12))
    seen.append((actor_arg,item))
    uc.reg_write(UC_X86_REG_EIP,ret)
    uc.reg_write(UC_X86_REG_ESP,sp+4)
c.uc.hook_add(UC_HOOK_CODE,record,begin=callback,end=callback)
def put(addr,value):c.uc.mem_write(addr,struct.pack("<I",value))
def execute(stage,ready,blocked=None,pending=None):
    c.uc.mem_write(loader,bytes(0xa4))
    c.uc.mem_write(actor+0x8ff,bytes([ready]))
    put(loader+0xa0,stage)
    for i in range(10):put(loader+16*i,callback)
    if blocked is not None:c.uc.mem_write(loader+16*blocked+4,b"\x01")
    if pending is not None:
        put(loader+16*pending[0]+pending[1],resource)
        c.uc.mem_write(resource+4,b"\x00")
    seen.clear();c.invoke(0xd00f80,loader,[actor])
    if any(a!=actor or p!=loader+16*i for i,(a,p) in enumerate(seen)) and blocked is None and pending is None:
        raise ValueError("callback arguments differ")
    return [int((p-loader)//16) for a,p in seen]
cases=[]
for name,stage,ready,blocked,pending,expected in (
    ("ready",1,1,None,None,list(range(10))),
    ("stage_zero",0,1,None,None,[]),
    ("stage_done",2,1,None,None,[]),
    ("not_ready",1,0,None,None,[]),
    ("blocked_entry",1,1,3,None,[0,1,2,4,5,6,7,8,9]),
    ("pending_resource",1,1,None,(6,8),[0,1,2,3,4,5,7,8,9]),
    ("pending_second_resource",1,1,None,(8,12),[0,1,2,3,4,5,6,7,9])):
    actual=execute(stage,ready,blocked,pending)
    if actual!=expected:raise ValueError((name,actual,expected))
    cases.append(dict(case=name,callbacks=actual))
report=dict(passed=True,dispatcher="0xd00f80",cases=cases,
    limitation="Synthetic callback stubs; actual asset paths, renderer and pixels not verified")
(ROOT/"private/typed-gameplay/model-loader-callback-validation.json").write_text(
    json.dumps(report,indent=2),encoding="utf8")
print(json.dumps(report))
