"""Check local Euler math against own Thai A32A70; CRT sin/cos are synthetic."""
import json
import math
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EIP
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
for values in ((0,0,0),(0,0,math.pi/2),(.2,-.4,1),(.15,.7,-2.9)):
    angles=struct.unpack('<3f',struct.pack('<3f',*values))
    counts={address:0 for address in counts}
    c.invoke(0xa32a70,c.OBJECT,[struct.unpack('<I',struct.pack('<f',v))[0] for v in angles])
    actual=struct.unpack('<9f',c.uc.mem_read(c.OBJECT,36))
    columns=[rotate(euler_xyz(angles),p) for p in ((1,0,0),(0,1,0),(0,0,1))]
    expected=[columns[j][i] for i in range(3) for j in range(3)]
    error=max(abs(a-b) for a,b in zip(actual,expected))
    if error>2e-6 or list(counts.values())!=[3,3]:raise ValueError((angles,error,counts))
    checks.append(dict(angles=angles,max_error=error))
report=dict(passed=True,checks=checks,
    limitation='Original matrix helper, synthetic CRT; static-scene placement/rendering is a separate validation')
(ROOT/'private/typed-gameplay/collision-rotation-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
