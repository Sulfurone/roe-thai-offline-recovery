"""Validate Thai unit attributes and exercise the native movement-speed calculator."""
import hashlib
import json
import struct
from native_codec_probe import NativeCodec, OUT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_ESP, UC_X86_REG_EIP

c = NativeCodec()
attrs = bytearray(0x5e8)
matrix = list(struct.unpack('<27I',bytes(c.uc.mem_read(0x28fb4e0,108))))
if any(i>=55 for i in matrix):raise ValueError('Movement attribute indices changed')
# Historical failed full-state test. Do not send this fixture in the launcher.
# The final group has 55 packed records: index and two DWORDs. The
# native calculator reads the second DWORD at 0x3FE + index*9.
# 560 / 560 / 120 are the original local-scene E54330 call's parameters,
# as reproduced by 106FB20. Its table's second/third indices are emitted in
# reverse output order. Pose-specific tuning comes later.
triples = [matrix[i:i+3] for i in range(0,27,3)]
triples += [[30,33,32],[34,38,36],[51,53,52]]
values = {}
for ids in triples:
    for index,value in zip(ids,(560,120,560)):
        if index in values and values[index]!=value:raise ValueError('Conflicting speed index')
        values[index]=value
        struct.pack_into('<BII',attrs,0x3f9+index*9,1,value,value)
code,body = c.pack_type(0xdc5e90,bytes(attrs))
if code:raise ValueError('Native unit-attribute writer failed')
decoded = c.decode_server(0x106a,body)
native = bytes(c.uc.mem_read(c.ROOT_OBJECT+10,len(attrs)))
if decoded['code'] or decoded['consumed']!=decoded['bytes'] or native!=bytes(attrs):
    raise ValueError(f'Unit attribute round trip failed: {decoded}')
code,repacked = c.pack_type(0xdc5e90,native)
if code or repacked!=body:raise ValueError('Unit attribute wire is not canonical')

# Execute the real calculator with synthetic entity/property lookups only.
# No host process, UI, network, allocator, or game callbacks are executed.
entity,vt,props,state,out = 0x10a00000,0x10a02000,0x10a04000,0x10a08000,0x10a10000
c.uc.mem_write(entity+0x10,struct.pack('<I',vt))
c.uc.mem_write(vt+0x54,struct.pack('<I',0xe515a0))
c.uc.mem_write(entity+0x7c8,struct.pack('<I',state))
c.uc.mem_write(props+0x830,bytes(attrs))
def support(uc,address,size,_):
    esp=uc.reg_read(UC_X86_REG_ESP);ret=c.read32(esp)
    if address==0xe515a0:
        value=256;uc.reg_write(UC_X86_REG_EDX,0)
    elif address==0x113e2c0:
        if bytes(uc.mem_read(esp+4,8))!=struct.pack('<Q',256):raise ValueError('Wrong actor lookup')
        value=props
    elif address==0x12ac680:value=0
    else:raise ValueError('Unexpected synthetic support hook')
    uc.reg_write(UC_X86_REG_EAX,value)
    uc.reg_write(UC_X86_REG_ESP,esp+4)
    uc.reg_write(UC_X86_REG_EIP,ret)
for address in (0xe515a0,0x113e2c0,0x12ac680):
    c.uc.hook_add(UC_HOOK_CODE,support,begin=address,end=address)
calculated=[]
for row in range(3):
    for col in range(3):
        c.invoke(0x106fb20,0,[entity,row,col,0,0,out,out+4,out+8])
        result=struct.unpack('<3f',bytes(c.uc.mem_read(out,12)))
        if result!=(560.,560.,120.):raise ValueError(f'Unexpected movement calculation: {result}')
        calculated.append(dict(row=row,col=col,values=result))
(OUT/'unit-attrs-movement.bin').write_bytes(body)
(OUT/'unit-attrs-movement.native.bin').write_bytes(bytes(attrs))
report=dict(message='0x106A',writer='0xDC5E90',reader='0xDC60F0',
            body_bytes=len(body),native_bytes=len(attrs),
            sha256=hashlib.sha256(body).hexdigest(),decode=decoded,
            calculator='0x106FB20',calculated=calculated,
            changed_speed_indices=values,
            status='rejected_live_enters_map_but_cannot_move',
            limitation='Known live regression; remaining zero attributes overwrite existing state. Do not send.')
(OUT/'unit-attrs-movement-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('calculated','changed_speed_indices')},indent=2))
