"""Read owned Thai PhysCollectionDesc SFC records, never redistribute assets."""
from collections import OrderedDict
import math
from pathlib import Path,PurePosixPath
import re
import struct
import xml.etree.ElementTree as ET

from sfc_extract import lz4_block
from offline_collision import Model,primitive,quaternion,rotate,add,multiply


def sfc_path_key(path):
    # Effective seed for this Thai cache's canonical relative DATA paths.
    # Derived from collision/LOD/asset pairs and cross-checked across archives;
    # not a claim that another build uses this cache namespace.
    text=path.replace('/','\\').lstrip('\\').upper()
    text.encode('ascii')
    value=0x1712e27f4d2960db
    for char in text:value=(value*67+ord(char))&((1<<64)-1)
    return value.to_bytes(8,'little')


def vector(element,names,default=None):
    if element is None:
        if default is not None:return default
        raise ValueError('Collision vector missing')
    values=tuple(float(element.get(name)) for name in names)
    if any(not math.isfinite(v) or abs(v)>2e6 for v in values):raise ValueError('Collision vector exceeds bounds')
    return values


def array(parent,name,maximum):
    container=parent.find(name)
    if container is None:return []
    rows=container.findall(name)
    if container.get('IsStaticArray')!='0' or int(container.get('ArrayCount','-1'))!=len(rows) or len(rows)>maximum:
        raise ValueError('Collision array count differs')
    return rows


def parse_model(root):
    if root.tag!='NewObj' or root.get('Version')!='1':raise ValueError('Unknown collision object')
    descriptor=root.find('PhysCollectionDesc')
    if descriptor is None:raise ValueError('Physics descriptor missing')
    actors=array(descriptor,'mActors',256)
    shapes=[]
    for actor in actors:
        if actor.get('mUsage')!='PhysActorDesc::eSTATIC':raise ValueError('Nonstatic collision actor')
        actor_position=vector(actor.find('mLocalPosition'),'xyz',(0,0,0))
        actor_rotation=quaternion(vector(actor.find('mLocalRotation'),'xyzw',(0,0,0,1)))
        for child in actor:
            if child.tag not in ('mSpheres','mBoxes','mConvexes','mCapsules','mLocalPosition','mLocalRotation'):
                raise ValueError('Unsupported collision geometry collection')
        for name,kind in (('mBoxes','box'),('mConvexes','convex'),('mSpheres','sphere'),('mCapsules','capsule')):
            for row in array(actor,name,4096):
                param=row.find('mParam')
                if param is None:raise ValueError('Shape parameters missing')
                position=vector(param.find('mLocalPosition'),'xyz')
                rotation=quaternion(vector(param.find('mLocalRotation'),'xyzw'))
                position=add(actor_position,rotate(actor_rotation,position))
                rotation=multiply(actor_rotation,rotation)
                flags=frozenset(k for k in ('physxThrough','mSeeThrough','mWalkThrough') if param.get(k)=='true')
                values={}
                if kind=='box':values['extents']=vector(row.find('mHalfExtents'),'xyz')
                elif kind=='convex':values['points']=[vector(p,'xyz') for p in array(row,'mPoints',256)]
                else:
                    # Only explicit half-height is supported. Do not guess
                    # whether another schema's mHeight is full or half height.
                    radius=row.get('mRadius')
                    if radius is None:raise ValueError('Unknown round shape radius')
                    values['radius']=float(radius)
                    if kind=='capsule':
                        height=row.get('mHalfHeight')
                        if height is None:raise ValueError('Unknown capsule height schema')
                        values['half_height']=float(height)
                shapes.append(primitive(kind,position,rotation,flags=flags,**values))
                if len(shapes)>16384:raise ValueError('Collision model exceeds shape bound')
    return Model(shapes)


def xml_records(path,selected_key=None):
    if not 8<=path.stat().st_size<=64*1024*1024:raise ValueError('Collision archive exceeds bound')
    data=path.read_bytes()
    if data[:8]!=b'SFC\x1a\x02\0\0\0':raise ValueError('Unknown collision SFC version')
    pos=8;active={};total=0
    while pos<len(data):
        if pos+16>len(data):raise ValueError('Truncated collision archive')
        key=data[pos:pos+8];packed=struct.unpack_from('<I',data,pos+8)[0];end=pos+12+packed
        if end+4>len(data):raise ValueError('Collision block exceeds archive')
        size=struct.unpack_from('<I',data,end)[0]
        payload=data[pos+12:end];pos=end+4
        active.pop(key,None)
        if selected_key is not None and key!=selected_key:continue
        # Avoid decompressing mesh/texture binary records. The first LZ4
        # literal is uncompressed and an XML record starts with '<' or BOM.
        if not payload:continue
        literal=payload[0]>>4;cursor=1
        if literal==15:
            while cursor<len(payload):
                extra=payload[cursor];cursor+=1;literal+=extra
                if extra!=255:break
        prefix=payload[cursor:cursor+min(literal,64)].lstrip(b'\xef\xbb\xbf \r\n\t')
        if prefix and not prefix.startswith(b'<'):continue
        if not 0<size<=32*1024*1024:raise ValueError('Collision XML exceeds record bound')
        total+=size
        if total>128*1024*1024:raise ValueError('Collision XML exceeds archive budget')
        raw=lz4_block(payload,size)
        if b'<PhysCollectionDesc' not in raw:continue
        if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:raise ValueError('External XML entities forbidden')
        active[key]=ET.fromstring(raw)  # Last occurrence of the same SFC key wins.
    return active


