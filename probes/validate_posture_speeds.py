"""Execute Thai sparse update and movement calculator for posture calibration.

Uses the owner's local original image/baseline. No renderer or live process.
"""
import json
import struct
import sys
from native_codec_probe import NativeCodec,OUT,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_EDX,UC_X86_REG_ESP,UC_X86_REG_EIP

sys.path.insert(0,str(ROOT))
from offline_posture import posture_speed_delta

c=NativeCodec()
for address,pointer,value in ((0x107f145,0x25d1dc4,1),(0x107f18e,0x25d1db4,2)):
    if bytes(c.uc.mem_read(address,7))!=b'\x68'+struct.pack('<I',pointer)+b'\x6a'+bytes([value]):
        raise ValueError('Original posture enum registration changed')

entity,vt,props,state,out=0x10a00000,0x10a02000,0x10a04000,0x10a08000,0x10a10000
c.uc.mem_write(props,bytes((i*37+13)%256 for i in range(0x3000)))

def decode_update(body):
    decoded=c.decode_server(0x516,body)
    if decoded['code'] or decoded['consumed']!=decoded['bytes']:
        raise ValueError(f'Incomplete original posture delta: {decoded}')
    native=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,497))
    code,repacked=c.pack_type(0xdc6580,native)
    if code or repacked!=body:
        raise ValueError('Original sparse writer does not reproduce the posture update')
    c.uc.mem_write(c.OBJECT,native)
    c.invoke(0x12d6f10,props,[c.OBJECT])
    return native,decoded

decode_update((OUT/'movement-grounded-delta.bin').read_bytes())
before=bytes(c.uc.mem_read(props,0x3000))
native,decoded=decode_update(posture_speed_delta())
after=bytes(c.uc.mem_read(props,0x3000))
expected=bytearray(before)
struct.pack_into('<I',expected,4,(struct.unpack_from('<I',before,4)[0]+1)&0xffffffff)
for ordinal in range(struct.unpack_from('<H',native)[0]):
    index= native[2+ordinal*9]
    expected[0xc29+index*9:0xc29+(index+1)*9]=native[2+ordinal*9:2+(ordinal+1)*9]
if after!=expected:
    raise ValueError('Posture update modified unrelated property bytes')
if struct.unpack_from('<I',after,0xc29+46*9+5)[0]!=6000:
    raise ValueError('Posture tuning changed the proven downward limit')

c.uc.mem_write(entity+0x10,struct.pack('<I',vt))
c.uc.mem_write(vt+0x54,struct.pack('<I',0xe515a0))
c.uc.mem_write(entity+0x7c8,struct.pack('<I',state))
state_active=False

def support(uc,address,size,user):
    esp=uc.reg_read(UC_X86_REG_ESP)
    if address==0xe515a0:
        value=256;uc.reg_write(UC_X86_REG_EDX,0)
    elif address==0x113e2c0:value=props
    elif address==0x12ac680:value=int(state_active)
    else:raise ValueError('Unexpected synthetic dependency')
    uc.reg_write(UC_X86_REG_EAX,value)
    uc.reg_write(UC_X86_REG_EIP,c.read32(esp))
    uc.reg_write(UC_X86_REG_ESP,esp+4)

for address in (0xe515a0,0x113e2c0,0x12ac680):
    c.uc.hook_add(UC_HOOK_CODE,support,begin=address,end=address)
results=[]
for row in range(3):
    for mode in range(3):
        c.invoke(0x106fb20,0,[entity,row,mode,0,0,out,out+4,out+8])
        result=struct.unpack('<3f',c.uc.mem_read(out,12))
        wanted=((560.,560.,120.),(280.,280.,120.),(120.,120.,120.))[row]
        if result!=wanted:
            raise ValueError(f'Pose {row}, mode {mode}: {result} != {wanted}')
        results.append(dict(posture=row,mode=mode,values=result))
for flag1,flag2,state_active in ((1,0,False),(0,1,False),(0,0,True)):
    c.invoke(0x106fb20,0,[entity,0,0,flag1,flag2,out,out+4,out+8])
    if struct.unpack('<3f',c.uc.mem_read(out,12))!=(560.,560.,120.):
        raise ValueError('Posture patch altered a special movement branch')
report=dict(passed=True,decode=decoded,calculated=results,
            unrelated_property_bytes_preserved=True,fall_limit_preserved=True,
            limitation='Offline calibrated speeds, not recovered server defaults; live crouch/prone acceptance pending')
(OUT/'posture-speed-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
