"""Local height queries from the verified Thai collision heightfield."""
from array import array
from dataclasses import dataclass
import math
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass
class TerrainSurface:
    rows: int
    columns: int
    row_scale: float
    column_scale: float
    height_scale: float
    origin: tuple
    samples: array

    @classmethod
    def from_repx(cls, path):
        path=Path(path)
        if not 0<path.stat().st_size<=64*1024*1024:
            raise ValueError('Collision heightfield exceeds the verified size bound')
        root=ET.parse(path).getroot()
        field,rigid=root.find('PxHeightField'),root.find('PxRigidStatic')
        if field is None or rigid is None:
            raise ValueError('Expected a Thai heightfield and rigid pose')
        shape=rigid.find('Shapes/PxShape/Geometry/PxHeightFieldGeometry')
        if shape is None:
            # The original extraction uses a direct PxShape child.
            shape=rigid.find('.//PxHeightFieldGeometry')
        if shape is None:
            geometry=rigid.find('.//Geometry')
            shape=geometry[0] if geometry is not None and len(geometry) else None
        if shape is None:
            raise ValueError('Missing heightfield geometry')
        rows,columns=int(field.findtext('NbRows')),int(field.findtext('NbColumns'))
        pose=tuple(float(v) for v in rigid.findtext('GlobalPose').split())
        if not (2<=rows<=4097 and 2<=columns<=4097 and rows*columns<=17_000_000
                and len(pose)==7 and pose[:4]==(.5,.5,.5,.5)
                and all(math.isfinite(v) for v in pose)):
            raise ValueError('Unsupported collision bounds or coordinate transform')
        scales=tuple(float(shape.findtext(k)) for k in ('RowScale','ColumnScale','HeightScale'))
        if not all(math.isfinite(v) and v>0 for v in scales):
            raise ValueError('Invalid heightfield scale')
        samples=array('h')
        for token in field.findtext('samples').split():
            value=int(token)&0xffff
            samples.append(value-65536 if value&32768 else value)
        if len(samples)!=rows*columns:
            raise ValueError('Heightfield sample count differs')
        return cls(rows,columns,*scales,pose[4:],samples)

    def height_at(self,x,y):
        # The verified quaternion maps local columns to world X and rows
        # to world Y. Bilinear sampling is a landing aid, not a collision solver.
        column=(x-self.origin[0])/self.column_scale
        row=(y-self.origin[1])/self.row_scale
        if not (math.isfinite(column) and math.isfinite(row)
                and 0<=column<=self.columns-1 and 0<=row<=self.rows-1):
            return None
        c,r=min(int(column),self.columns-2),min(int(row),self.rows-2)
        u,v=column-c,row-r
        def sample(dr,dc):
            return self.samples[(r+dr)*self.columns+c+dc]
        height=((1-u)*(1-v)*sample(0,0)+u*(1-v)*sample(0,1)
                +(1-u)*v*sample(1,0)+u*v*sample(1,1))
        return height*self.height_scale+self.origin[2]
