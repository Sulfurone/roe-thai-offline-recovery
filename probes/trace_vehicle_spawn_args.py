"""Trace Thai vehicle factory arguments using only decoded local fixtures.

The factory is intercepted before it executes; this checks the real 0x654B
callback arguments, not asset creation, rendering, or a running process.
"""
import json
import struct
from native_codec_probe import NativeCodec, ROOT, OUT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP

codec=NativeCodec()
captured=[]


def trace(uc,address,size,user):
    stack=uc.reg_read(UC_X86_REG_ESP)
    captured.append(struct.unpack('<10I',uc.mem_read(stack,40)))
    uc.reg_write(UC_X86_REG_EIP,codec.RETURN)


codec.uc.hook_add(UC_HOOK_CODE,trace,begin=0x10999d0,end=0x10999d0)
results=[]
for name,expected in [('vehicle-cross-map.bin',4),('vehicle-glider.bin',3),('vehicle-jeep.bin',101)]:
    path=ROOT/'private/typed-gameplay'/name
    result=codec.decode_server(0x654b,path.read_bytes())
    if result['code'] or result['consumed']!=result['bytes']:
        raise ValueError(f'Original spawn decoder rejected {name}: {result}')
    dto=bytes(codec.uc.mem_read(codec.ROOT_OBJECT+10,0x1259))
    codec.uc.mem_write(codec.OBJECT,struct.pack('<I',0x654b)+dto+bytes(64))
    codec.invoke(0x1289610,0,[codec.OBJECT])
    if len(captured)!=1:raise ValueError('Factory was not reached exactly once')
    args=captured.pop()
    if args[4]!=expected:raise ValueError(f'Unexpected vehicle config: {name}')
    position=struct.unpack('<3f',bytes(codec.uc.mem_read(args[5],12)))
    quaternion=struct.unpack('<4f',bytes(codec.uc.mem_read(args[6],16)))
    if quaternion!=(0.,0.,0.,1.):raise ValueError('Unexpected vehicle orientation')
    results.append(dict(fixture=name,config=args[4],uid=hex(args[1]|args[2]<<32),
                        control_type=args[3],position=position,quaternion=quaternion,
                        trailing_integer=args[7],status_pointer=hex(args[8]),last_flag=args[9]))
report={'callback':'0x1289610','factory':'0x10999D0','results':results,
        'scope':'Original decoded DTO and callback only; factory, asset loading and rendered model not executed'}
(OUT/'vehicle-spawn-arguments.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
