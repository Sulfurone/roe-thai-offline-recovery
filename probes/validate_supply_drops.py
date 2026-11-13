"""Check Thai supply packets and spawn arguments using the local offline codec."""
import json
import struct
import sys

from native_codec_probe import NativeCodec, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EIP, UC_X86_REG_ESP

sys.path.insert(0,str(ROOT))
from test_supply_drops import scenario


def main():
    game,zones,parcels,drops = scenario(
        smoke_profile=(ROOT/'private/typed-gameplay/bot-basic-profile.bin').read_bytes())
    drops.template = (ROOT/'private/typed-gameplay/vehicle-cross-map.bin').read_bytes()
    zones.started = 100
    packets = [packet for now in (220,225,226,232,239) for packet in drops.tick(now)]
    entity = next(iter(parcels.parcels))
    position = game.player_position = parcels.parcels[entity][0]
    packets += [packet for now in (240,241,241.25,306.25) for packet in drops.tick(now)]
    packets += parcels.handle(0xbce,struct.pack('>QQ',entity,game.actor_uid))
    pickup = struct.pack('>IIQBHB3iB',entity,1,game.actor_uid,0,0,1,*position,0)
    packets += parcels.handle(0x3b63,pickup)
    packets += drops.tick(539)[:1]

    codec = NativeCodec()
    codec.uc.mem_map(0,4096)
    factory = []
    smoke = []
    actor, actor_vtable, throws, grenade, node = range(0x10900000,0x10905000,0x1000)
    smoke_name = node+0x100

    def put(address,*values):
        codec.uc.mem_write(address,struct.pack(f'<{len(values)}I',*values))

    def args(count):
        return struct.unpack(f'<{count}I',codec.uc.mem_read(codec.uc.reg_read(UC_X86_REG_ESP)+4,4*count))

    def finish(value=0, cleanup=0):
        stack = codec.uc.reg_read(UC_X86_REG_ESP)
        codec.uc.reg_write(UC_X86_REG_EIP,codec.read32(stack))
        codec.uc.reg_write(UC_X86_REG_EAX,value)
        codec.uc.reg_write(UC_X86_REG_ESP,stack+4+cleanup)

    def hook(address, callback):
        codec.uc.hook_add(UC_HOOK_CODE,lambda *_:callback(),begin=address,end=address)

    put(actor,actor_vtable)
    put(actor+0x8c4,throws)
    put(actor_vtable+4,0xe99730)
    put(throws+0x10,node,node,1)
    put(node,throws+0x10,throws+0x10,grenade)
    put(grenade,actor_vtable+0x400)
    codec.uc.mem_write(grenade+0x740,struct.pack('<f',60.))
    put(actor_vtable+0x400+4,0xe743d0)
    put(actor_vtable+0x400+0xfc,0x5469c0)
    put(grenade+0x768,smoke_name)
    codec.uc.mem_write(smoke_name,b'smoke_bomb\0')
    hook(0x1132390,lambda:finish(actor))
    hook(0x1130210,lambda:finish(actor))
    hook(0x67b4c0,lambda:finish(int(codec.uc.reg_read(UC_X86_REG_ECX)!=0x2edb890),4))

    def release():
        pos,_,_,template,_,serial=args(6)
        smoke.append(('release',template,struct.unpack('<3f',codec.uc.mem_read(pos,12))))
        put(grenade+0x7a0,serial)
        finish(1,24)

    def effect():
        name,pos,*_=args(5)
        label=bytes(codec.uc.mem_read(codec.read32(name),11)).rstrip(b'\0').decode('ascii')
        smoke.append(('effect',label,struct.unpack('<3f',codec.uc.mem_read(pos,12))))
        finish()

    hook(0xe3b100,release)
    hook(0x1ac07e0,effect)
    hook(0x12aa540,lambda:finish(0,12))

    def capture_spawn(uc,address,size,user):
        stack = uc.reg_read(UC_X86_REG_ESP)
        _,_,_,_,config,position_ptr,_,hp,*_ = struct.unpack('<10I',uc.mem_read(stack,40))
        factory.append(dict(config=config,hp=hp,position=struct.unpack('<3f',uc.mem_read(position_ptr,12))))
        uc.reg_write(UC_X86_REG_EIP,codec.RETURN)

    codec.uc.hook_add(UC_HOOK_CODE,capture_spawn,begin=0x10999d0,end=0x10999d0)
    for message,body in packets:
        result = codec.decode_server(message,body)
        if result['code'] or result['consumed']!=result['bytes']:
            raise ValueError(f'Original decoder rejected {message:#x}: {result}')
        if message==0x654b:
            dto = bytes(codec.uc.mem_read(codec.ROOT_OBJECT+10,0x1259))
            codec.uc.mem_write(codec.OBJECT,struct.pack('<I',message)+dto+bytes(64))
            codec.invoke(0x1289610,0,[codec.OBJECT])
        elif message in (0x1006,0x1009):
            codec.invoke({0x1006:0x1287c40,0x1009:0x1287db0}[message],0,[codec.ROOT_OBJECT+6])
    if [row['config'] for row in factory]!=[4,501] or any(row['hp']!=100 for row in factory):
        raise ValueError(f'Unexpected original spawn arguments: {factory}')
    if smoke!=[('release',50002,position),('effect','smoke_bomb',position)]:
        raise ValueError(f'Original smoke callbacks differ: {smoke}')
    print(json.dumps(dict(fully_decoded=[hex(message) for message,_ in packets],factory=factory,smoke=smoke),indent=2))


if __name__=='__main__':
    main()
