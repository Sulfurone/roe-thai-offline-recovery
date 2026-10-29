"""Read the owner's complete Thai component table v2 / rows27 / overrides11.

Names and model paths are consumed but not included in the numeric report.
Reflection E5F8A0..E609A0 defines root/override field order and vector sizes.
"""
import hashlib
import json
import math
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
MODIFIERS=('damage','spread','muzzle','vertical','horizontal','ads','sway','reload','shotgun_spread')


class Reader:
    def __init__(self,data):self.data,self.pos=data,0

    def value(self,kind):
        size=struct.calcsize('<'+kind)
        if self.pos+size>len(self.data):raise ValueError('Truncated component field')
        value=struct.unpack_from('<'+kind,self.data,self.pos)[0];self.pos+=size
        if kind=='f' and not math.isfinite(value):raise ValueError('Nonfinite component scalar')
        return value

    def string(self):
        tag=self.value('B')
        if tag>=0xc0:length=tag&63
        elif tag>=0x80:
            length=(tag&63)|(self.value('B')<<6)
            if length<64:raise ValueError('Noncanonical compact string')
        else:raise ValueError('Unsupported compact string')
        if length>4096 or self.pos+length>len(self.data):raise ValueError('Unbounded component string')
        value=self.data[self.pos:self.pos+length];self.pos+=length
        return value

    def vector3(self):
        if self.value('H')!=3:raise ValueError('Unknown component vector schema')
        return tuple(self.value('f') for _ in range(3))

    def boolean(self):
        value=self.value('B')
        if value not in (0,1):raise ValueError('Invalid component flag')
        return value


def extract(path):
    data=Path(path).read_bytes();reader=Reader(data)
    header=b'\x1cQSWeaponComponentConfigTable'*2
    if not data.startswith(header):raise ValueError('Unknown component table header')
    reader.pos=len(header)
    if reader.value('H')!=2:raise ValueError('Unknown component table version')
    apply=reader.boolean();count=reader.value('I')
    if count!=79:raise ValueError('Unknown component count')
    rows=[]
    for _ in range(count):
        start=reader.pos
        if reader.value('H')!=27:raise ValueError(('Unknown component row',start))
        ident=reader.value('I');reader.string()  # Legacy encoded label.
        for _ in range(3):reader.string()
        overrides=reader.value('I')
        if overrides>32:raise ValueError('Unbounded weapon overrides')
        weapon_ids=[]
        for _ in range(overrides):
            if reader.value('H')!=11:raise ValueError('Unknown apply-weapon schema')
            weapon_ids.append(reader.value('I'));reader.string();reader.value('f');reader.boolean()
            for _ in range(3):reader.value('f')
            reader.vector3()
            for _ in range(3):reader.value('f')
        flags=dict(zip(('hide_flash','silenced','grip','scope','extended'),(reader.boolean() for _ in range(5))))
        modifiers={name:reader.value('f') for name in MODIFIERS}
        scope_type=reader.value('I');reader.vector3();reader.value('f')
        for _ in range(3):reader.vector3()
        reader.value('I')
        rows.append(dict(template=ident,start=start,end=reader.pos,weapon_overrides=weapon_ids,
                         flags=flags,modifiers=modifiers,scope_type=scope_type))
    footer=reader.pos
    if data[footer:footer+10]!=b'\x07GameObj\x02\0':raise ValueError('Component rows do not meet footer')
    reader.pos+=10
    if reader.string()!=b'Data.Table.Weapons.QSWeaponComponentConfigTable' or len(data)-reader.pos!=4:
        raise ValueError('Unknown component owner/footer')
    if len({r['template'] for r in rows})!=count:raise ValueError('Duplicate components')
    return dict(source=Path(path).name,sha256=hashlib.sha256(data).hexdigest(),apply_config=apply,
                rows=rows,footer=footer,limitation='Numeric fields only; runtime use and server capacity formula require separate proof')


if __name__=='__main__':
    report=extract(ROOT/'extracted/tablebin/ba5fbeaa4ae24bce.bin')
    (ROOT/'private/gameplay-catalog/weapon-components.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(rows=len(report['rows']),footer=report['footer'],
        magazines=[r for r in report['rows'] if 40400<r['template']<40450])))
