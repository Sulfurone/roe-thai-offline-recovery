"""Bounded local box/convex/sphere/capsule queries, independent of game code.

Uses source collision geometry when available. It is not PhysX simulation,
material penetration, navigation, or an exact swept character controller.
"""
from dataclasses import dataclass
from collections import Counter
import itertools
import math


def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm(a):return math.sqrt(dot(a,a))


def quaternion(q):
    length=norm(q)
    if len(q)!=4 or not math.isfinite(length) or abs(length-1)>.001:
        raise ValueError('Collision quaternion is not normalized')
    return tuple(v/length for v in q)


def rotate(q,p):
    t=tuple(2*x for x in cross(q[:3],p))
    extra=cross(q[:3],t)
    return tuple(p[i]+q[3]*t[i]+extra[i] for i in range(3))


def multiply(a,b):
    v=add(add(tuple(a[3]*x for x in b[:3]),tuple(b[3]*x for x in a[:3])),cross(a[:3],b[:3]))
    return (*v,a[3]*b[3]-dot(a[:3],b[:3]))


def euler_xyz(angles):
    x,y,z=(v/2 for v in angles)
    sx,sy,sz=math.sin(x),math.sin(y),math.sin(z)
    cx,cy,cz=math.cos(x),math.cos(y),math.cos(z)
    # Own Thai A32A70 matrix: Rx * Ry * Rz, applied to column vectors.
    return (sx*cy*cz+cx*sy*sz,cx*sy*cz-sx*cy*sz,cx*cy*sz+sx*sy*cz,cx*cy*cz-sx*sy*sz)


def bounds_entry(start,end,lower,upper,padding=0):
    enter,leave=0.,1.
    for a,b,lo,hi in zip(start,end,lower,upper):
        delta=b-a
        if abs(delta)<1e-12:
            if not lo-padding<=a<=hi+padding:return None
        else:
            first,last=sorted(((lo-padding-a)/delta,(hi+padding-a)/delta))
            enter,leave=max(enter,first),min(leave,last)
            if enter>leave+1e-10:return None
    return enter


def convex_planes(points):
    points=tuple(dict.fromkeys(tuple(p) for p in points))
    if not 4<=len(points)<=256 or any(len(p)!=3 or any(not math.isfinite(v) or abs(v)>2e6 for v in p) for p in points):
        raise ValueError('Invalid bounded convex points')
    original=points
    weld=max(1e-5,max(max(p[a] for p in points)-min(p[a] for p in points) for a in range(3))*1e-6)
    unique=[]
    for p in points:
        if all(norm(sub(p,q))>weld for q in unique):unique.append(p)
    points=tuple(unique)
    if len(points)<4:raise ValueError('Convex points collapsed during numeric welding')
    first=min(range(len(points)),key=lambda i:points[i])
    second=max(range(len(points)),key=lambda i:dot(sub(points[i],points[first]),sub(points[i],points[first])))
    scale=norm(sub(points[second],points[first]));epsilon=weld
    if scale<=epsilon:raise ValueError('Degenerate convex point cloud')
    line=sub(points[second],points[first])
    third=max(range(len(points)),key=lambda i:norm(cross(line,sub(points[i],points[first]))))
    normal=cross(line,sub(points[third],points[first]))
    if norm(normal)<=epsilon*scale:raise ValueError('Collinear convex points')
    fourth=max(range(len(points)),key=lambda i:abs(dot(normal,sub(points[i],points[first]))))
    if abs(dot(normal,sub(points[fourth],points[first])))<=epsilon*norm(normal):
        raise ValueError('Coplanar convex points')
    seed=(first,second,third,fourth)
    interior=tuple(sum(points[i][axis] for i in seed)/4 for axis in range(3))
    def face(a,b,c):
        normal=cross(sub(points[b],points[a]),sub(points[c],points[a]))
        length=norm(normal)
        if length<=epsilon*epsilon:raise ValueError('Degenerate hull face')
        if dot(normal,sub(interior,points[a]))>0:b,c=c,b;normal=tuple(-v for v in normal)
        normal=tuple(v/length for v in normal)
        return (a,b,c,normal,dot(normal,points[a]))
    faces=[face(first,second,third),face(first,fourth,second),
           face(first,third,fourth),face(second,fourth,third)]
    for index,p in enumerate(points):
        if index in seed:continue
        visible=[f for f in faces if dot(f[3],p)-f[4]>max(1e-10,scale*1e-12)]
        if not visible:continue
        horizon=set()
        for a,b,c,_,_ in visible:
            for edge in ((a,b),(b,c),(c,a)):
                reverse=edge[::-1]
                if reverse in horizon:horizon.remove(reverse)
                else:horizon.add(edge)
        degree=Counter(i for edge in horizon for i in edge)
        if len(horizon)<3 or any(v!=2 for v in degree.values()):raise ValueError('Nonmanifold hull horizon')
        faces=[f for f in faces if f not in visible]+[face(a,b,index) for a,b in horizon]
        if len(faces)>1024:raise ValueError('Convex hull exceeds face bound')
    edges=Counter(tuple(sorted(edge)) for a,b,c,_,_ in faces for edge in ((a,b),(b,c),(c,a)))
    if any(v!=2 for v in edges.values()):raise ValueError('Convex hull is not closed')
    outside=max(dot(f[3],p)-f[4] for f in faces for p in original)
    if outside>epsilon*8:raise ValueError(f'Convex hull excludes a source point: {outside:g} > {epsilon*8:g}')
    # Tiny source-coordinate duplicates can produce unstable sliver faces.
    # Weld only within 1e-6 of the cloud span, then move each support plane
    # outward to include every original point. Larger discrepancies reject.
    planes={tuple(round(v,8) for v in (*f[3],f[4])):(f[3],max(dot(f[3],p) for p in original)) for f in faces}
    return tuple(planes.values())


