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
from offline_bot_ai import BotAI
from offline_peer_messages import peer_facing


def main():
    codec=NativeCodec()
    uc=codec.uc
    actor,controller,ride,nodes=0x10900000,0x10901000,0x10902000,0x10b00000
    motion=controller+0x80
    timeline=motion+0xc0
    queue=timeline+0xb8
    world,clock=0x10904000,0x10905000
    model,model_vtable=0x10906000,0x10907000
    uid=0x1000000001100
    allocated=[]
    animation={}

    def put(address,value):
        uc.mem_write(address,struct.pack('<I',value))

    uc.mem_map(0,4096)
    for address,value in ((actor+0x10,0x25a3780),(actor+0x348,controller),
                          (actor+0x7c8,ride),(actor+0x2f8,0x402),
                          (controller,0x261e788),(controller+8,actor),
                          (motion,0x261e978),(motion+0x1b8,actor),(motion+0x1bc,controller),
                          (timeline,motion),(queue,queue),(queue+4,queue),
                          (actor+0x104,model),(model,model_vtable),(model_vtable+0x1e8,0xbae420),
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
            if codec.read32(sp+4)!=0xa0 or len(allocated)>=256:
                raise ValueError('Unexpected allocation at native queue')
            result=nodes+len(allocated)*0x100
            allocated.append(result)
        elif address==0xbae420:
            prop,value,size=struct.unpack('<3I',uc.mem_read(sp+4,12))
            if size!=4:raise ValueError('Unexpected model parameter size')
            animation[prop]=struct.unpack('<f',uc.mem_read(value,4))[0]
            pop=12
        elif address in (0xe50e90,0x13820f0,0x12cd690):
            pop=4
        uc.reg_write(UC_X86_REG_EAX,result)
        uc.reg_write(UC_X86_REG_ESP,sp+4+pop)
        uc.reg_write(UC_X86_REG_EIP,ret)

    for address in (0x1130210,0x1130320,0x65ae50,0x65ae90,0xbae420,0xe50e90,0x13820f0,
                    0xe51750,0x12d0130,0x12d1340,0x12cdce0,0x1333730,0x12cd690):
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
    if codec.read32(allocated[1]+8+0x60)-codec.read32(first+0x60)!=50:
        raise ValueError('Keyframes have no 50 ms playback interval when world tick duration is zero')
    facing=struct.unpack('<3f',uc.mem_read(first+0x48,12))
    expected=(math.cos(heading),math.sin(heading),0)
    if math.dist(facing,expected)>.001:
        raise ValueError(f'Wrong decoded facing: {facing}')
    uc.mem_write(timeline+4,struct.pack('<f',.825))
    codec.invoke(0x1335b50,timeline,[])
    if (abs(animation.get(0x28,0)-220)>.01 or animation.get(0x29)!=0
            or abs(animation.get(0x59,0)-220)>.01 or uc.mem_read(controller+0x5c,1)[0]!=1):
        raise ValueError(f'Wrong model parameters after interpolation: {animation}')
    walking_parameters=animation.copy()

    deliver(0x12783c0,*peer_motion(uid,end,17))
    if uc.mem_read(allocated[-1]+8+0x89,1)[0]!=1:
        raise ValueError('Position-only update did not set the queue reset flag')
    deliver(0x1278350,*peer_locomotion(uid,end,end,18,0,heading))
    stop=allocated[-1]+8
    codec.invoke(0x12d01e0,motion,[stop])
    if any(animation.get(prop)!=0 for prop in (0x28,0x29,0x59)) or uc.mem_read(controller+0x5c,1)[0]!=0:
        raise ValueError(f'Wrong idle animation parameters: {animation}')
    idle_parameters=animation.copy()

    turned=[]

    def rotation(uc,*_):
        vector=codec.read32(uc.reg_read(UC_X86_REG_ESP)+4)
        turned.append(struct.unpack('<3f',uc.mem_read(vector,12)))
        uc.reg_write(UC_X86_REG_EIP,codec.RETURN)

    uc.hook_add(UC_HOOK_CODE,dependency,begin=0x10f37b0,end=0x10f37b0)
    uc.hook_add(UC_HOOK_CODE,rotation,begin=0x12b1d30,end=0x12b1d30)
    deliver(0x1278400,*peer_facing(uid,-math.pi/2,.6))
    if len(turned)!=1 or math.dist(turned[0],(0,-.8,.6))>.001:
        raise ValueError(f'Original turn direction differs: {turned}')

    # The live offline match reported zero for the world's tick duration.
    # Advance the real queue at 60 FPS with a 20 Hz stream under that clock.
    put(clock+0x74,0)
    movement,movement_vtable=0x10908000,0x10909000
    put(motion+0x1cc,movement)
    put(movement,movement_vtable)
    put(movement_vtable+0x24,0x12cd690)
    frame_time=struct.unpack('<I',struct.pack('<f',1/60))[0]
    startup_frames=30  # Allow the native queue to establish its playback buffer.
    steady_frames={}
    for speed in (BotAI.WALK_SPEED,BotAI.RUN_SPEED):
        codec.invoke(0x13353c0,timeline,[])
        put(timeline,motion)
        frames=0
        step=round(speed/20)
        for index in range(40):
            x=start[0]+index*step
            deliver(0x1278350,*peer_locomotion(uid,(x,start[1],start[2]),
                                              (x+step,start[1],start[2]),index+2,speed,0))
            for _ in range(3):
                codec.invoke(0x13358d0,timeline,[])
                codec.invoke(0x1335e40,timeline,[frame_time])
                forward=struct.unpack('<f',uc.mem_read(motion+0x1f8,4))[0]
                if frames>=startup_frames and abs(forward-speed)>.01:
                    raise ValueError(f'Movement input {speed} dropped at frame {frames}: {forward}')
                frames+=1
        steady_frames[speed]=frames-startup_frames
    report=dict(passed=True,waypoints=points,facing=facing,stationary_aim_facing=turned[0],walking_parameters=walking_parameters,
                idle_parameters=idle_parameters,zero_clock_steady_walking_frames=steady_frames[BotAI.WALK_SPEED],
                zero_clock_steady_running_frames=steady_frames[BotAI.RUN_SPEED],running_speed=BotAI.RUN_SPEED,
                position_only_queue_reset=True,
                limitation='Synthetic peer lookup, timeline, allocator, property cache and model interface; no live renderer')
    (ROOT/'private/typed-gameplay/peer-locomotion-validation.json').write_text(
        json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report))


if __name__=='__main__':
    main()
