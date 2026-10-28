"""Own-client map placement plus complete native world-message decoding."""
import json
import math
from pathlib import Path
import random
import struct
import sys
from native_codec_probe import NativeCodec, ROOT
sys.path.insert(0,str(ROOT))
from offline_client_map import ThaiClientMap
from offline_gameplay import OfflineGameplay, TYPED_ACTOR_UID
from offline_population import WorldPopulation
from offline_bots import BotRoster
from control_actions import ControlSession

client_map=ThaiClientMap.from_folder(ROOT/'private/client-map/World_EU_KillZone_2048_RemainingFiles')
game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,actor_uid=TYPED_ACTOR_UID)
game.handle(0x2a,struct.pack('>I3i',1,47562,187323,10691))
control=ControlSession(game,(ROOT/'private/typed-gameplay/vehicle-jeep-near.bin').read_bytes())
bots=BotRoster((ROOT/'private/typed-gameplay/bot-basic-profile.bin').read_bytes())
population=WorldPopulation(control,client_map,123,bots=bots)
packets=population.tick()
codec=NativeCodec()
for message,body in packets:
    result=codec.decode_server(message,body)
    if result['code'] or result['consumed']!=result['bytes']:
        raise ValueError(f'Generated map message {message:#x} is not completely decoded: {result}')
    if message==0xbe7:
        expected=next(iter(bots.actors.values()))['position']
        actual=struct.unpack('<3i',codec.uc.mem_read(codec.ROOT_OBJECT+10+0x48+0x107c,12))
        if actual!=expected:
            raise ValueError('Basic peer profile lost its actual map spawn position')
cars=list(control.vehicles.values())
if len(cars)!=1 or len(bots.actors)!=1:
    raise ValueError('Expected one road Jeep and one outdoor peer candidate')
car=cars[0].vehicle_position
if client_map.is_road(*car[:2]) or not any(client_map.is_road(car[0]+dx,car[1]+dy)
    for dx in range(-600,601,200) for dy in range(-600,601,200)):
    raise ValueError('Car is not beside the road')
auto_stacks=list(game.ground_loot.stacks.values())[1:]
if len(auto_stacks)!=6:
    raise ValueError('Expected three residential weapon/ammo pairs')
if any(not any(abs(stack.position[2]-(round(door[2])+10))<1 and
               50<math.hypot(stack.position[0]-door[0],stack.position[1]-door[1])<350
               for door in client_map.doors) for stack in auto_stacks):
    raise ValueError('Loot is outside the authored entrance-side placement rules')
report=dict(houses=len(client_map.houses),entrances=len(client_map.doors),messages=len(packets),
            player_height_error_cm=client_map.height_at(47562,187323)-10691,
            car=car,peer=next(iter(bots.actors.values()))['position'],passed=True,
            limitation='Private map/DTO checks only; indoor visuals, parking and peer rendering still need live acceptance')
(ROOT/'private/client-map/population-validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
