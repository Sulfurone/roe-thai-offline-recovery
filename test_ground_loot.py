from pathlib import Path
import struct
import unittest
from offline_gameplay import OfflineGameplay,TYPED_ACTOR_UID
from offline_inventory import Item,AMMO_TEMPLATE
from offline_ground_loot import GroundStack


def request(entity=0x400001,slot=0,owner=0,container=0,destination=0,automatic=1,
            camera=(325800,271700,6488)):
    return struct.pack('>IIQBHB3iB',entity,slot,owner,container,destination,automatic,*camera,0)


def drop(quantity=20,owner=0,container=2,slot=0,current=1):
    return struct.pack('>BBHHQB',2,container,slot,quantity,owner,current)


class GroundLootTests(unittest.TestCase):
    def ready(self,reserve=120):
        game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,reserve=reserve,
                             actor_uid=TYPED_ACTOR_UID)
        game.handle(0x2a,struct.pack('>I3i',1,325800,271700,6488))
        return game

    def test_spawn_matches_original_native_writer_fixture(self):
        stack=GroundStack(0x400001,(325950,271700,6501),Item(3,AMMO_TEMPLATE,0x100103,60))
        self.assertEqual(stack.spawn()[1],(Path(__file__).parent/'private/typed-gameplay/loot-ammo-candidate.bin').read_bytes())
        game=self.ready()
        self.assertEqual(game.handle(0x2a,struct.pack('>I3i',2,325800,271700,6488)),[])

    def test_pickup_and_partial_drop_repickup_conserve_items_and_ammo(self):
        game=self.ready()
        replies=game.handle(0x3b63,request()+bytes(8))
        self.assertEqual([m for m,_ in replies],[0x3e82,0x82b,0x3b64])
        self.assertEqual(game.reserve,180)
        self.assertEqual(game.ground_loot.stacks,{})
        replies=game.handle(0x3e80,drop()+bytes(8))
        self.assertEqual([m for m,_ in replies],[0x821,0x3e82,0x3e81,0x4a0])
        self.assertEqual(game.reserve,160)
        stack=next(iter(game.ground_loot.stacks.values()))
        self.assertEqual(stack.position,game.player_position)
        self.assertEqual(stack.item.count,20)
        self.assertNotEqual(stack.item.uid,game.inventory.items[2,0].uid)
        game.handle(0x3b63,request(stack.entity))
        self.assertEqual((game.reserve,game.magazine),(180,30))
        before=game.inventory.snapshot(game.magazine,game.selected_slot)
        self.assertEqual(game.handle(0x3b63,request(stack.entity))[0][0],0x3b66)
        self.assertEqual(game.inventory.snapshot(game.magazine,game.selected_slot),before)

    def test_full_drop_and_explicit_empty_destination_preserve_identity(self):
        game=self.ready()
        original=game.inventory.items[2,0]
        game.handle(0x3e80,drop(120,owner=TYPED_ACTOR_UID))
        stack=game.ground_loot.stacks[0x400002]
        self.assertEqual(stack.item,original)
        self.assertNotIn((2,0),game.inventory.items)
        game.handle(0x3b63,request(stack.entity,owner=TYPED_ACTOR_UID,container=2,destination=8,automatic=0))
        self.assertEqual(game.inventory.items[2,8],original)

    def test_invalid_requests_do_not_mutate_world_or_inventory(self):
        game=self.ready()
        before=game.inventory.snapshot(30,1)
        world=dict(game.ground_loot.stacks)
        for body in [request(owner=123),request(slot=5),request(entity=0x400009),
                     request(automatic=2),request(container=1,destination=2,automatic=0),
                     request(destination=128,container=2,automatic=0),request()[:-1]]:
            game.handle(0x3b63,body)
            self.assertEqual(game.inventory.snapshot(30,1),before)
            self.assertEqual(game.ground_loot.stacks,world)
        for body in [drop(121),drop(owner=123),drop(container=1,slot=1,quantity=2),
                     drop(current=0),drop()[:-1]]:
            game.handle(0x3e80,body)
            self.assertEqual(game.inventory.snapshot(30,1),before)
            self.assertEqual(game.ground_loot.stacks,world)
        game.seated=True
        self.assertEqual(game.handle(0x3b63,request())[0][0],0x3b66)
        game.seated=False
        game.player_position=(0,0,6488)
        self.assertEqual(game.handle(0x3b63,request(camera=(0,0,6488)))[0][0],0x3b66)
        self.assertEqual(game.inventory.snapshot(30,1),before)

    def test_live_camera_allows_nearby_pickup_without_moving_actor_or_losing_limits(self):
        game=self.ready()
        game.player_position=(325300,271700,6488)
        # Synthetic stale walking keyframe, with the live camera by the item.
        for camera in ((0,0,0),(2000000,271700,6488),(320000,271700,6638)):
            replies=game.handle(0x3b63,request(camera=camera))
            self.assertEqual(replies[0][0],0x3b66)
            self.assertEqual(game.ground_loot.last_rejection['reason'],'distance')
            self.assertEqual(game.reserve,120)
        replies=game.handle(0x3b63,request(camera=(325800,271700,6638)))
        self.assertEqual([m for m,_ in replies],[0x3e82,0x82b,0x3b64])
        self.assertEqual(game.reserve,180)
        self.assertEqual(game.player_position,(325300,271700,6488))
        self.assertIsNone(game.ground_loot.last_rejection)

    def test_actual_client_zero_quantity_drops_the_whole_item(self):
        game=self.ready()
        weapon=game.inventory.items[1,1]
        actual=bytes.fromhex('020100010000000000000000000001')
        replies=game.handle(0x3e80,actual)
        self.assertEqual([message for message,_ in replies],[0x821,0x3e82,0x3e81,0x4a0])
        self.assertNotIn((1,1),game.inventory.items)
        self.assertEqual((game.ground_loot.stacks[0x400002].item,game.ground_loot.stacks[0x400002].magazine),(weapon,30))
        ammo=game.inventory.items[2,0]
        replies=game.handle(0x3e80,drop(0))
        self.assertEqual(replies[0][0],0x821)
        self.assertNotIn((2,0),game.inventory.items)
        self.assertEqual(game.ground_loot.stacks[0x400003].item,ammo)

    def test_capacity_limit_rejects_pickup_without_removing_ground_stack(self):
        game=self.ready(reserve=990)
        self.assertEqual(game.handle(0x3b63,request(container=2,destination=0,automatic=0))[0][0],0x3b66)
        self.assertEqual(game.reserve,990)
        self.assertEqual(len(game.ground_loot.stacks),1)
        self.assertEqual(game.handle(0x3b63,request())[0][0],0x3e82)
        self.assertEqual((game.inventory.items[2,0].count,game.inventory.items[2,1].count),(990,60))

    def test_persistent_or_disabled_inventory_cannot_enable_ephemeral_world(self):
        for kwargs in ({},{'inventory_enabled':True,'state_file':Path('unused.json')}):
            with self.assertRaises(ValueError):
                OfflineGameplay(ground_loot_enabled=True,**kwargs)


if __name__=='__main__':
    unittest.main()
