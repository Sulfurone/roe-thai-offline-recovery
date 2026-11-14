"""Check the Thai kill broadcast and original HUD event without a renderer."""
import struct
import sys

from native_codec_probe import NativeCodec, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EIP, UC_X86_REG_ESP

sys.path.insert(0,str(ROOT))
from offline_match_status import room_kill_broadcast


def main():
    codec=NativeCodec()
    uc=codec.uc
    for name,value in ((b'SHOOT',1),(b'MISSLE',2),(b'SHRINK',3),(b'VEHICLE_HIT_STC',12)):
        label=b'E_POWER_UPDATE_REASON_'+name+b'\0'
        location=codec.base+codec.image.index(label)
        assert struct.pack('<II',location,value) in codec.image
    uc.mem_map(0,4096)
    history,record=0x10900000,0x10901000
    uc.mem_write(0x2f0ae28,struct.pack('<I',history))
    events=[]

    def event_name(uc,*_):
        stack=uc.reg_read(UC_X86_REG_ESP)
        name=codec.read32(stack+4)
        events.append(bytes(uc.mem_read(name,48)).split(b'\0')[0])
        uc.reg_write(UC_X86_REG_EAX,uc.reg_read(UC_X86_REG_ECX))
        uc.reg_write(UC_X86_REG_EIP,codec.read32(stack))
        uc.reg_write(UC_X86_REG_ESP,stack+8)

    # Observe the original Lua event dispatcher, after it has stored the DTO.
    def dispatch(uc,*_):
        events.append('dispatched')
        uc.reg_write(UC_X86_REG_EIP,codec.RETURN)

    uc.hook_add(UC_HOOK_CODE,event_name,begin=0x401330,end=0x401330)
    uc.hook_add(UC_HOOK_CODE,dispatch,begin=0x66e7f0,end=0x66e7f0)
    shooter,victim=0x1000000000100,0x1000000001100
    for weapon,vehicle,reason,headshot in ((10201,0,1,False),(10301,0,1,True),
                                           (50001,0,2,False),(0,0,3,False),(0,101,12,False)):
        killer,killer_name=(shooter,b'RoeTest') if weapon or vehicle else (0,b'')
        message,body=room_kill_broadcast(killer,killer_name,victim,b'AI-1',weapon or vehicle,22,
                                        headshot=headshot,vehicle_impact=bool(vehicle))
        result=codec.decode_server(message,body)
        assert result['code']==0 and result['consumed']==result['bytes'],result
        native=bytes(uc.mem_read(codec.ROOT_OBJECT+10,0x1ad))
        assert struct.unpack_from('<Q',native)[0]==killer
        assert native[8:8+len(killer_name)+1]==killer_name+b'\0'
        assert struct.unpack_from('<Q',native,0x88)[0]==0
        assert struct.unpack_from('<IQ',native,0x110)==(weapon,victim)
        assert native[0x11c:0x121]==b'AI-1\0'
        assert struct.unpack_from('<3I5B',native,0x19c)==(22,vehicle,reason,0,0,0,0,int(headshot))
        assert codec.pack_type(0xdd3390,native)==(0,body)
        uc.mem_write(0,bytes(4))
        uc.mem_write(history,struct.pack('<3I',record,record,record+0x1ad))
        events.clear()
        codec.invoke(0x128e0e0,0,[codec.ROOT_OBJECT+6])
        assert events==[b'EVENT_KILL_HINT_UPDATED','dispatched'],events
        latest=codec.invoke(0x1138400,0,[])
        assert latest==record and bytes(uc.mem_read(latest,0x1ad))==native
        assert codec.decode_server(message,body[:-1])['code']!=0
    print('Thai 0x0480 reader, writer, HUD event and latest-kill data agreed for bullets, frag, circle and vehicle impact.')


if __name__=='__main__':
    main()
