import math
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from offline_collision import Instance,Model,primitive
from offline_dynamic_doors import Door,DynamicDoors,read_doors
from offline_doors import DoorState


class DoorCollisionTests(unittest.TestCase):
    def test_closed_open_both_sides_and_reclose_follow_same_native_state_dictionary(self):
        model=Model([primitive('box',(50,0,100),extents=(50,3,100))])
        door=Door(67,Instance('own.xml',(0,0,7000),(0,0,0),1),(0,-math.pi/2,math.pi/2),0)
        geometry=DynamicDoors([door],SimpleNamespace(get=lambda path:model))
        state=DoorState();geometry.states=state.states
        across=((50,-30,7100),(50,30,7100))
        self.assertTrue(geometry.blocks(*across))
        for value,y in ((1,-50),(2,50)):
            replies=state.handle(struct.pack('>II',67,value))
            self.assertEqual(replies[0][0],0x6f55)
            self.assertFalse(geometry.blocks(*across))
            self.assertTrue(geometry.blocks((-30,y,7100),(30,y,7100)))
        state.handle(struct.pack('>II',67,0))
        self.assertTrue(geometry.blocks(*across))

    def test_unrelated_or_invalid_requests_do_not_change_the_door_query(self):
        model=Model([primitive('box',extents=(50,3,100))])
        door=Door(67,Instance('own.xml',(0,0,7000),(0,0,0),1),(0,-1.68,1.68),0)
        geometry=DynamicDoors([door],SimpleNamespace(get=lambda path:model))
        state=DoorState();geometry.states=state.states
        state.handle(struct.pack('>II',68,1))
        self.assertEqual(state.handle(struct.pack('>II',67,3)),[])
        self.assertTrue(geometry.blocks((25,-30,7000),(25,30,7000)))

    def test_catalogue_uses_three_original_rotations_and_does_not_treat_glass_as_a_door(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'scene.xml'
            row=('<mTable mID="67" mEntityFullName="data.world.EU_KillZone_2048.MJ_door_001_DM_mesh123a" '
                'mPosX="0" mPosY="0" mPosZ="7000" mRotateX="0" mRotateY="0" mRotateZ="0" mScale="1">'
                '<mSwitcherStatus mType="EStatus_REVERSIBLE" mSwitcherType="ESwitcher_DOOR" mStatus="0">'
                '<mDoorRelativeZRotation ArrayCount="3"><mDoorRelativeZRotation v="0"/>'
                '<mDoorRelativeZRotation v="-1.68"/><mDoorRelativeZRotation v="1.68"/>'
                '</mDoorRelativeZRotation></mSwitcherStatus></mTable>')
            path.write_text('<r ObjName="x.eu_killzone_2048.ClientTable.EntityStatusInPxScene">'+row+'</r>')
            doors=read_doors(path)
            self.assertEqual(len(doors),1)
            self.assertEqual(doors[0].rotations,(0,-1.68,1.68))
            self.assertTrue(doors[0].instance.path.endswith('MJ_door_001_DM_collision.xml'))
            path.write_text(path.read_text().replace('MJ_door_001_DM','MJ_glass_001_DM'))
            self.assertEqual(read_doors(path),[])


if __name__=='__main__':unittest.main()
