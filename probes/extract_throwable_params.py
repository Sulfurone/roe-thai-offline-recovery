"""Read the bounded ThrowableParams tail of the owned Thai weapon table.

Reflection E788AE..E792C6: vector<ThrowableParams v20>, then bone names.
Nested recoil/avatar/trail portions before this vector are not decoded.
Resource data and generated reports stay private.
"""
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from probes.extract_original_item_defaults import Reader

FLOATS = ('mFuseTime', 'mRestitution', 'mRestitutionFactor', 'mSweepRadius',
          'mInitSpeedFar', 'mInitSpeedClose', 'mAirDrag', 'mExplodeRange',
          'mReserveTime', 'mPredictTrajectoryTime', 'mVelDeltaTime')


def extract(path):
    blob = Path(path).read_bytes()
    if (len(blob)<78 or not blob.startswith(b'\x13QSWeaponConfigTable'*2)
            or struct.unpack_from('<H',blob,40)[0]!=14
            or struct.unpack_from('<I',blob,74)[0]!=24):
        raise ValueError('Not the original weapon table')
    marker = struct.pack('<IHII', 2, 20, 50001, 0)
    if blob.count(marker) != 1:
        raise ValueError('Throwable tail boundary is ambiguous')
    reader = Reader(blob)
    reader.pos = blob.index(marker)
    count = reader.value('I')
    rows = []
    for _ in range(count):
        start = reader.pos
        if reader.value('H') != 20:
            raise ValueError('Unknown ThrowableParams version')
        row = dict(mThrowableId=reader.value('I'), mType=reader.value('I'))
        row.update((name, reader.value('f')) for name in FLOATS)
        for name in ('mInitRotatation', 'mRotationXYZPerSecond'):
            if reader.value('H') != 3:
                raise ValueError('Unknown throwable vector version')
            row[name] = [reader.value('f') for _ in range(3)]
        row['mMeshPathReleased'] = reader.value('s')
        row['mReleasedMeshScale'] = reader.value('f')
        row['mExplodeFxName'] = reader.value('s')
        row['mExplodeHintFxName'] = reader.value('s')
        row['mMeshOffsetZ'] = reader.value('f')
        if any(not math.isfinite(row[name]) for name in FLOATS):
            raise ValueError('Nonfinite throwable parameter')
        row.update(start=start, end=reader.pos)
        rows.append(row)
    bones = reader.value('vs')
    footer = reader.pos
    if blob[footer:footer+10] != b'\x07GameObj\x02\0':
        raise ValueError('Throwable tail does not end at GameObj footer')
    reader.pos += 10
    if reader.value('s') != 'Data.Table.Weapons.QSWeaponConfigTable' or len(blob)-reader.pos != 4:
        raise ValueError('Unknown owning config footer')
    if [(r['mThrowableId'], r['mType']) for r in rows] != [(50001, 0), (50002, 1)]:
        raise ValueError('Unknown original throwable rows')
    return dict(source=Path(path).name, sha256=hashlib.sha256(blob).hexdigest(),
                rows=rows, check_bones=bones, footer=footer,
                limitation='Only the ThrowableParams tail; no server damage formula or proof of active runtime override')


if __name__ == '__main__':
    report = extract(ROOT/'extracted/tablebin/231f78952b1944f4.bin')
    output = ROOT/'private/gameplay-catalog/throwable-params.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(dict(rows=[{k:row[k] for k in ('mThrowableId', 'mType', 'mFuseTime',
          'mExplodeRange', 'mReserveTime', 'mInitSpeedFar')} for row in report['rows']],
          check_bones=len(report['check_bones']), footer=report['footer'],
          limitation=report['limitation'])))
