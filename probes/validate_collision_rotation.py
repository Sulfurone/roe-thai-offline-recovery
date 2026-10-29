"""Check local Euler math against own Thai A32A70; CRT sin/cos are synthetic."""
import json
import math
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EIP,UC_X86_REG_EBP,UC_X86_REG_ESI
sys.path.insert(0,str(ROOT))
from offline_collision import rotate,euler_xyz

c=NativeCodec()
stub,value=0x1090f000,0x1090f020
# Explicit synthetic CRT boundary: replace the input ST0 with supplied
# sin/cos, return to original matrix construction. No OS library executes.
c.uc.mem_write(stub,b'\xdd\xd8\xdd\x05'+struct.pack('<I',value)+b'\xc3')
c.external_hooks.update(range(stub,stub+16))
counts={0x1428fb8:0,0x1428fbe:0}
angles=()
def trig(uc,address,size,user):
    i=counts[address];counts[address]+=1
    number=(math.cos if address==0x1428fb8 else math.sin)(angles[i])
    uc.mem_write(value,struct.pack('<d',number));uc.reg_write(UC_X86_REG_EIP,stub)
for address in counts:c.uc.hook_add(UC_HOOK_CODE,trig,begin=address,end=address)
checks=[]
frame,point,target=0x10910000,0x10911000,0x10912000
matrix=b''
def vector_entry(uc,address,size,user):
    uc.reg_write(UC_X86_REG_EBP,frame);uc.reg_write(UC_X86_REG_ESI,target)
    uc.mem_write(frame-0x30,matrix);uc.mem_write(frame+8,struct.pack('<I',point))
def vector_end(uc,address,size,user):uc.reg_write(UC_X86_REG_EIP,c.RETURN)
c.uc.hook_add(UC_HOOK_CODE,vector_entry,begin=0xa33027,end=0xa33027)
c.uc.hook_add(UC_HOOK_CODE,vector_end,begin=0xa33102,end=0xa33102)
for values in ((0,0,0),(0,0,math.pi/2),(.2,-.4,1),(.15,.7,-2.9)):
    angles=struct.unpack('<3f',struct.pack('<3f',*values))
    counts={address:0 for address in counts}
    c.invoke(0xa32a70,c.OBJECT,[struct.unpack('<I',struct.pack('<f',v))[0] for v in angles])
    actual=struct.unpack('<9f',c.uc.mem_read(c.OBJECT,36))
    columns=[rotate(euler_xyz(angles),p) for p in ((1,0,0),(0,1,0),(0,0,1))]
    expected=[columns[j][i] for i in range(3) for j in range(3)]
    error=max(abs(a-b) for a,b in zip(actual,expected))
    if error>2e-6 or list(counts.values())!=[3,3]:raise ValueError((angles,error,counts))
    matrix=bytes(c.uc.mem_read(c.OBJECT,36))
    vector=(37.,-91.,205.)
    c.uc.mem_write(point,struct.pack('<3f',*vector))
    # Run the original matrix-times-vector arithmetic after its unrelated
    # owner/config lookup. Matrix, point and output buffers are synthetic.
    c.invoke(0xa33027,0,[])
    moved=struct.unpack('<3f',c.uc.mem_read(target+0x30,12))
    expected_point=rotate(euler_xyz(angles),vector)
    point_error=max(abs(a-b) for a,b in zip(moved,expected_point))
    if point_error>5e-5:raise ValueError(('Original point transform differs',angles,moved,expected_point))
    checks.append(dict(angles=angles,max_error=error,point_transform_error=point_error))
report=dict(passed=True,checks=checks,
    limitation='Original matrix helper and bounded A33027 point arithmetic; synthetic CRT, matrix/input/owner dependencies; static-scene loader/rendering remain separate')
(ROOT/'private/typed-gameplay/collision-rotation-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
