"""Replay own walking reports through local surveyed-ground population.

Input is private application traffic; no data is bundled or redistributed.
This checks placement relative to reported capsules, not final rendering.
"""
import json
from pathlib import Path
import struct
import sys
from native_codec_probe import ROOT
sys.path.insert(0, str(ROOT))
from offline_gameplay import OfflineGameplay
from control_actions import ControlSession
from offline_population import WorldPopulation
from offline_ground_survey import GroundSurvey

game = OfflineGameplay(inventory_enabled=True, ground_loot_enabled=True)
game.seated = True
control = ControlSession(game, (ROOT/'private/typed-gameplay/vehicle-jeep-near.bin').read_bytes())
population = WorldPopulation(control, GroundSurvey(), 123)
data = Path(sys.argv[1]).read_bytes()
cursor, reports, batches = 0, 0, []
while cursor + 26 <= len(data):
    size, message = struct.unpack_from('>IH', data, cursor)
    if not 26 <= size <= 65536 or cursor + size > len(data):
        break
    body = data[cursor+26:cursor+size]
    if message == 0x6566:
        game.seated = False
    if message == 0x2a:
        game.handle(message, body)
        population.observe(message, body)
        packets = population.tick()
        reports += 1
        if packets:
            if game.player_position[2] >= 50000 or game.seated:
                raise ValueError('Airborne population detected')
            batches.append(dict(reports=reports, messages=len(packets), items=len(game.ground_loot.stacks),
                                cars=len(control.vehicles), position=game.player_position))
    cursor += size
if not batches or not control.vehicles:
    raise ValueError('No surveyed walking ground was populated')
report = dict(reports=reports, batches=batches, surveyed_points=len(population.terrain.points),
              passed=True, scope='Own walking DTO replay; live visuals not established')
(ROOT/'private/typed-gameplay/survey-capture-validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(dict(reports=reports,batches=len(batches),items=len(game.ground_loot.stacks),
                      cars=len(control.vehicles),passed=True)))
