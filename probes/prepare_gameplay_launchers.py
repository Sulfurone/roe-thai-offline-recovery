"""Create opt-in diagnostics from the unchanged verified ground launcher."""
from pathlib import Path
import hashlib
import json

root=Path(__file__).resolve().parents[1]
baseline=(root/'start_native_lobby.cmd').read_bytes()
source=baseline.decode('utf-8')
evidence={'baseline_sha256':hashlib.sha256(baseline).hexdigest(),'candidates':{}}
for name,config,vehicle,scene in [
    ('start_gameplay_probe.cmd',101,'vehicle-jeep-candidate.bin',None),
    ('start_glider_probe.cmd',3,'vehicle-glider-candidate.bin','room-scene-glider-altitude.bin'),
    ('start_aircraft_probe.cmd',4,'vehicle-helicopter-candidate.bin','room-scene-glider-altitude.bin')]:
    text=source.replace('Thai offline map prototype. Landing and basic movement verified.',
                        'Thai gameplay diagnostic. Weapons and vehicles remain unverified.')
    text=text.replace('Combat, inventory and pose-specific movement are still incomplete.',
                      'The normal launcher retains the verified ground-walking baseline.')
    text=text.replace('--seconds 43200 --launch',
                      f'--seconds 43200 --launch --gameplay-prototype --gameplay-auto-seat --gameplay-vehicle-config {config}')
    if scene:
        text=text.replace('room-scene-dry-spawn.bin',scene)
    text=text.replace('--push-delay 3.0',
        '--push-delay 3.0 ^\n'
        '  --push-after-player-ready 0x05fb:"%~dp0private\\native-roster\\inventory-m4a1-candidate.bin" ^\n'
        '  --push-after-player-ready 0x04a0:"%~dp0private\\native-roster\\ammo-m4a1-candidate.bin" ^\n'
        f'  --push-after-load-success 0x654b:"%~dp0private\\native-roster\\{vehicle}"')
    (root/name).write_text(text,encoding='utf-8')
    evidence['candidates'][name]={'config':config,'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()}
if (root/'start_native_lobby.cmd').read_bytes()!=baseline:
    raise ValueError('Baseline launcher changed')
(root/'private/native-roster/gameplay-launchers-validation.json').write_text(
    json.dumps(evidence,indent=2),encoding='utf-8')
print(json.dumps(evidence,indent=2))