def plane_hit(start,end,planes,padding=0):
    enter,leave=0.,1.
    direction=sub(end,start)
    for normal,distance in planes:
        gap=distance+padding-dot(normal,start)
        speed=dot(normal,direction)
        if abs(speed)<1e-12:
            if gap< -1e-8:return False
        elif speed<0:enter=max(enter,gap/speed)
        else:leave=min(leave,gap/speed)
        if enter>leave+1e-10:return False
    return enter<=leave+1e-10


def segment_distance(a,b,c,d):
    # Closest points on two finite segments, including degenerate endpoints.
    u,v,w=sub(b,a),sub(d,c),sub(a,c)
    aa,bb,cc,dd,ee=dot(u,u),dot(u,v),dot(v,v),dot(u,w),dot(v,w)
    if aa<1e-12:s=0.;t=max(0,min(1,ee/cc)) if cc>1e-12 else 0.
    elif cc<1e-12:t=0.;s=max(0,min(1,-dd/aa))
    else:
        denominator=aa*cc-bb*bb
        s=max(0,min(1,(bb*ee-cc*dd)/denominator)) if denominator>1e-12 else 0.
        t=(bb*s+ee)/cc if cc>1e-12 else 0.
        if t<0:t=0.;s=max(0,min(1,-dd/aa))
        elif t>1:t=1.;s=max(0,min(1,(bb-dd)/aa))
    return norm(sub(add(a,tuple(s*x for x in u)),add(c,tuple(t*x for x in v))))


@dataclass(frozen=True)
class Shape:
    lower:tuple
    upper:tuple
    planes:tuple=()
    axis:tuple=()
    radius:float=0
    flags:frozenset=frozenset()

    def blocks(self,start,end,padding=0,mode='solid'):
        if ('physxThrough' in self.flags or mode=='sight' and 'mSeeThrough' in self.flags
                or padding>0 and 'mWalkThrough' in self.flags):return False
        if bounds_entry(start,end,self.lower,self.upper,padding) is None:return False
        return (plane_hit(start,end,self.planes,padding) if self.planes else
                segment_distance(start,end,*self.axis)<=self.radius+padding)


def primitive(kind,position=(0,0,0),rotation=(0,0,0,1),*,points=(),extents=(),radius=0,half_height=0,flags=frozenset()):
    rotation=quaternion(rotation)
    if kind=='box':
        if len(extents)!=3 or any(not math.isfinite(v) or not 0<v<1e5 for v in extents):raise ValueError('Invalid box extents')
        points=tuple(itertools.product(*[(-v,v) for v in extents]))
        planes=tuple((tuple(sign if i==axis else 0 for i in range(3)),extent)
                     for axis,extent in enumerate(extents) for sign in (-1,1))
    elif kind=='convex':planes=convex_planes(points)
    elif kind in ('sphere','capsule'):
        if not 0<radius<1e5 or not 0<=half_height<1e5:raise ValueError('Invalid round shape')
        axis=tuple(add(position,rotate(rotation,p)) for p in ((-half_height,0,0),(half_height,0,0)))
        return Shape(tuple(min(p[i] for p in axis)-radius for i in range(3)),
                     tuple(max(p[i] for p in axis)+radius for i in range(3)),axis=axis,radius=radius,flags=flags)
    else:raise ValueError('Unknown collision primitive')
    transformed=tuple(add(position,rotate(rotation,p)) for p in points)
    planes=tuple((rotate(rotation,n),d+dot(rotate(rotation,n),position)) for n,d in planes)
    return Shape(tuple(min(p[i] for p in transformed) for i in range(3)),
                 tuple(max(p[i] for p in transformed) for i in range(3)),planes=planes,flags=flags)


@dataclass(frozen=True)
class Node:
    lower:tuple
    upper:tuple
    children:tuple
    shapes:tuple


class Model:
    def __init__(self,shapes):
        self.shapes=tuple(shapes)
        if not 1<=len(self.shapes)<=16384:raise ValueError('Collision model exceeds shape bound')
        def build(items):
            lower=tuple(min(s.lower[i] for s in items) for i in range(3))
            upper=tuple(max(s.upper[i] for s in items) for i in range(3))
            if len(items)<=8:return Node(lower,upper,(),tuple(items))
            axis=max(range(3),key=lambda i:upper[i]-lower[i])
            ordered=sorted(items,key=lambda s:s.lower[axis]+s.upper[axis]);middle=len(items)//2
            return Node(lower,upper,(build(ordered[:middle]),build(ordered[middle:])),())
        self.root=build(self.shapes)

    def blocks(self,start,end,padding=0,mode='solid'):
        stack=[self.root]
        while stack:
            node=stack.pop()
            if bounds_entry(start,end,node.lower,node.upper,padding) is None:continue
            if any(s.blocks(start,end,padding,mode) for s in node.shapes):return True
            stack.extend(node.children)
        return False


@dataclass(frozen=True)
class Instance:
    path:str
    position:tuple
    angles:tuple
    scale:float

    def __post_init__(self):
        if (len(self.position)!=3 or len(self.angles)!=3
                or any(not math.isfinite(v) or abs(v)>2e6 for v in (*self.position,*self.angles))
                or not math.isfinite(self.scale) or not 0<self.scale<=1024):
            raise ValueError('Invalid collision instance transform')

    def local_ray(self,start,end):
        q=euler_xyz(self.angles);inverse=tuple(-x for x in q[:3])+(q[3],)
        return tuple(tuple(v/self.scale for v in rotate(inverse,sub(p,self.position))) for p in (start,end))
