"""Validate dynamic panel payloads using the user's own Thai native decoder."""
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native_codec_probe import NativeCodec
from control_actions import ControlSession
from offline_gameplay import OfflineGameplay, TYPED_ACTOR_UID


def main():
    game = OfflineGameplay(inventory_enabled=True, ground_loot_enabled=True, actor_uid=TYPED_ACTOR_UID)
    game.handle(0x002a, struct.pack('>I3i', 1, 325800, 271700, 6501))
    session = ControlSession(game, (ROOT / 'private/typed-gameplay/vehicle-jeep-near.bin').read_bytes())
    codec = NativeCodec()
    results = []
    commands = [{'action': 'weather', 'weather_id': 2, 'transition': 30},
                {'action': 'weapon', 'template': 10202, 'count': 2, 'ammo': 120},
                {'action': 'vehicle', 'config': 101}, {'action': 'vehicle', 'config': 101, 'distance': 8}]
    for command in commands:
        packets, _ = session.execute(command)
        for message, body in packets:
            decoded = codec.decode_server(message, body)
            if decoded['code'] != 0 or decoded['consumed'] != len(body) + 10:
                raise ValueError(f'Native panel payload failed: {message:#x}: {decoded}')
            if message == 0x654b:
                native = bytes(codec.uc.mem_read(codec.ROOT_OBJECT + 10, 0xa0))
                uid, = struct.unpack_from('<Q', native)
                config, hp = struct.unpack_from('<I', native, 0x88)[0], struct.unpack_from('<I', native, 0x90)[0]
                position = struct.unpack_from('<3i', native, 0x94)
                if uid not in session.vehicles or config != 101 or hp != 24000 or position != session.vehicles[uid].vehicle_position:
                    raise ValueError('Cloned vehicle native fields differ')
            results.append({'message': hex(message), 'body_bytes': len(body), 'native_decode': 'passed'})
    print(json.dumps({'passed': True, 'packets': results,
                      'scope': 'Native codecs and vehicle DTO fields; game visuals require live validation'}, indent=2))


if __name__ == '__main__':
    main()
