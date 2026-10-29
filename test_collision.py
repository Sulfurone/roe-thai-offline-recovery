import itertools
import math
import random
import unittest

from offline_collision import Model,Instance,primitive,convex_planes,rotate,euler_xyz,sub,dot,cross,norm,plane_hit


class CollisionTests(unittest.TestCase):
    def test_room_gap_passes_but_each_separate_wall_blocks(self):
        room=Model([primitive('box',(-100,0,0),extents=(10,100,100)),
                    primitive('box',(100,0,0),extents=(10,100,100))])
        self.assertFalse(room.blocks((0,-80,0),(0,80,0)))
        self.assertTrue(room.blocks((-200,0,0),(0,0,0)))
        self.assertTrue(room.blocks((0,0,0),(200,0,0)))
        self.assertFalse(room.blocks((-200,200,0),(200,200,0)))

    def test_convex_sloping_empty_space_is_not_its_enclosing_box(self):
        shape=primitive('convex',points=((0,0,0),(100,0,0),(0,100,0),(0,0,100)))
        self.assertFalse(shape.blocks((80,80,-10),(80,80,120)))
        self.assertTrue(shape.blocks((10,10,-10),(10,10,120)))
        self.assertTrue(shape.blocks((10,10,10),(20,20,20)))
        self.assertFalse(shape.blocks((200,0,0),(300,0,0)))

    def test_cube_hull_clips_all_axes_and_rejects_degenerate_input(self):
        points=list(itertools.product((-1.,1.),repeat=3))+[(0,0,0)]
        planes=convex_planes(points)
        self.assertEqual(len(planes),6)
        shape=primitive('convex',points=points)
        for axis in range(3):
            a=[0,0,0];b=[0,0,0];a[axis]=-2;b[axis]=2
            self.assertTrue(shape.blocks(a,b))
        for points in (((0,0,0),)*4,((0,0,0),(1,0,0),(0,1,0),(1,1,0))):
            with self.assertRaises(ValueError):convex_planes(points)

    def test_round_shapes_hit_segment_middle_and_capsule_axis_is_x(self):
        sphere=primitive('sphere',radius=10)
        self.assertTrue(sphere.blocks((-100,0,0),(100,0,0)))
        self.assertFalse(sphere.blocks((-100,11,0),(100,11,0)))
        capsule=primitive('capsule',radius=10,half_height=30)
        self.assertTrue(capsule.blocks((25,-100,0),(25,100,0)))
        self.assertFalse(capsule.blocks((45,-100,0),(45,100,0)))

    def test_local_pose_and_instance_inverse_rotation_scale_are_consistent(self):
        q=euler_xyz((0,0,math.pi/2))
        box=primitive('box',(100,200,0),q,extents=(50,5,5))
        self.assertTrue(box.blocks((0,220,0),(200,220,0)))
        self.assertFalse(box.blocks((0,260,0),(200,260,0)))
        instance=Instance('own.xml',(1000,2000,3000),(0,0,math.pi/2),2)
        a,b=instance.local_ray((1000,1800,3000),(1000,2200,3000))
        self.assertAlmostEqual(a[0],-100)
        self.assertAlmostEqual(b[0],100)
        self.assertAlmostEqual(a[1],0)
        self.assertAlmostEqual(b[2],0)

    def test_query_flags_and_padding_are_separate(self):
        glass=primitive('box',extents=(10,10,10),flags=frozenset(('mSeeThrough',)))
        self.assertTrue(glass.blocks((-20,0,0),(20,0,0)))
        self.assertFalse(glass.blocks((-20,0,0),(20,0,0),mode='sight'))
        box=primitive('box',extents=(10,10,10))
        self.assertFalse(box.blocks((-20,12,0),(20,12,0)))
        self.assertTrue(box.blocks((-20,12,0),(20,12,0),3))

    def test_incremental_hull_agrees_with_independent_support_plane_enumeration(self):
        rng=random.Random(731)
        for _ in range(6):
            points=[tuple(rng.uniform(-100,100) for _ in range(3)) for _ in range(10)]
            points.append(tuple(v+1e-6 for v in points[3]))
            support=[]
            for a,b,c in itertools.combinations(points,3):
                n=cross(sub(b,a),sub(c,a));length=norm(n)
                if length<1e-8:continue
                n=tuple(v/length for v in n);d=dot(n,a)
                offsets=[dot(n,p)-d for p in points]
                if max(offsets)<=1e-6:support.append((n,max(dot(n,p) for p in points)))
                elif min(offsets)>=-1e-6:
                    n=tuple(-v for v in n);support.append((n,max(dot(n,p) for p in points)))
            shape=primitive('convex',points=points)
            for _ in range(30):
                a,b=[tuple(rng.uniform(-150,150) for _ in range(3)) for _ in range(2)]
                self.assertEqual(shape.blocks(a,b),plane_hit(a,b,support))


if __name__=='__main__':unittest.main()
