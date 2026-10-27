"""Read original EntityTable v1/row38 using EABB60 reflection order.

Only observed compact UTF-8 strings and exact schema are accepted. Entire
row vectors must end at QSSplitTableBase; byte-pattern hits are insufficient.
"""
import hashlib
import json
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FIELDS=[('id','I'),('name','s'),('model_type','I'),('display_name','I'),
    ('model_id','I'),('model_path','s'),('gather_fx_strategy','I'),
    ('gather_fx_path','s'),('gather_fx_scale','f'),('drop_box_quality','I'),
    ('drop_box_state','I'),('block_width','I'),('block_length','I'),
    ('block_type','I'),('collectable','B'),('skill_id','I'),('enable_drop_skill','I'),
    ('mouse_trans','s'),('collect_text','s'),('collect_time','I'),('refresh_times','I'),
    ('refresh_interval','I'),('disappear_time','I'),('max_op_distance','I'),
    ('min_op_distance','I'),('refresh_action','s'),('refresh_anim','s'),
    ('process_anim','s'),('dead_anim','s'),('drop_id','I'),('condition','s'),
    ('pre_action','s'),('post_action','s'),('remark','s'),('next_entity','I'),
    ('show_achievement_effect','B'),('achievement_id','I'),('achievement_req_id','I')]

def extract(path):
    blob=path.read_bytes()
    header=b'\x0bEntityTable'*2
    if not blob.startswith(header):raise ValueError('Wrong table header')
    cursor=len(header)
    def value(fmt):
        nonlocal cursor
        n=struct.calcsize('<'+fmt)
        if cursor+n>len(blob):raise ValueError('Truncated field')
        result=struct.unpack_from('<'+fmt,blob,cursor)[0]
        cursor+=n
        return result
    def string():
        nonlocal cursor
        tag=value('B')
        if not 0xc0<=tag<=0xff:raise ValueError(f'Unsupported string tag {tag:#x} at {cursor-1}')
        n=tag-0xc0
        if cursor+n>len(blob):raise ValueError('Truncated string')
        text=blob[cursor:cursor+n].decode('utf-8')
        cursor+=n
        return text
    if value('H')!=1:raise ValueError('Unknown table version')
    count=value('I')
    if not 0<count<=1024:raise ValueError('Unexpected row count')
    rows=[]
    ids=set()
    for _ in range(count):
        start=cursor
        if value('H')!=len(FIELDS):raise ValueError(f'Unknown row schema at {start}')
        row={name:string() if kind=='s' else value(kind) for name,kind in FIELDS}
        if row['id'] in ids:raise ValueError('Duplicate entity template')
        ids.add(row['id'])
        row.update(start=start,end=cursor)
        rows.append(row)
    if blob[cursor:cursor+17]!=b'\x10QSSplitTableBase':
        raise ValueError(f'Rows do not end at original table footer: {cursor}')
    return dict(source=path.name,source_sha256=hashlib.sha256(blob).hexdigest(),
                reflection='0xEABB60',row_version=len(FIELDS),rows=rows,
                row_count=count,rows_end=cursor)

def main():
    tables=[extract(ROOT/'extracted/tablebin'/name) for name in
            ('731ced6c9309b681.bin','f8812b92f6888786.bin')]
    report={'tables':tables,'supported_loot':[]}
    keys=('id','name','model_path','collectable','max_op_distance','min_op_distance','condition')
    for ident in (10201,30001):
        found=[next(row for row in table['rows'] if row['id']==ident) for table in tables]
        if any({k:r[k] for k in keys}!={k:found[0][k] for k in keys} for r in found):
            raise ValueError('Supported loot configuration differs between original tables')
        if found[0]['collectable']!=1 or found[0]['max_op_distance']!=500 or found[0]['condition']:
            raise ValueError('Supported loot has unexpected interaction gate')
        report['supported_loot'].append({k:found[0][k] for k in keys})
    path=ROOT/'private/gameplay-catalog/ground-entity-defaults.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'tables':[{k:t[k] for k in ('source','row_count','rows_end')} for t in tables],
                      'supported_loot':report['supported_loot']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