class CollisionAssets:
    def __init__(self,directory):
        self.directory=Path(directory)
        if not self.directory.is_dir():raise ValueError('Collision SFC directory not found')
        self.archives={p.name.casefold():p for p in self.directory.glob('*.sfc')}
        if not self.archives:raise ValueError('Collision directory has no SFC archives')
        self.cache=OrderedDict();self.failures={};self.loads=0
        self.frozen=False
        self.index=None

    def build_index(self):
        index={};records=0
        if len(self.archives)>10000:raise ValueError('Too many collision archives')
        for path in self.archives.values():
            active={}
            with path.open('rb',buffering=0) as source:
                size=path.stat().st_size
                if not 8<=size<=4*1024**3 or source.read(8)!=b'SFC\x1a\x02\0\0\0':
                    raise ValueError('Unknown archive in collision directory')
                offset=8
                while offset<size:
                    source.seek(offset);header=source.read(12)
                    if len(header)!=12:raise ValueError('Truncated collision archive index')
                    packed=struct.unpack_from('<I',header,8)[0]
                    if offset+packed+16>size:raise ValueError('Collision index block exceeds archive')
                    active[header[:8]]=offset
                    offset+=packed+16;records+=1
                    if records>1_000_000:raise ValueError('Collision record index exceeds bound')
            for key,offset in active.items():index.setdefault(key,[]).append((path,offset))
        self.index=index

    def indexed_model(self,key):
        matches=self.index.get(key,())
        if len(matches)!=1:raise ValueError('Exact collision resource is absent or duplicated across archives')
        path,offset=matches[0]
        with path.open('rb') as source:
            source.seek(offset);header=source.read(12)
            if len(header)!=12 or header[:8]!=key:raise ValueError('Collision archive changed after indexing')
            packed=struct.unpack_from('<I',header,8)[0]
            if not 0<packed<=32*1024*1024:raise ValueError('Indexed collision block exceeds bound')
            payload,tail=source.read(packed),source.read(4)
        if len(payload)!=packed or len(tail)!=4:raise ValueError('Indexed collision block truncated')
        size=struct.unpack('<I',tail)[0]
        if not 0<size<=32*1024*1024:raise ValueError('Indexed collision XML exceeds bound')
        raw=lz4_block(payload,size);self.loads+=1
        if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:raise ValueError('External XML entities forbidden')
        return ET.fromstring(raw)

    def prepare(self,paths,max_shapes=200000):
        """Load before client launch; never decode assets on the live loop.

        Keep the full successfully prepared set under a shape budget. Unknown
        or excess models keep the old broad bound; a query never triggers I/O.
        """
        self.preparing=True
        self.build_index()
        count=0
        for path in sorted(set(paths),key=str.casefold):
            model=self.get(path)
            if model is None:continue
            count+=len(model.shapes)
            if count>max_shapes:
                key=path.replace('\\','/').casefold()
                count-=len(model.shapes);self.cache.pop(key,None)
                self.failures[key]='Prepared collision shape budget exceeded'
        self.preparing=False;self.frozen=True
        self.summary=dict(models=len(self.cache),shapes=count,fallback_models=len(self.failures))
        return self.summary

    def get(self,path):
        key=path.replace('\\','/').casefold()
        if key in self.cache:
            self.cache.move_to_end(key);return self.cache[key]
        if key in self.failures:return None
        if self.frozen:return None
        try:
            parts=PurePosixPath(key).parts
            if (len(parts)<4 or parts[:2]!=('data','scene') or not parts[-1].endswith('_collision.xml')
                    or any(not re.fullmatch(r'[a-z0-9_-]+',p) for p in parts[:-1])):
                raise ValueError('Unknown collision path')
            stem=parts[-1][:-4]
            if not re.fullmatch('[a-z0-9_-]+',stem):raise ValueError('Collision filename differs')
            if self.index is None:self.build_index()
            selected=self.indexed_model(sfc_path_key(path))
            result=parse_model(selected)
        except (OSError,ValueError,TypeError,ET.ParseError) as error:
            self.failures[key]=str(error);return None
        self.cache[key]=result
        if not getattr(self,'preparing',False) and len(self.cache)>64:self.cache.popitem(last=False)
        return result
