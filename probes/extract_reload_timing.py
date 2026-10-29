"""Read bounded Thai WeaponParams prefixes and WeaponInfo reload suffixes.

Requires the owner's extract_weapon_stat_prefixes.py report and matching table.
Does not decode the intervening FX/avatar payloads or export proprietary blobs.
"""
import hashlib
import json
import math
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]


def extract():
    data=(ROOT/'extracted/tablebin/231f78952b1944f4.bin').read_bytes()
    prefixes=json.loads((ROOT/'private/gameplay-catalog/weapon-stat-prefixes.json').read_text(encoding='utf8'))
    rows=prefixes['candidates']
    if (hashlib.sha256(data).hexdigest()!=prefixes['source_sha256'] or len(rows)!=24
            or rows[0]['offset']!=78 or struct.unpack_from('<I',data,74)[0]!=24):
        raise ValueError('Reload data requires matching, bounded original prefixes')
    firearms={r['id'] for r in prefixes['firearms']}
    result=[]
    for index,row in enumerate(rows[:-1]):
        if row['id'] not in firearms:continue
        start,end=row['offset'],rows[index+1]['offset']
        if (not start<end<=len(data) or struct.unpack_from('<HI',data,start)!=(29,row['id'])):
            raise ValueError('Invalid WeaponInfo boundary')
        length=data[start+6]-0xc0
        if not 0<length<=63 or data[start+7:start+7+length].decode('utf8')!=row['name']:
            raise ValueError('Invalid original weapon name boundary')
        pos=start+7+length+38
        if struct.unpack_from('<H',data,pos)[0]!=121:raise ValueError('Unsupported WeaponParams')
        # 111C4BA..111DDFF: 75 four-byte scalar properties, including HitType.
        pos+=2+75*4
        # Root members in 111DEA6..111E2A2, each with its own version tag.
        for count in (6,6,6,6,6,5,5):
            if struct.unpack_from('<H',data,pos)[0]!=count:raise ValueError('Unknown spring schema')
            pos+=2+4*count
        count=struct.unpack_from('<I',data,pos)[0]
        if not 1<=count<=4:raise ValueError('Unknown firing-mode vector')
        pos+=4+count*4
        for _ in range(2):
            if struct.unpack_from('<H',data,pos)[0]!=3:raise ValueError('Unknown aiming-offset schema')
            pos+=14
        pos+=12  # SightFov, mFpsEnterTimeMul, mFPSFireTimeOut.
        mode=struct.unpack_from('<I',data,pos)[0]  # 111E66B: ReloadType at Params+1E8.
        # E5F62E..E5F6E6: final three WeaponInfo members at +444/+448/+44C.
        base,extra,bolt=struct.unpack_from('<3f',data,end-12)
        if (pos+4>=end-12 or mode not in (0,1)
                or not all(math.isfinite(v) and 0<v<30 for v in (base,extra,bolt))):
            raise ValueError('Unsupported reload fields')
        result.append(dict(template=row['id'],mode=mode,base=base,extra=extra,bolt=bolt))
    if len(result)!=20 or len({r['template'] for r in result})!=20:raise ValueError('Unknown firearm coverage')
    return result


if __name__=='__main__':
    report=dict(rows=extract(),limitation='Bounded Params prefix and final Info fields; intervening payloads unparsed')
    (ROOT/'private/gameplay-catalog/reload-timing.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report))
