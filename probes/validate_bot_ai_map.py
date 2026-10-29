"""Run the opt-in bot pipeline with own Thai map data and synthetic self samples.

No client is launched. This checks placement and state flow against local
terrain/bounds, not rendering, native collision or original AI/balance.
"""
import json
import math
from collections import Counter
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from offline_client_map import ThaiClientMap
from offline_visibility import StaticVisibility
from offline_bot_ai import BotAI
from offline_population import WorldPopulation
from offline_bots import BotRoster
from control_actions import ControlSession
from offline_gameplay import OfflineGameplay

folder=ROOT/'private/client-map/World_EU_KillZone_2048_RemainingFiles'
terrain=ThaiClientMap.from_folder(folder)
visibility=StaticVisibility.from_scene(terrain,folder/'RIGIDSTATICINPXSCENE.XML')
game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,vitals_enabled=True)
game.actor_ready=True
game.ground_loot.announced=True
game.player_position=(325800,271700,6501)
bots=BotRoster((ROOT/'private/typed-gameplay/bot-basic-profile.bin').read_bytes())
control=ControlSession(game,(ROOT/'private/typed-gameplay/vehicle-jeep-near.bin').read_bytes())
population=WorldPopulation(control,terrain,1,bots=bots,extra_items=True)
ai=BotAI(game,bots,population,visibility)
packets=population.tick()
loot_kinds=Counter(stack.item.kind for entity,stack in game.ground_loot.stacks.items()
                   if entity in population.auto_item_ids)
if not {3,4,5,7,20}<=set(loot_kinds):raise ValueError('Sparse coastal scene starved an equipment category')
if len(bots.actors)!=1:raise ValueError('No dry screened peer at the coastal ground entry')
uid=next(iter(bots.actors))
spawn=bots.actors[uid]['position']
if visibility.walk(spawn,spawn) is None:raise ValueError('Peer overlaps a static bound')


def simulate(controller,point,start):
    shots=hits=0
    for i in range(481):
        now=start+i*.25
        game.accept_self_position(point,now)
        controller.tick(now)
        shots+=sum(e['action']=='bot_fire' for e in controller.events)
        hits+=sum(e['action']=='player_hit' for e in controller.events)
    return dict(seconds=120,shots=shots,hits=hits,player_hp=game.vitals.current)


coastal=simulate(ai,game.player_position,100)
point=bots.actors[uid]['position']
clear_target=None
for distance in (1500,2500,3500):
    for index in range(32):
        angle=math.tau*index/32
        x,y=round(point[0]+distance*math.cos(angle)),round(point[1]+distance*math.sin(angle))
        height=terrain.height_at(x,y)
        if height is None:continue
        target=(x,y,round(height)+5)
        if visibility.walk(target,target) is not None and visibility.clear(
                (*point[:2],point[2]+150),(*target[:2],target[2]+35)):
            clear_target=target;break
    if clear_target is not None:break
if clear_target is None:raise ValueError('No nearby unobstructed dry self sample for AI control')
game.vitals.current=1000
ai=BotAI(game,bots,population,visibility)
exposed=simulate(ai,clear_target,300)
if exposed['shots']!=50 or exposed['hits']!=50 or exposed['player_hp']!=0:
    raise ValueError(f'Bounded AI firing/death control differs: {exposed}')
report=dict(passed=True,static_bounds=len(visibility.bounds),population_messages=len(packets),
    spawn=list(spawn),loot_kinds=dict(loot_kinds),coastal=coastal,exposed=exposed,
    limitation='Own map bounds/terrain with synthetic stationary self samples; no real rendering, mesh collision, original balance or live gameplay proof')
(ROOT/'private/typed-gameplay/bot-ai-map-preflight.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
