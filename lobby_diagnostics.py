"""Read session-bound lobby inventory snapshots from the own-process observer."""
import argparse
import json
from pathlib import Path
import struct
import time
from self_position import SAMPLE

HEADER = struct.Struct('<8s32s6I')
ROW = struct.Struct('<II')
SIZE = HEADER.size + 1024 * ROW.size
OLD_SIZE = HEADER.size + 64 * ROW.size
STATUS = ('fields_ready', 'inventory_absent', 'read_unavailable', 'row_limit', 'list_changed')


def decode_lobby(raw, token, pid):
    if len(raw) not in (SIZE, OLD_SIZE):
        raise ValueError('Lobby inventory snapshot size differs')
    magic, actual_token, actual_pid, sequence, status, actor, inventory, count = HEADER.unpack_from(raw)
    capacity = 1024 if magic == b'ROELOB2\0' and len(raw) == SIZE else 64 if magic == b'ROELOB1\0' and len(raw) == OLD_SIZE else 0
    if (not capacity or actual_token != token or actual_pid != pid or not pid
            or not sequence or status >= len(STATUS) or count > capacity
            or status == 0 and not inventory):
        raise ValueError('Lobby inventory snapshot identity/layout differs')
    items = [dict(template=template, quantity=quantity) for template, quantity in
             (ROW.unpack_from(raw, HEADER.size + i * ROW.size) for i in range(count))]
    return dict(pid=pid, sequence=sequence, status=STATUS[status], actor=hex(actor),
                inventory=hex(inventory), items=items,
                limitation='Self-read inventory list/counts; no clothing asset or visible-pixel proof')


def read_lobby(position_path, *, now=None):
    position_path = Path(position_path)
    lobby_path = position_path.with_name(position_path.name + '.lobby')
    now = time.time() if now is None else now
    for path, size in ((position_path, SAMPLE.size), (lobby_path, SIZE)):
        info = path.stat()
        valid_size = info.st_size == size or path == lobby_path and info.st_size == OLD_SIZE
        if not valid_size or not -1 <= now - info.st_mtime <= 3:
            raise ValueError('Lobby/position sample stale or wrong size')
    position = SAMPLE.unpack(position_path.read_bytes())
    if position[0] != b'ROEPOS1\0':
        raise ValueError('Position sample format differs')
    return decode_lobby(lobby_path.read_bytes(), position[1], position[2])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('position_sample', type=Path)
    args = parser.parse_args()
    print(json.dumps(read_lobby(args.position_sample), ensure_ascii=False))
