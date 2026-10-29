"""Read nonce-bound primary-gun/scope snapshots from the self-read observer.

These fields distinguish a consumed inventory response from a missing model.
Pointers or visibility flags do not establish rendered pixels or working ADS.
"""
import argparse
import json
from pathlib import Path
import struct
import time

from self_position import SAMPLE

HEADER = struct.Struct('<8s32s4I')
ROW = struct.Struct('<21I')
STATUS = ('fields_ready', 'inventory_absent', 'slot_absent', 'read_unavailable', 'layout_differs')


def decode_equipment(raw, token, pid):
    if len(raw) != HEADER.size + 2 * ROW.size:
        raise ValueError('Equipment snapshot size differs')
    magic, actual_token, actual_pid, sequence, count, inventory = HEADER.unpack_from(raw)
    if (magic != b'ROEEQP1\0' or actual_token != token or actual_pid != pid
            or not pid or not sequence or count != 2):
        raise ValueError('Equipment snapshot identity differs')
    rows = []
    for index in range(2):
        (slot, status, item, vtable, low, high, template, owner, model, loaded, capacity, dirty,
         scope, scope_vtable, scope_template, scope_owner, normal, ads, mode,
         normal_flag, ads_flag) = ROW.unpack_from(raw, HEADER.size + index * ROW.size)
        if slot != index + 1 or status >= len(STATUS):
            raise ValueError('Equipment snapshot row differs')
        if status == 0 and (not inventory or not item or not vtable or not (low or high)
                            or loaded > capacity or capacity > 1000 or dirty > 1
                            or scope and (not scope_vtable or mode > 1)
                            or normal_flag > 255 and normal_flag != 0xffffffff
                            or ads_flag > 255 and ads_flag != 0xffffffff):
            raise ValueError('Ready equipment fields differ')
        rows.append(dict(slot=slot, status=STATUS[status], uid=hex((high << 32) | low),
                         template=template, object=hex(item), vtable=hex(vtable),
                         owner=hex(owner), model=hex(model), loaded=loaded, capacity=capacity,
                         dirty=bool(dirty), scope_template=scope_template,
                         scope=hex(scope), scope_vtable=hex(scope_vtable), scope_owner=hex(scope_owner),
                         normal_model=hex(normal), ads_model=hex(ads), ads_mode=bool(mode),
                         normal_model_flag=None if normal_flag == 0xffffffff else normal_flag,
                         ads_model_flag=None if ads_flag == 0xffffffff else ads_flag))
    return dict(pid=pid, sequence=sequence, inventory=hex(inventory), weapons=rows,
                limitation='Self-read inventory/model fields only; not rendered-pixel or successful ADS proof')


def read_equipment(position_path, *, now=None):
    position_path = Path(position_path)
    path = position_path.with_name(position_path.name + '.equipment')
    now = time.time() if now is None else now
    for current, size in ((position_path, SAMPLE.size), (path, HEADER.size + 2 * ROW.size)):
        info = current.stat()
        if info.st_size != size or not -1 <= now - info.st_mtime <= 3:
            raise ValueError('Equipment/position sample stale or wrong size')
    position = SAMPLE.unpack(position_path.read_bytes())
    if position[0] != b'ROEPOS1\0':
        raise ValueError('Position snapshot format differs')
    return decode_equipment(path.read_bytes(), position[1], position[2])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('position_sample', type=Path)
    args = parser.parse_args()
    print(json.dumps(read_equipment(args.position_sample), ensure_ascii=False))
