"""Validate generated Thai world DTOs and basic peer callback routing offline.

Only own-client codecs/callbacks in bounded emulation; no renderer or live
process access. This does not establish working door animation or combat AI.
"""
import json
import struct
import sys
from native_codec_probe import NativeCodec, ROOT
sys.path.insert(0, str(ROOT))
from control_actions import ControlSession
from offline_gameplay import OfflineGameplay, TYPED_ACTOR_UID
from offline_doors import DoorState
from offline_population import WorldPopulation
from offline_bots import BotRoster
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EAX

codec = NativeCodec()
game = OfflineGameplay(inventory_enabled=True, ground_loot_enabled=True, actor_uid=TYPED_ACTOR_UID)
game.handle(0x2a, struct.pack('>I3i', 1, 135000, 166000, 20250))
control = ControlSession(game, (ROOT/'private/typed-gameplay/vehicle-jeep-near.bin').read_bytes())
class Surface:
    def height_at(self, x, y):
        return 20000
bots = BotRoster((ROOT/'private/typed-gameplay/bot-basic-profile.bin').read_bytes())
population = WorldPopulation(control, Surface(), bots=bots)
packets = population.tick()
packets += DoorState().handle(struct.pack('>II', 17415, 1))
evidence = []
profile_native = None
for message, body in packets:
    result = codec.decode_server(message, body)
    if result['code'] or result['consumed'] != result['bytes']:
        raise ValueError(f'Native world message {message:#x}: {result}')
    if message == 0x6f55:
        if struct.unpack('<3I', codec.uc.mem_read(codec.ROOT_OBJECT+10, 12)) != (17415, 1, 1):
            raise ValueError('Door ID/state/count changed')
    if message == 0xbe7:
        profile_native = bytes(codec.uc.mem_read(codec.ROOT_OBJECT+10, 0x48+0x7c85))
    evidence.append(dict(message=hex(message), **result))

created = []
runtime_received = []
def factory(uc, address, size, _):
    stack = uc.reg_read(UC_X86_REG_ESP)
    ret, low, high, info = struct.unpack('<4I', uc.mem_read(stack, 16))
    created.append(dict(uid=hex(low | high << 32), name=bytes(uc.mem_read(info, 128)).split(b'\0')[0].decode(),
                        position=tuple(struct.unpack('<3i',uc.mem_read(info+0x107c,12)))))
    uc.reg_write(UC_X86_REG_EAX, 0)
    uc.reg_write(UC_X86_REG_ESP, stack + 4)
    uc.reg_write(UC_X86_REG_EIP, ret)
codec.uc.hook_add(UC_HOOK_CODE, factory, begin=0x1281f30, end=0x1281f30)
def runtime(uc,address,size,_):
    stack=uc.reg_read(UC_X86_REG_ESP)
    ret,low,high,info=struct.unpack('<4I',uc.mem_read(stack,16))
    runtime_received.append(hex(low|high<<32))
    uc.reg_write(UC_X86_REG_EAX,0)
    uc.reg_write(UC_X86_REG_ESP,stack+4)
    uc.reg_write(UC_X86_REG_EIP,ret)
codec.uc.hook_add(UC_HOOK_CODE,runtime,begin=0x1284c90,end=0x1284c90)
codec.uc.mem_write(codec.OBJECT, struct.pack('<I', 0xbe7) + profile_native)
codec.invoke(0x1285290, 0, [codec.OBJECT])
if created != [dict(uid=hex(TYPED_ACTOR_UID+0x1000), name='OfflineBot1',position=next(iter(bots.actors.values()))['position'])]:
    raise ValueError('Native basic-profile callback did not forward the intended peer')
if runtime_received != [hex(TYPED_ACTOR_UID+0x1000)]:
    raise ValueError('Full peer data did not reach the runtime-state callback')
report = dict(messages=evidence, peer_callback=created,
              limitation='Codec and basic factory routing only; door visuals, peer rendering/navigation/combat unverified')
(ROOT/'private/typed-gameplay/world-population-validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(dict(messages=len(evidence),peer_callback=created,passed=True)))
