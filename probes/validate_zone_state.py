"""Recover the original Thai 047B circle DTO and consumer field mapping.

Only offline execution of an owner-supplied image. No packet is sent to a
live client. The phase-zero arithmetic slice stops at the UI-facing setter.
"""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_EDI,UC_X86_REG_ESI,UC_X86_REG_EBP,UC_X86_REG_ESP,UC_X86_REG_EIP

c=NativeCodec()
sys.path.insert(0,str(ROOT))
from offline_zones import Circle,zone_state,interpolated_circle
c.uc.mem_map(0,4096)
record,manager=0x10900000,0x10901000
current,target=Circle(200000,190000,150000.),Circle(215000,180000,90000.)
_,wire=zone_state(0,0,120,current,target)
decoded=c.decode_server(0x47b,wire)
if decoded['code'] or decoded['consumed']!=decoded['bytes']:raise ValueError(decoded)
native=bytes(c.uc.mem_read(c.ROOT_OBJECT+10,36))
expected=struct.pack('<IfIiifiif',0,0.,120,200000,190000,150000.,215000,180000,90000.)
if native!=expected:raise ValueError('Original circle layout differs')
code,repacked=c.pack_type(0xdd3210,native)
if code or repacked!=wire:raise ValueError('Original circle writer differs')
c.uc.mem_write(record,native)
c.uc.mem_write(0x2f0aac0,struct.pack('<I',manager))
received=[]
def stop_at_setter(uc,a,s,u):
    sp=uc.reg_read(UC_X86_REG_ESP)
    vector=c.read32(sp+4)
    received.append(struct.unpack('<9f',uc.mem_read(vector,36)))
    uc.emu_stop()
c.uc.hook_add(UC_HOOK_CODE,stop_at_setter,begin=0x13192d0,end=0x13192d0)
c.uc.reg_write(UC_X86_REG_ESI,record)
c.uc.reg_write(UC_X86_REG_EBP,c.STACK-0x1000)
c.uc.reg_write(UC_X86_REG_ESP,c.STACK-0x2000)
c.uc.emu_start(0x128dca3,0x128dd2b,timeout=1000000,count=10000)
if len(received)!=1:raise ValueError('Original phase-zero slice did not reach circle setter')
circles=((200000.,190000.,150000.),(200000.,190000.,150000.),(215000.,180000.,90000.))
if received[0]!=sum(circles,()):raise ValueError(f'Original circle consumer differs: {received}')
phase_zero=received[0]
# Phase two divides the elapsed FLOAT by the total DWORD. Do not interpret
# the latter as an epoch timestamp: that would distort circle interpolation.
blends=[]
for fraction in (0.,.25,.5,1.):
    _,wire=zone_state(2,120*fraction,120,current,target)
    decoded=c.decode_server(0x47b,wire)
    if decoded['code'] or decoded['consumed']!=decoded['bytes']:raise ValueError(decoded)
    c.uc.mem_write(record,bytes(c.uc.mem_read(c.ROOT_OBJECT+10,36)))
    frame=c.STACK-0x1000
    c.uc.mem_write(frame+8,struct.pack('<I',record+8))
    c.uc.mem_write(frame-0x18,struct.pack('<I',record+4))
    c.uc.reg_write(UC_X86_REG_ESI,record)
    c.uc.reg_write(UC_X86_REG_EBP,frame)
    c.uc.reg_write(UC_X86_REG_ESP,c.STACK-0x2000)
    c.uc.reg_write(UC_X86_REG_EDI,0)
    c.uc.emu_start(0x128da34,0x128db85,timeout=1000000,count=10000)
    expected_blend=interpolated_circle(120*fraction,120,current,target)
    if received[-1]!=circles[0]+expected_blend+circles[2]:
        raise ValueError(f'Original shrinking interpolation differs: {fraction}, {received[-1]}')
    blends.append(dict(fraction=fraction,circles=received[-1]))
# Execute original countdown initialization against a synthetic clock source.
# The clock shim only returns an x87 float; 13186A0 performs the state writes.
clock_shim,clock_value=0x10902000,0x10902100
c.uc.mem_write(clock_value,struct.pack('<f',123.5))
c.uc.mem_write(clock_shim,b'\xd9\x05'+struct.pack('<I',clock_value)+b'\xc3')
c.external_hooks.update((clock_shim,clock_shim+6))
def clock(uc,a,s,u):uc.reg_write(UC_X86_REG_EIP,clock_shim)
c.uc.hook_add(UC_HOOK_CODE,clock,begin=0x13185c0,end=0x13185c0)
c.invoke(0x13186a0,manager,[120,struct.unpack('<I',struct.pack('<f',30.))[0]])
remaining=c.read32(manager+0x48)
clock_anchor=struct.unpack('<f',c.uc.mem_read(manager+0x50,4))[0]
if remaining!=90 or clock_anchor!=123.5:raise ValueError('Original countdown initialization differs')
report=dict(passed=True,message='0x047b',body_bytes=len(wire),codec_reader='0xdd32e0',codec_writer='0xdd3210',
    original_phase_zero_circles=phase_zero,original_shrink_interpolation=blends,
    countdown_initialization=dict(total=120,elapsed=30.,remaining=remaining,synthetic_clock_anchor=clock_anchor),
    limitation='Original codec/writer and phase-zero/phase-two arithmetic to setter boundary; no live map rendering, wall-clock timing, damage, helicopter or match outcome')
(ROOT/'private/typed-gameplay/zone-state-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report))
