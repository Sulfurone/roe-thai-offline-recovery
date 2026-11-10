"""Decode the local death container and every Thai container item variant."""
import json
import sys
from types import SimpleNamespace
from native_codec_probe import NativeCodec, ROOT

sys.path.insert(0,str(ROOT))
from offline_bot_parcels import BotParcels
from test_control_panel import ready_game

codec=NativeCodec()
game=ready_game()
uid=0x1000000001100
parcels=BotParcels(game,SimpleNamespace(actors={uid:{'position':game.player_position}}),
                   SimpleNamespace(brains={uid:SimpleNamespace(equipped=True,magazine=17,reserve=61)}))
packets=parcels.drop(uid)
entity=next(iter(parcels.parcels))
packets.append(parcels.contents(entity))
checks=[]
for message,body in packets:
    result=codec.decode_server(message,body)
    if result['code'] or result['consumed']!=result['bytes']:raise ValueError(result)
    checks.append(dict(message=hex(message),body_bytes=len(body),decode=result))
report=dict(passed=True,checks=checks,limitation='Original DTO decode; model and search UI require live confirmation')
(ROOT/'private/typed-gameplay/bot-parcels-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
