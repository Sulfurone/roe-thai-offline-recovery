"""Run the original Thai aircraft route integrator in isolated emulation.

Only three local model accessors are stubbed. No live process, input,
operating-system callback, or network interaction is involved.
"""
import json
import struct
from native_codec_probe import NativeCodec,OUT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ESP,UC_X86_REG_EIP

c=NativeCodec()
unit,vtable,controller=0x10800000,0x10801000,0x10802000
position,direction,target=0x10803000,0x10803100,0x10803200
getter,setter,facing=0x10900000,0x10900020,0x10900040
facings=[]

def put(address,fmt,*values):
    c.uc.mem_write(address,struct.pack('<'+fmt,*values))

def stub(uc,address,size,user):
    stack=uc.reg_read(UC_X86_REG_ESP)
    ret=c.read32(stack)
    if address==getter:
        uc.reg_write(UC_X86_REG_EAX,position)
        consumed=0
    elif address==setter:
        uc.mem_write(position,bytes(uc.mem_read(c.read32(stack+4),12)))
        consumed=4
    else:
        facings.append(struct.unpack('<2f',uc.mem_read(c.read32(stack+4),8)))
        consumed=8
    uc.reg_write(UC_X86_REG_ESP,stack+4+consumed)
    uc.reg_write(UC_X86_REG_EIP,ret)

for address in (getter,setter,facing):
    c.external_hooks.add(address)
    c.uc.mem_write(address,b'\xc3')
    c.uc.hook_add(UC_HOOK_CODE,stub,begin=address,end=address)
put(unit+0x10,'I',vtable)
put(controller+0x1c,'I',unit)
for off,address in ((0x6c,getter),(0x68,setter),(0x60,facing)):
    put(vtable+off,'I',address)
put(position,'3f',325800.,271700.,35000.)
put(direction,'3f',0.,1.,0.)
put(target,'3f',325800.,273700.,35000.)
fword=lambda value:struct.unpack('<I',struct.pack('<f',value))[0]
c.invoke(0x130dd50,controller,[position,direction,fword(2000)])
c.invoke(0x130e0e0,controller,[target,direction,fword(2000)])
c.invoke(0x130ddd0,controller,[])
speed=struct.unpack('<f',c.uc.mem_read(controller+0x8c,4))[0]
positions=[]
for _ in range(6):
    c.invoke(0x130e180,controller,[fword(.1)])
    positions.append(struct.unpack('<3f',c.uc.mem_read(position,12)))
if not (positions[0][1]>271700 and abs(positions[-1][1]-273700)<1):
    raise ValueError(f'Original route integrator did not reach target: {positions}')
if any(abs(x-325800)>1 or abs(z-35000)>1 for x,y,z in positions):
    raise ValueError('Unexpected movement outside the horizontal route')
original_positions=positions
c.uc.mem_write(controller,bytes(0x148))
put(controller+0x1c,'I',unit)
put(position,'3f',200.,204800.,75000.)
put(direction,'3f',1.,0.,0.)
put(target,'3f',2200.,204800.,75000.)
c.invoke(0x130dd50,controller,[position,direction,fword(5000)])
c.invoke(0x130e0e0,controller,[target,direction,fword(5000)])
c.invoke(0x130ddd0,controller,[])
cross_positions=[]
for _ in range(6):
    c.invoke(0x130e180,controller,[fword(.1)])
    cross_positions.append(struct.unpack('<3f',c.uc.mem_read(position,12)))
if (abs(cross_positions[-1][0]-2200)>1
        or any(abs(y-204800)>1 or abs(z-75000)>1 for x,y,z in cross_positions)
        or facings[-1]!=(1.,0.)):
    raise ValueError(f'West-east direction and original movement integration disagree: {cross_positions} / {facings}')
stop_position=tuple(cross_positions[-1])
put(target,'3f',*stop_position)
c.invoke(0x130e0e0,controller,[target,direction,fword(0)])
c.invoke(0x130ddd0,controller,[])
c.invoke(0x130e180,controller,[fword(1)])
stopped=struct.unpack('<3f',c.uc.mem_read(position,12))
if any(abs(a-b)>.01 for a,b in zip(stopped,stop_position)):
    raise ValueError(f'Zero-speed endpoint still moves in the original integrator: {stopped}')
result={'original_functions':['0x130DD50','0x130E0E0','0x130DDD0','0x130E180'],
        'accessors_stubbed':True,'isolated_simulation':True,
        'wire_speed_parameter':2000,'native_initial_catchup_speed':speed,
        'step_seconds':.1,'positions':positions,'passed':True,
        'west_east_positions':cross_positions,'native_facing_directions':facings,
        'zero_speed_endpoint_position':stopped,'zero_speed_endpoint_stopped':True,
        'limitation':'Synthetic model accessors; not live rendering or boarding proof'}
(OUT/'aircraft-controller-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
