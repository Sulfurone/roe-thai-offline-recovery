"""Exercise the Thai peer trajectory decoder, queue and animation inputs."""
import json
import math
import struct
import sys

from native_codec_probe import NativeCodec, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP

sys.path.insert(0,str(ROOT))
from offline_bots import peer_locomotion, peer_motion


def main():
    codec=NativeCodec()
    uc=codec.uc
    actor,controller,ride,nodes=0x10900000,0x10901000,0x10902000,0x10903000
    motion=controller+0x80
    timeline=motion+0xc0
    queue=timeline+0xb8
    world,clock=0x10904000,0x10905000
    uid=0x1000000001100
    allocated=[]
    animation=[]

    def put(address,value):
        uc.mem_write(address,struct.pack('<I',value))

    uc.mem_map(0,4096)
    for address,value in ((actor+0x10,0x25a3780),(actor+0x348,controller),
                          (actor+0x7c8,ride),(actor+0x2f8,0x402),
                          (controller,0x261e788),(controller+8,actor),
                          (motion,0x261e978),(motion+0x1b8,actor),(motion+0x1bc,controller),
                          (timeline,motion),(queue,queue),(queue+4,queue),
                          (0x2eed5b0,world),(world+0xc8,clock),(clock+0x74,50)):
        put(address,value)
    # Stand in for the two CRT x87 imports while leaving the original
    # quantization, normalization and angle conversion instructions intact.
    uc.mem_write(0x1428fb8,b'\xd9\xff\xc3')  # FCOS
    uc.mem_write(0x1428fbe,b'\xd9\xfe\xc3')  # FSIN

    def dependency(uc,address,*_):
        sp=uc.reg_read(UC_X86_REG_ESP)
        ret=codec.read32(sp)
        pop=0
        result=0
        if address in (0x1130210,0x1130320):
            if struct.unpack('<Q',uc.mem_read(sp+4,8))[0]!=uid:
                raise ValueError('Wrong peer UID at actor lookup')
            result=actor
        elif address==0x65ae50:
            if codec.read32(sp+4)!=0xa0 or len(allocated)>=4:
                raise ValueError('Unexpected allocation at native queue')
            result=nodes+len(allocated)*0x100
            allocated.append(result)
        elif address==0x13bf2d0:
            animation.append((struct.unpack('<f',uc.mem_read(sp+4,4))[0],
                              uc.mem_read(codec.read32(sp+8),1)[0]))
            pop=16
        elif address in (0xe50e90,0x12cde90):
            pop=4
        uc.reg_write(UC_X86_REG_EAX,result)
        uc.reg_write(UC_X86_REG_ESP,sp+4+pop)
        uc.reg_write(UC_X86_REG_EIP,ret)

    for address in (0x1130210,0x1130320,0x65ae50,0x13bf2d0,0xe50e90,0x12cde90):
        uc.hook_add(UC_HOOK_CODE,dependency,begin=address,end=address)

    def deliver(handler,message,body):
        result=codec.decode_server(message,body)
        if result['code'] or result['consumed']!=result['bytes']:
            raise ValueError(result)
        dto=bytes(uc.mem_read(codec.ROOT_OBJECT+10,0x116))
        uc.mem_write(codec.OBJECT,struct.pack('<I',message)+dto)
        codec.invoke(handler,0,[codec.OBJECT])

    start,end=(100000,200000,7000),(100006,200010,7000)
    heading=math.pi/3
    deliver(0x1278350,*peer_locomotion(uid,start,end,17,220,heading))
    points=[struct.unpack('<3f',uc.mem_read(node+8,12)) for node in allocated]
    if points!=[start,end] or codec.read32(queue+8)!=2:
        raise ValueError(f'Wrong base or relative keyframe: {points}')
    first=allocated[0]+8
    facing=struct.unpack('<3f',uc.mem_read(first+0x48,12))
    expected=(math.cos(heading),math.sin(heading),0)
    if math.dist(facing,expected)>.001:
        raise ValueError(f'Wrong decoded facing: {facing}')
    uc.mem_write(timeline+4,struct.pack('<f',.825))
    codec.invoke(0x1335b50,timeline,[])
    if not animation or abs(animation[-1][0]-220)>.01 or animation[-1][1]!=1:
        raise ValueError(f'Wrong animation input after interpolation: {animation}')

    deliver(0x12783c0,*peer_motion(uid,end,17))
    if uc.mem_read(allocated[-1]+8+0x89,1)[0]!=1:
        raise ValueError('Position-only update did not set the queue reset flag')
    deliver(0x1278350,*peer_locomotion(uid,end,end,18,0,heading))
    stop=allocated[-1]+8
    codec.invoke(0x12d01e0,motion,[stop])
    # The callback keeps the last facing while idle, but clears the
    # controller input and passes zero speed to the animation sink.
    if animation[-1][0]!=0 or uc.mem_read(controller+0x5c,1)[0]!=0:
        raise ValueError(f'Wrong idle animation input: {animation[-1]}')
    report=dict(passed=True,waypoints=points,facing=facing,animation_inputs=animation,
                position_only_queue_reset=True,
                limitation='Synthetic peer lookup, timeline, allocator and animation sink; no live renderer')
    (ROOT/'private/typed-gameplay/peer-locomotion-validation.json').write_text(
        json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report))


if __name__=='__main__':
    main()
