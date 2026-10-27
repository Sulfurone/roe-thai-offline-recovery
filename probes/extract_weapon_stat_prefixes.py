"""Extract bounded original WeaponInfo/WeaponParams prefixes.

This is deliberately a prefix catalogue, not a full QSWeaponConfigTable
decoder. Candidate root records must match the declared count, be unique,
start at the original first-row boundary and join complete ItemTable and
EntityTable rows. Nested recoil/FX/avatar rows remain unparsed.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from extract_original_item_defaults import extract as extract_items
from extract_ground_entity_defaults import extract as extract_entities

ROOT=Path(__file__).resolve().parents[1]
PREFIX=struct.Struct('<IfBBII5fHII fIfI'.replace(' ',''))

def main():
    source=ROOT/'extracted/tablebin/231f78952b1944f4.bin'
    blob=source.read_bytes()
    if blob[:40]!=b'\x13QSWeaponConfigTable'*2 or struct.unpack_from('<H',blob,40)[0]!=14:
        raise ValueError('Unknown original weapon table')
    count=struct.unpack_from('<I',blob,74)[0]
    if count!=24:raise ValueError('Unknown declared weapon-vector count')
    candidates=[]
    for match in re.finditer(b'\x1d\x00',blob):
        offset=match.start()
        if offset+7+PREFIX.size>len(blob):continue
        ident=struct.unpack_from('<I',blob,offset+2)[0]
        length=blob[offset+6]-0xc0
        if not 0<length<=63 or offset+7+length+PREFIX.size>len(blob):continue
        try:name=blob[offset+7:offset+7+length].decode('utf-8')
        except UnicodeDecodeError:continue
        values=PREFIX.unpack_from(blob,offset+7+length)
        if values[11]!=121:continue
        if not (0<ident<1000000 and values[2] in (0,1) and values[3] in (0,1)
                and all(math.isfinite(x) for x in values if type(x) is float)):
            raise ValueError('Invalid original weapon-prefix candidate')
        candidates.append(dict(offset=offset,id=ident,name=name,weapon_version=29,params_version=121,
            base_damage=values[0],base_range=values[1],max_ammo=values[12],rpm=values[13],
            range=values[14],damage=values[15],muzzle_velocity=values[16],hit_type=values[17]))
    if (len(candidates)!=count or candidates[0]['offset']!=78
            or len({row['id'] for row in candidates})!=count):
        raise ValueError('Original candidate roots do not match declared vector')
    item_tables=[extract_items(ROOT/'extracted/tablebin'/name) for name in
                 ('4049c7809f4ac10f.bin','08e66a956e5d5647.bin')]
    items={row['dwStringID']:row for table in item_tables for row in table['rows']}
    entities={row['id']:row for row in extract_entities(ROOT/'extracted/tablebin/731ced6c9309b681.bin')['rows']}
    ammo_by_type={row['BulletType']:row for row in items.values() if row['mCategory']==3}
    joined=[]
    for row in candidates:
        item=items.get(row['id'])
        if item is None:raise ValueError('Weapon prefix has no original ItemTable record')
        row.update(item_category=item['mCategory'],item_subcategory=item['mSubCategory'])
        if item['mCategory'] not in (1,2):continue
        accepted=item['BulletUseTypeArray']
        if len(accepted)!=1 or accepted[0] not in ammo_by_type or row['id'] not in entities:
            raise ValueError('Original firearm/ammo/entity join is ambiguous')
        entity=entities[row['id']]
        ammo=ammo_by_type[accepted[0]]
        if entity['collectable']!=1 or not 1<=row['max_ammo']<=100 or not 1<=row['rpm']<=2000:
            raise ValueError('Unsupported recovered firearm limits')
        row.update(ammo_template=ammo['dwStringID'],bullet_type=accepted[0],ammo_stack_max=ammo['nPackMax'],
                   model_path=entity['model_path'],pickup_distance=entity['max_op_distance'])
        joined.append(row)
    if len(joined)!=20:raise ValueError('Unknown original firearm count')
    report=dict(source=source.name,source_sha256=hashlib.sha256(blob).hexdigest(),
        reflection={'weapon_info':'0xE5D890','params':'0x111C400'},declared_count=count,
        candidates=candidates,firearms=joined,
        limitation='Only WeaponInfo/WeaponParams prefixes; no nested recoil/FX/avatar decoding and no live weapon proof')
    destination=ROOT/'private/gameplay-catalog/weapon-stat-prefixes.json'
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'prefixes':len(candidates),'firearms':[
        {k:row[k] for k in ('id','name','max_ammo','rpm','ammo_template')} for row in joined]},ensure_ascii=True,indent=2))

if __name__=='__main__':main()
