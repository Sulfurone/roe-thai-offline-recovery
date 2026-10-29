import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_collision_assets import CollisionAssets,sfc_path_key
from offline_visibility import StaticVisibility


def collision_xml():
    rows=[]
    for x in (-100,100):
        rows.append(f'<mBoxes><mParam><mLocalPosition x="{x}" y="0" z="0"/>'
            '<mLocalRotation x="0" y="0" z="0" w="1"/></mParam>'
            '<mHalfExtents x="10" y="100" z="100"/></mBoxes>')
    return ('<NewObj Version="1" ObjName="Own_Room"><PhysCollectionDesc>'
        '<mActors IsStaticArray="0" ArrayCount="1"><mActors mUsage="PhysActorDesc::eSTATIC">'
        '<mBoxes IsStaticArray="0" ArrayCount="2">'+''.join(rows)+
        '</mBoxes></mActors></mActors></PhysCollectionDesc></NewObj>').encode()


def sfc(raw,key):
    size=len(raw);extra=size-15;packed=bytearray(b'\xf0')
    while extra>=255:packed.append(255);extra-=255
    packed.append(extra);packed.extend(raw)
    return b'SFC\x1a\x02\0\0\0'+key+struct.pack('<I',len(packed))+packed+struct.pack('<I',size)


class Flat:
    def height_at(self,x,y):return 6500


class CollisionAssetTests(unittest.TestCase):
    path='Data/Scene/general/building/Own_Room_collision.xml'

    def test_exact_key_scene_room_gap_and_wall_queries(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'Scene_General_Building_Own_Room.sfc').write_bytes(sfc(collision_xml(),sfc_path_key(self.path)))
            scene=root/'scene.xml'
            scene.write_text('<r ObjName="x.eu_killzone_2048.ClientTable.RigidStaticInPxScene">'
                f'<mItems mID="1" mModelFullPath="{self.path}" mPosX="1000" mPosY="2000" mPosZ="7000" '
                'mRotateX="0" mRotateY="0" mRotateZ="0" mScale="1" '
                'mBoundingX="1000" mBoundingY="2000" mBoundingZ="7000" mBoundingRadius="200"/></r>')
            before=StaticVisibility.from_scene(Flat(),scene)
            after=StaticVisibility.from_scene(Flat(),scene,root)
            self.assertFalse(before.clear((1000,1920,7000),(1000,2080,7000)))
            self.assertTrue(after.clear((1000,1920,7000),(1000,2080,7000)))
            self.assertFalse(after.clear((800,2000,7000),(1000,2000,7000)))
            self.assertEqual(len(after.assets.get(self.path).shapes),2)
            with patch.object(after.assets,'indexed_model',side_effect=AssertionError('Live query performed I/O')), \
                 patch.object(after.assets,'build_index',side_effect=AssertionError('Live query rebuilt the index')):
                self.assertTrue(after.clear((1000,1920,7000),(1000,2080,7000)))
                self.assertIsNone(after.assets.get('Data/Scene/general/building/Unprepared_collision.xml'))

    def test_preparation_budget_falls_back_and_child_archive_paths_use_exact_key(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            child=self.path.replace('Own_Room_collision','Own_Room_glass_dm_collision')
            (root/'Scene_General_Building_Own_Room.sfc').write_bytes(sfc(collision_xml(),sfc_path_key(child)))
            library=CollisionAssets(root)
            report=library.prepare([child],max_shapes=1)
            self.assertEqual(report,dict(models=0,shapes=0,fallback_models=1))
            self.assertIsNone(library.get(child))
            self.assertIn('budget',library.failures[child.casefold()])

    def test_missing_wrong_key_and_bad_array_keep_conservative_fallback(self):
        for kind in ('missing','key','array'):
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder);raw=collision_xml()
                if kind=='array':raw=raw.replace(b'ArrayCount="2"',b'ArrayCount="3"')
                key=bytes(8) if kind in ('key','missing') else sfc_path_key(self.path)
                name='Other.sfc' if kind=='missing' else 'Scene_General_Building_Own_Room.sfc'
                (root/name).write_bytes(sfc(raw,key))
                library=CollisionAssets(root)
                self.assertIsNone(library.get(self.path))
                self.assertIn(self.path.casefold(),library.failures)

    def test_path_key_normalization_and_known_independent_asset_pairs(self):
        self.assertEqual(sfc_path_key(self.path),sfc_path_key(self.path.upper().replace('/','\\')))
        # Small factual record identifiers from two owned Thai asset families.
        self.assertEqual(sfc_path_key('Data/Scene/general/building/MJ_2floor_007_001_collision.xml').hex(),'356eed1dd2b6bdb2')
        self.assertEqual(sfc_path_key('Data/Scene/general/stone/KF_Rock_03_collision.xml').hex(),'9b4f1365856f7a18')

    def test_exact_key_finds_unrelated_archive_name_and_rejects_duplicate_owners(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data=sfc(collision_xml(),sfc_path_key(self.path))
            (root/'Other.sfc').write_bytes(data)
            library=CollisionAssets(root)
            self.assertEqual(len(library.get(self.path).shapes),2)
            (root/'Duplicate.sfc').write_bytes(data)
            library=CollisionAssets(root)
            self.assertIsNone(library.get(self.path))
            self.assertIn('duplicated',library.failures[self.path.casefold()])

    def test_last_record_for_same_key_wins_within_an_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);key=sfc_path_key(self.path)
            first=sfc(collision_xml(),key)
            broken=sfc(collision_xml().replace(b'ArrayCount="2"',b'ArrayCount="3"'),key)
            (root/'Own.sfc').write_bytes(first+broken[8:])
            library=CollisionAssets(root)
            self.assertIsNone(library.get(self.path))
            self.assertIn('count',library.failures[self.path.casefold()])

    def test_external_entities_and_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            raw=b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///unread">]>'+collision_xml()
            (root/'Scene_General_Building_Own_Room.sfc').write_bytes(sfc(raw,sfc_path_key(self.path)))
            library=CollisionAssets(root)
            self.assertIsNone(library.get(self.path))
            self.assertIsNone(library.get('Data/Scene/../../Own_Room_collision.xml'))

    def test_original_round_shape_attributes_use_explicit_radius_and_half_height(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            param=b'<mParam><mLocalPosition x="0" y="0" z="0"/><mLocalRotation x="0" y="0" z="0" w="1"/></mParam>'
            raw=(b'<NewObj Version="1"><PhysCollectionDesc><mActors IsStaticArray="0" ArrayCount="1">'
                 b'<mActors mUsage="PhysActorDesc::eSTATIC"><mCapsules IsStaticArray="0" ArrayCount="1">'
                 b'<mCapsules mRadius="10" mHalfHeight="30">'+param+
                 b'</mCapsules></mCapsules></mActors></mActors></PhysCollectionDesc></NewObj>')
            (root/'Scene_General_Building_Own_Room.sfc').write_bytes(sfc(raw,sfc_path_key(self.path)))
            library=CollisionAssets(root);model=library.get(self.path)
            self.assertIsNotNone(model)
            self.assertTrue(model.blocks((25,-100,0),(25,100,0)))
            self.assertFalse(model.blocks((45,-100,0),(45,100,0)))


if __name__=='__main__':unittest.main()
