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
VISUAL_HEADER=struct.Struct('<8s32s3I')
VISUAL_ROW=struct.Struct('<10I')
VISUAL_MODEL_ROW=struct.Struct('<13I')
VISUAL_LOADER_ROW=struct.Struct('<15I')
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


def decode_visuals(raw,token,pid):
    if len(raw)<VISUAL_HEADER.size:raise ValueError('Visual snapshot size differs')
    magic,actual_token,actual_pid,sequence,count=VISUAL_HEADER.unpack_from(raw)
    row_type={b'ROEVIS2\0':VISUAL_ROW,b'ROEVIS3\0':VISUAL_MODEL_ROW,b'ROEVIS4\0':VISUAL_LOADER_ROW}.get(magic)
    if (row_type is None or actual_token!=token or actual_pid!=pid or count!=5):
        raise ValueError('Visual snapshot identity differs')
    if len(raw)!=VISUAL_HEADER.size+5*row_type.size:raise ValueError('Visual snapshot size differs')
    rows=[]
    for index in range(count):
        fields=row_type.unpack_from(raw,VISUAL_HEADER.size+index*row_type.size)
        low,high,status,actor,mask,visual,vtable,secondary,gates,nested=fields[:10]
        if len(fields)>10 and status==0 and (fields[12]>255 or fields[11] and not fields[10]):
            raise ValueError('Visual snapshot model fields differ')
        if (low,high)!=(0x10ff+index if index else 0x100,0x10000) or status not in (0,1,2):
            raise ValueError('Visual snapshot row differs')
        if status==0 and (not actor or secondary>255 or gates>0xffffff or visual and not vtable):
            raise ValueError('Visual snapshot ready fields differ')
        rows.append(dict(uid=hex((high<<32)|low),status=('fields_ready','actor_absent','read_unavailable')[status],
                         actor=hex(actor),display_mask=hex(mask) if status==0 else None,
                         visual=hex(visual),visual_vtable=hex(vtable),
                         secondary_gate=secondary if status==0 else None,
                         appearance_gates=[(gates>>(i*8))&255 for i in range(3)] if status==0 and visual else None,
                         nested=hex(nested)))
        if len(fields)>10:
            rows[-1].update(model_wrapper=hex(fields[10]),render_model=hex(fields[11]),
                            model_gate=fields[12] if status==0 and visual else None)
        if len(fields)>13:
            if status==0 and fields[13]>255:raise ValueError('Visual snapshot loader fields differ')
            rows[-1].update(loader_ready=fields[13] if status==0 and visual else None,
                            loader_stage=fields[14] if status==0 and visual else None)
    return dict(pid=pid,sequence=sequence,actors=rows,
                limitation='Appearance object and raw display mask do not prove rendered model, pixels or visibility')


def read_visuals(position_path,*,now=None):
    position_path=Path(position_path);path=position_path.with_name(position_path.name+'.visuals')
    now=time.time() if now is None else now
    for current,sizes in ((position_path,(SAMPLE.size,)),(path,tuple(VISUAL_HEADER.size+5*r.size for r in (VISUAL_ROW,VISUAL_MODEL_ROW,VISUAL_LOADER_ROW)))):
        info=current.stat()
        if info.st_size not in sizes or not -1<=now-info.st_mtime<=3:raise ValueError('Visual/position sample stale or wrong size')
    position=SAMPLE.unpack(position_path.read_bytes())
    if position[0]!=b'ROEPOS1\0':raise ValueError('Position format differs')
    return decode_visuals(path.read_bytes(),position[1],position[2])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('position_sample', type=Path)
    parser.add_argument('--visuals',action='store_true')
    args = parser.parse_args()
    print(json.dumps((read_visuals if args.visuals else read_peers)(args.position_sample), ensure_ascii=False))
