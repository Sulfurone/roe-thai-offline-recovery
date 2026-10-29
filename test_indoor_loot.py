import math
import random
import unittest
import threading
from types import SimpleNamespace
from offline_collision import Instance,Model,primitive
from offline_visibility import StaticVisibility
from offline_indoor_loot import IndoorFloors,vertical_interval
from offline_client_map import ThaiClientMap


def building(angles=(0,0,0),scale=1):
    model=Model([primitive('box',(0,0,z),extents=(500,450,10)) for z in (0,320,640)]
                +[primitive('box',(0,0,120),extents=(40,40,120))])
    instance=Instance('house',(10000,12000,8000),angles,scale)
    bounds=(10000,12000,8200,1200)
    assets=SimpleNamespace(get=lambda path:model)
    vis=StaticVisibility(SimpleNamespace(height_at=lambda x,y:7990),[bounds],{bounds:[instance]},assets)
    return IndoorFloors(vis)


class IndoorLootTests(unittest.TestCase):
    def test_background_sampler_does_not_block_the_game_thread(self):
        finder=IndoorFloors(None,background=True)
        entered=threading.Event();release=threading.Event()
        house=(10000,12000,800,8000)
        def compute(row):
            entered.set()
            if not release.wait(3):raise ValueError('Test worker was not released')
            finder.cache[row]=((10000,12000,8340),)
            return finder.cache[row]
        finder.candidates=compute
        try:
            self.assertEqual(finder.nearby((10000,12000,8020),[house]),[])
            self.assertTrue(entered.wait(1))
            self.assertEqual(finder.nearby((10000,12000,8020),[house]),[])
            release.set();finder.jobs[house].result(timeout=2)
            self.assertEqual(finder.nearby((10000,12000,8020),[house]),[(10000,12000,8340)])
        finally:
            release.set();finder.close()

    def test_delayed_floors_populate_an_already_visited_cell_once(self):
        from control_actions import ControlSession
        from offline_population import WorldPopulation
        from test_control_panel import ready_game
        game=ready_game();game.player_position=(10000,12000,8020)
        game.ground_loot.stacks.clear()
        terrain=ThaiClientMap(SimpleNamespace(width=409600,height_at=lambda x,y:8000),b'',[],[])
        class Ready:
            rows=[]
            def ready_buildings(self,position,houses):return self.rows
            def nearby(self,position,houses):return [p for _,points in self.rows for p in points]
        terrain.indoor_floors=Ready()
        pop=WorldPopulation(ControlSession(game),terrain,vehicles=False,extra_items=True)
        pop.visited.add((0,0))
        self.assertEqual(pop.tick(),[])
        terrain.indoor_floors.rows=[((10000,12000,800,8000),((9800,12000,8020),(10000,12000,8340),(10400,12000,8340)))]
        replies=pop.tick()
        self.assertEqual([m for m,_ in replies],[0x821]*6)
        self.assertTrue(all(s.position[2]==8340 for s in game.ground_loot.stacks.values()))
        self.assertEqual(pop.tick(),[])
        self.assertTrue(pop.auto_item_ids==set(game.ground_loot.stacks))

    def test_two_floors_have_headroom_and_roof_is_excluded(self):
        finder=building()
        points=finder.candidates((10000,12000,800,8000))
        self.assertEqual({p[2] for p in points},{8020,8340})
        self.assertTrue(all(abs(p[0]-10000)>65 or abs(p[1]-12000)>65 for p in points if p[2]==8020))
        self.assertEqual(finder.candidates((10000,12000,800,8000)),points)

    def test_rotated_scaled_building_uses_world_surfaces(self):
        points=building((0,0,math.pi/4),1.2).candidates((10000,12000,900,8000))
        self.assertEqual({p[2] for p in points},{8022,8406})

    def test_low_ceiling_and_missing_assets_do_not_invent_a_floor(self):
        instance=Instance('low',(0,0,8000),(0,0,0),1)
        model=Model([primitive('box',(0,0,z),extents=(500,500,10)) for z in (0,150)])
        bound=(0,0,8000,1000)
        vis=StaticVisibility(None,[bound],{bound:[instance]},SimpleNamespace(get=lambda p:model))
        self.assertEqual(IndoorFloors(vis).candidates((0,0,600,8000)),())
        vis.assets=SimpleNamespace(get=lambda p:None)
        self.assertEqual(IndoorFloors(vis).candidates((0,0,600,8000)),())

    def test_sampling_reaches_upstairs_and_never_falls_back_to_roof(self):
        data=ThaiClientMap(SimpleNamespace(width=409600),b'',[(10000,12000,800,8000)],[])
        data.indoor_floors=building()
        heights=set()
        for seed in range(20):
            spot=data.spawn_spot((10500,12500,8020),random.Random(seed),'loot',[])
            self.assertIsNotNone(spot);heights.add(spot[2])
        self.assertEqual(heights,{8020,8340})


if __name__=='__main__':unittest.main()
