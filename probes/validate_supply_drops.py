"""Check Thai supply packets and spawn arguments using the local offline codec."""
import json
import struct
import sys

from native_codec_probe import NativeCodec, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP

sys.path.insert(0,str(ROOT))
from test_supply_drops import scenario


def main():
    game,zones,parcels,drops = scenario()
    drops.template = (ROOT/'private/typed-gameplay/vehicle-cross-map.bin').read_bytes()
    zones.started = 100
    packets = [packet for now in (220,225,226,232,239) for packet in drops.tick(now)]
    uid, = drops.landed
    entity = drops.landed[uid].parcel
    position = game.player_position = parcels.parcels[entity][0]
    request = struct.pack('>Q',uid)
    packets += parcels.handle(0x656f,request)
    pickup = struct.pack('>IIQBHB3iB',entity,1,0,0,0,1,*position,0)
    packets += parcels.handle(0x3b63,pickup)
    packets += drops.tick(539)[:1]

    codec = NativeCodec()
    factory = []

    def capture_spawn(uc,address,size,user):
        stack = uc.reg_read(UC_X86_REG_ESP)
        _,_,_,_,config,position_ptr,_,hp,state,_ = struct.unpack('<10I',uc.mem_read(stack,40))
        factory.append(dict(config=config,hp=hp,state=codec.read32(state),position=struct.unpack('<3f',uc.mem_read(position_ptr,12))))
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
    if [row['config'] for row in factory]!=[4,501,501] or any(row['hp']!=100 for row in factory):
        raise ValueError(f'Unexpected original spawn arguments: {factory}')
    if factory[-1]['state']!=1 or factory[-1]['position']!=position:
        raise ValueError(f'Original landed cargo arguments differ: {factory[-1]}')
    print(json.dumps(dict(fully_decoded=[hex(message) for message,_ in packets],factory=factory),indent=2))


if __name__=='__main__':
    main()
