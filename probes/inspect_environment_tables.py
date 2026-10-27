"""Inspect original Thai time/weather tables without extracting game assets.

Pass already extracted TableBin records.  The report contains identifiers and
numeric configuration only; it does not copy the proprietary table blobs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct


def table_header(data,expected):
    cursor=0
    names=[]
    for _ in range(2):
        length=data[cursor]
        cursor+=1
        names.append(data[cursor:cursor+length].decode('ascii'))
        cursor+=length
    version,count=struct.unpack_from('<HI',data,cursor)
    cursor+=6
    if names != [expected,expected] or version != 1:
        raise ValueError(f'Unexpected {expected} header')
    return cursor,count


def footer(data,cursor):
    if data[cursor:cursor+8] != b'\x07GameObj':
        raise ValueError('Unexpected table footer or row schema')


def time_table(path):
    data=path.read_bytes()
    cursor,count=table_header(data,'EnvrTimeTable')
    rows=[]
    for _ in range(count):
        row_version,identifier,day_length,slots=struct.unpack_from('<HIII',data,cursor)
        cursor+=14
        periods=[]
        for slot in range(slots):
            version,duration=struct.unpack_from('<HI',data,cursor)
            cursor+=6
            length=data[cursor]-0xc0
            cursor+=1
            name=data[cursor:cursor+length].decode('utf-8')
            cursor+=length
            period=struct.unpack_from('<I',data,cursor)[0]
            cursor+=4
            if version != row_version:
                raise ValueError('Mixed EnvrTimeTable row versions')
            periods.append(dict(slot=slot,duration=duration,name=name,period=period))
        rows.append(dict(version=row_version,id=identifier,day_length=day_length,periods=periods))
    footer(data,cursor)
    return rows


def weather_table(path):
    data=path.read_bytes()
    cursor,count=table_header(data,'EnvrWeatherTable')
    rows=[]
    for _ in range(count):
        values=struct.unpack_from('<H7I',data,cursor)
        cursor+=30
        rows.append(dict(version=values[0],weather_id=values[1],category=values[2],
                         parameters=list(values[3:])))
    footer(data,cursor)
    return rows


def resource_table(path):
    data=path.read_bytes()
    cursor,count=table_header(data,'EnvrMapWeatherResourceTable')
    rows=[]
    for _ in range(count):
        version,weather_id,period=struct.unpack_from('<HII',data,cursor)
        cursor+=10
        length=data[cursor]-0xc0
        cursor+=1
        name=data[cursor:cursor+length].decode('utf-8')
        cursor+=length
        rows.append(dict(version=version,weather_id=weather_id,period=period,resource=name))
    footer(data,cursor)
    return rows


parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('time_table',type=Path)
parser.add_argument('weather_table',type=Path)
parser.add_argument('resource_table',type=Path)
parser.add_argument('--out',type=Path)
args=parser.parse_args()

report={
    'time':time_table(args.time_table),
    'weather':weather_table(args.weather_table),
    'resources':resource_table(args.resource_table),
    'note':'Field names for the five weather parameters remain unknown; values are preserved in wire order.',
}
encoded=json.dumps(report,indent=2,ensure_ascii=False)
if args.out:
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(encoded,encoding='utf-8')
print(encoded)
