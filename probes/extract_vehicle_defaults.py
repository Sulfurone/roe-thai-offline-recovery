"""Read original EuVehicleTable rows using 0x74FEF0 reflection field order.

This deliberately supports only the observed Thai version 1/row 15 schema.
Unknown versions or string encodings fail instead of guessing boundaries.
"""
import hashlib
import json
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class Reader:
    def __init__(self,blob):
        self.blob,self.pos=blob,0
    def value(self,fmt):
        result=struct.unpack_from('<'+fmt,self.blob,self.pos)
        self.pos+=struct.calcsize('<'+fmt)
        return result[0] if len(result)==1 else result
    def version(self,wanted):
        actual=self.value('H')
        if actual!=wanted:
            raise ValueError(f'Unexpected version {actual}, wanted {wanted}, at {self.pos-2}')
    def small_string(self):
        size=self.value('B')
        if not 0xc0<=size<=0xff:
            raise ValueError(f'Unsupported compact string {size:#x}')
        size-=0xc0
        result=self.blob[self.pos:self.pos+size].decode('utf-8')
        self.pos+=size
        return result
    def count(self):
        n=self.value('I')
        if n>64:
            raise ValueError('Count outside this table schema')
        return n

rows=[]
for filename in ('8b62f6baf243d5be.bin','30680cc186959e47.bin','17dd10bdb377b749.bin'):
    blob=(ROOT/'extracted/tablebin'/filename).read_bytes()
    header=b'\x0eEuVehicleTable'*2
    if not blob.startswith(header):
        raise ValueError('Wrong table')
    r=Reader(blob)
    r.pos=len(header)
    r.version(1)
    count=r.count()
    for _ in range(count):
        start=r.pos
        r.version(15)
        ident,kind=r.value('II')
        name,module=r.small_string(),r.small_string()
        parts=[]
        for _ in range(r.count()):
            r.version(5)
            index,damage,hp=r.value('IBI')
            obj=r.small_string()
            affects=[]
            for _ in range(r.count()):
                r.version(2)
                affects.append((r.value('I'),r.small_string()))
            parts.append(dict(index=index,damage=damage,hp=hp,object=obj,affects=affects))
        seat_mode=r.value('I')
        r.version(3)
        group=r.value('iii')
        seats=[]
        for _ in range(r.count()):
            r.version(12)
            index,x,y,z=r.value('4i')
            axis=r.value('3f')
            off=r.value('3i')
            on_state,off_state=r.value('2i')
            seats.append(dict(index=index,position=(x,y,z),axis=axis,exit_position=off,
                              on_state=on_state,off_state=off_state))
        values=r.value('7i')
        row=dict(zip(('geton_distance','initial_hp','initial_oil','max_oil','mass','max_velocity','max_acceleration'),values))
        row.update(id=ident,kind=kind,name=name,module=module,parts=parts,seat_mode=seat_mode,
                   group_seat=group,seats=seats,source=filename,start=start,end=r.pos,
                   source_sha256=hashlib.sha256(blob).hexdigest())
        rows.append(row)
    if blob[r.pos:r.pos+17]!=b'\x10QSSplitTableBase':
        raise ValueError(f'Rows did not end at QSSplitTableBase: {filename} {r.pos}')

path=ROOT/'private/gameplay-catalog/vehicle-defaults.json'
path.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{k:r[k] for k in ('id','kind','name','initial_hp','initial_oil','max_oil','geton_distance')} for r in rows],ensure_ascii=False,indent=2))
