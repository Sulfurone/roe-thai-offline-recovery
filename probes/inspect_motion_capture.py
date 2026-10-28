"""Bounded local motion samples alongside control events; no live input."""
import collections
import json
from pathlib import Path
import struct
import sys

folder = Path(sys.argv[1])
data = (folder / '1-application.bin').read_bytes()
packets = []
cursor = 0
while cursor + 26 <= len(data):
    size, message = struct.unpack_from('>IH', data, cursor)
    if not 26 <= size <= 65536 or cursor + size > len(data):
        break
    packets.append((message, data[cursor + 26:cursor + size]))
    cursor += size
events = [json.loads(line) for line in (folder / 'server.jsonl').read_text(encoding='utf-8').splitlines()]
index, position, vehicle = 0, None, None
window = collections.deque(maxlen=7)
for event in events:
    if event['event'] == 'application_message':
        if index >= len(packets):
            break
        message, body = packets[index]
        index += 1
        if message != event['message_id']:
            raise ValueError('Capture/event order differs')
        if message == 42 and len(body) >= 16:
            position = struct.unpack_from('>3i', body, 4)
            window.append((event['time'], 'actor', position))
        if message == 0x6549 and len(body) >= 25:
            vehicle = (hex(struct.unpack_from('>Q', body)[0]), struct.unpack_from('>3i', body, 13))
        if message in (0x31, 0x6541, 0x6543, 0x6566):
            window.append((event['time'], hex(message), body[:50].hex()))
    elif event['event'] == 'control_command_sent' and event['action'] != 'weather':
        print(json.dumps(dict(time=event['time'], action=event['action'],
                              latest_actor=position, latest_vehicle=vehicle, recent=list(window))))
