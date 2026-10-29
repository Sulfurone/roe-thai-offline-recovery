"""Execute original slot-based attachment sender and replay its actual writer.

Only manager lookup and map storage are synthetic. Context normalization,
weapon UID getter, original sender and binary writer are original instructions.
No renderer or live game is used.
"""
import json
import struct
import sys
from native_codec_probe import NativeCodec,ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ESP,UC_X86_REG_EIP

sys.path.insert(0,str(ROOT))
from offline_inventory import OfflineInventory,Item

c=NativeCodec();manager,gun,cells=0x10900000,0x10901000,0x10902000
captured=[]


def done(value=0,cleanup=0):
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EAX,value);c.uc.reg_write(UC_X86_REG_EIP,c.read32(sp))
    c.uc.reg_write(UC_X86_REG_ESP,sp+4+cleanup)


def hook(address,fn):c.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:fn(),begin=address,end=address)


def send():
    sp=c.uc.reg_read(UC_X86_REG_ESP)
    mid,body,size=struct.unpack('<3I',c.uc.mem_read(sp+4,12))
    captured.append((mid,bytes(c.uc.mem_read(body,size))));done(0,12)


def lookup():
    keyptr=c.read32(c.uc.reg_read(UC_X86_REG_ESP)+4)
    slot=c.read32(keyptr)
    done(cells+slot*4,4)


hook(0x11302f0,lambda:done(manager));hook(0x793e90,lookup);hook(0xea4610,send)
c.uc.mem_write(0x2952df7,b'\1')
checks=[]
for slot,context_type in ((1,4),(2,5)):
    iv=OfflineInventory();weapon=iv.items.pop((1,1));iv.items[1,slot]=weapon
    iv.weapon_magazines[weapon.uid]=19
    iv.items[2,1]=Item(4,40305,iv.next_uid,1)
    c.uc.mem_write(gun+0x18,struct.pack('<Q',weapon.uid))
    c.uc.mem_write(cells+slot*4,struct.pack('<I',gun))
    for args in ((2,1,context_type,2,1),(context_type,2,2,1,1)):
        captured.clear();c.invoke(0xf625b0,manager,list(args))
        if len(captured)!=1 or captured[0][0]!=0x3e80:raise ValueError('Original sender not reached')
        code,wire=c.pack_type(0xdd6430,captured[0][1])
        if code or len(wire)!=26:raise ValueError('Original attachment writer failed')
        fields=struct.unpack('>BQBHQBHHB',wire)
        expected=((6,0,2,1,weapon.uid,3,2,1,1) if args[0]==2
                  else (6,weapon.uid,3,2,0,2,1,1,1))
        if fields!=expected:raise ValueError(('Unexpected original identity fields',fields))
        replies=iv.handle(wire)
        if [m for m,b in replies]!=[0x3e82,0x3e81]:raise ValueError('Native request rejected')
        if iv.weapon_magazines[weapon.uid]!=19:raise ValueError('Attachment changed loaded rounds')
        checks.append(dict(weapon_slot=slot,source=fields[2],destination=fields[5],source_uid=fields[1]))
    if iv.items[1,slot].parts or iv.items[2,1].template!=40305:raise ValueError('Part did not survive detach')

report=dict(passed=True,checks=checks,limitation='Original slot sender/writer with synthetic manager map; no rendered attachment proof')
(ROOT/'private/typed-gameplay/attachment-sender-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
