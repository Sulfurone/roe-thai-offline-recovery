"""Read the observer's four local-bot scene snapshots; never a spawn authority."""
import argparse
import json
import math
from pathlib import Path
import struct
import time

from self_position import SAMPLE

HEADER = struct.Struct('<8s32s7I')
ROW = struct.Struct('<9I3f')
STATUS = {0: 'position_ready', 1: 'scene_unavailable', 2: 'actor_absent',
          3: 'actor_without_position', 4: 'lookup_unavailable', 5: 'actor_removed'}


def decode_peers(raw, token, pid):
    if len(raw) != HEADER.size + 4 * ROW.size:
        raise ValueError('Peer snapshot size differs')
    magic, actual_token, actual_pid, sequence, count, hp_status, current, maximum, death_tag = HEADER.unpack_from(raw)
    if magic != b'ROEPEER2' or actual_token != token or actual_pid != pid or count != 4:
        raise ValueError('Peer snapshot identity differs')
    if hp_status > 4 or hp_status == 0 and (not 0 <= current <= maximum <= 1_000_000 or maximum == 0):
        raise ValueError('Player health snapshot differs')
    rows = []
    for index in range(count):
        low, high, status, actor, vtable, flags, removed, body, interest, *xyz = ROW.unpack_from(
            raw, HEADER.size + index * ROW.size)
        if (low, high) != (0x1100 + index, 0x10000) or status not in STATUS or interest > 2:
            raise ValueError('Peer snapshot row differs')
        if status == 0 and (not actor or removed or not all(math.isfinite(v) and abs(v) < 2_000_000 for v in xyz)):
            raise ValueError('Peer ready position differs')
        rows.append(dict(uid=hex((high << 32) | low), status=STATUS[status],
                         actor=hex(actor), vtable=hex(vtable), flags=hex(flags),
                         removed=bool(removed), body=hex(body),
                         interest=('absent', 'present', 'unavailable')[interest],
                         position=xyz if status == 0 else None))
    return dict(pid=pid, sequence=sequence, peers=rows,
                player_health=dict(status=('ready', 'lookup_unavailable', 'actor_absent',
                                           'property_guard_differs', 'range_differs')[hp_status],
                                   current=current if hp_status == 0 else None,
                                   maximum=maximum if hp_status == 0 else None,
                                   death_tag=hex(death_tag) if hp_status == 0 else None),
                limitation='Scene/position presence is not proof of model rendering or visibility')


def read_peers(position_path, *, now=None):
    position_path = Path(position_path)
    path = position_path.with_name(position_path.name + '.peers')
    now = time.time() if now is None else now
    for current, size in ((position_path, SAMPLE.size), (path, HEADER.size + 4 * ROW.size)):
        info = current.stat()
        if info.st_size != size or not -1 <= now - info.st_mtime <= 3:
            raise ValueError('Peer/position sample is stale or has a different size')
    position = SAMPLE.unpack(position_path.read_bytes())
    if position[0] != b'ROEPOS1\0':
        raise ValueError('Position snapshot format differs')
    return decode_peers(path.read_bytes(), position[1], position[2])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('position_sample', type=Path)
    args = parser.parse_args()
    print(json.dumps(read_peers(args.position_sample), ensure_ascii=False))
