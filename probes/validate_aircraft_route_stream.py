"""Exercise full-distance versus bounded aircraft targets in the original controller.

All model accessors are synthetic. This checks movement integration and snap
behavior, not resource loading, rendering, camera or a live client.
"""
import json
import math
import struct
import sys
from native_codec_probe import NativeCodec,ROOT,OUT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ESP,UC_X86_REG_EIP
sys.path.insert(0,str(ROOT))
from offline_gameplay import OfflineGameplay

c=NativeCodec()
unit,vtable,controller=0x10800000,0x10801000,0x10802000
position,direction,target=0x10803000,0x10803100,0x10803200
getter,setter,facing=0x10900000,0x10900020,0x10900040


def put(addr,fmt,*values):c.uc.mem_write(addr,struct.pack('<'+fmt,*values))
def word(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def xyz():return struct.unpack('<3f',bytes(c.uc.mem_read(position,12)))


def stub(uc,address,size,user):
    stack=uc.reg_read(UC_X86_REG_ESP);ret=c.read32(stack)
    if address==getter:
        uc.reg_write(UC_X86_REG_EAX,position);consumed=0
    elif address==setter:
        uc.mem_write(position,bytes(uc.mem_read(c.read32(stack+4),12)));consumed=4
    else:consumed=8
    uc.reg_write(UC_X86_REG_ESP,stack+4+consumed)
    uc.reg_write(UC_X86_REG_EIP,ret)


for address in (getter,setter,facing):
    c.external_hooks.add(address);c.uc.mem_write(address,b'\xc3')
    c.uc.hook_add(UC_HOOK_CODE,stub,begin=address,end=address)
put(unit+0x10,'I',vtable)
for offset,address in ((0x6c,getter),(0x68,setter),(0x60,facing)):put(vtable+offset,'I',address)
threshold=struct.unpack('<f',bytes(c.uc.mem_read(0x25178f0,4)))[0]
if threshold!=8000.:raise ValueError('Unexpected original initial snap threshold')


def initialize():
    c.uc.mem_write(controller,bytes(0x148));put(controller+0x1c,'I',unit)
    put(controller+0x144,'f',threshold)
    put(position,'3f',200,204800,75000);put(direction,'3f',1,0,0)
    c.invoke(0x130dd50,controller,[position,direction,word(5000)])


initialize();put(target,'3f',409400,204800,75000)
c.invoke(0x130e310,controller,[target,direction,word(5000)])
c.invoke(0x130e180,controller,[word(.05)]) # consume queued target
c.invoke(0x130e180,controller,[word(.05)]) # actual movement
old=xyz()
if abs(old[0]-409400)>1:raise ValueError(f'Expected old far target to snap: {old}')

initialize()
game=OfflineGameplay(vehicle_config=4,auto_board=True,opening_airdrop=True,
    aircraft_route_speed=5000,auto_exit_after=81.84,aircraft_route_end=(409400,204800,75000))
game.vehicle_position=(200,204800,75000);game.board(now=100.)
samples=[];previous=xyz();max_step=0.
for frame in range(200):
    now=100.+frame*.05
    for message,body in game.tick(now):
        if message!=0x6563:continue
        target_xyz=struct.unpack_from('>3i',body,8)
        put(target,'3f',*target_xyz)
        c.invoke(0x130e310,controller,[target,direction,word(5000)])
    c.invoke(0x130e180,controller,[word(.05)])
    current=xyz();max_step=max(max_step,math.dist(current,previous));previous=current
    if frame in (0,19,99,199):samples.append(dict(seconds=(frame+1)*.05,position=current))
if not 40000<previous[0]<60000 or max_step>1000:
    raise ValueError(f'Bounded route has unexpected position or jump: {previous}, max_step={max_step}')
report={'passed':True,'old_far_target_first_step':old,'bounded_samples':samples,
        'max_step_cm':max_step,'frame_seconds':.05,'sync_interval_seconds':.25,
        'initial_snap_threshold_cm':threshold,'scope':'Isolated controller; real rendered flight remains unverified'}
(OUT/'aircraft-route-stream-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
