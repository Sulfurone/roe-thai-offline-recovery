"""Exploration-time synthetic loot/land vehicles using own-client terrain.

This is a finite local scenario, not the original map's authored spawn data.
Heightfield checks cannot detect buildings, trees or other map props.
"""
import math
import random

from offline_ground_loot import MAX_GROUND_STACKS
from offline_inventory import Item
from offline_weapons import WEAPONS
from offline_motion import actor_motion
from offline_items import EXTRA_ITEMS
from offline_vehicles import LAND_VEHICLES
import struct


class WorldPopulation:
    CELL = 15000  # centimetres

    def __init__(self, control, terrain, seed=1, loot=True, vehicles=True, bots=None, clusters=8,
                 vehicle_clusters=3,extra_items=False):
        if type(clusters) is not int or not 1<=clusters<=16:
            raise ValueError('Population density must be 1..16 weapon/ammo pairs per region')
        if type(vehicle_clusters) is not int or not 1<=vehicle_clusters<=4:
            raise ValueError('Vehicle density must be 1..4 per region')
        self.control, self.terrain = control, terrain
        self.seed, self.loot, self.vehicles = seed, loot, vehicles
        self.visited = set()
        self.spots = []
        self.auto_vehicles = 0
        self.bots = bots
        self.clusters=clusters
        self.vehicle_clusters=vehicle_clusters
        self.extra_items=extra_items
        if bots is not None:
            control.peer_positions=bots.actors
        if hasattr(terrain,'spawn_spot'):
            control.placement_map=terrain

    def surface(self, x, y):
        if not 400 <= x <= 409200 or not 400 <= y <= 409200:
            return None
        heights = [self.terrain.height_at(x + dx, y + dy)
                   for dx, dy in ((0, 0), (-200, 0), (200, 0), (0, -200), (0, 200))]
        # Conservative dry-land floor, consistent with the existing Thai
        # ground scenario. This is not a recovered water-volume query.
        if any(h is None or not math.isfinite(h) or h < 6499.99 for h in heights):
            return None
        if max(heights) - min(heights) > 160:
            return None
        return round(heights[0])

    def choose_spot(self, position, rng, vehicle=False, peer=False):
        if hasattr(self.terrain, 'spawn_spot'):
            spot = self.terrain.spawn_spot(position,rng,
                'vehicle' if vehicle else 'peer' if peer else 'loot',self.spots)
            if spot is not None:
                self.spots.append(spot[:2])
            return spot
        x, y, _ = position
        for _ in range(48):
            angle = rng.uniform(0, math.tau)
            nearby = getattr(self.terrain, 'nearby_only', False)
            distance = (rng.uniform(350, 450) if vehicle else rng.uniform(100, 300)) if nearby else rng.uniform(
                3500 if vehicle else 1800, 8000 if vehicle else 5500)
            px, py = round(x + distance * math.cos(angle)), round(y + distance * math.sin(angle))
            height = self.surface(px, py)
            separation = (260 if vehicle else 150) if nearby else 500
            if height is None or any(math.hypot(px - a, py - b) < separation for a, b in self.spots):
                continue
            self.spots.append((px, py))
            return px, py, height + (100 if vehicle else 30)
        return None

    def observe(self, message, body):
        if message != 0x2a or not hasattr(self.terrain, 'observe') or self.control.gameplay.seated:
            return
        motion = actor_motion(body)
        if motion is None:
            return
        count = struct.unpack_from('>I', body)[0]
        event = body[4 + 19 * (count - 1) + 12] if len(body) != 16 else 0
        self.terrain.observe(motion[0], event)

    def tick(self):
        game = self.control.gameplay
        if not game or not game.actor_ready or game.seated:
            return []
        position = game.player_position
        ground = self.terrain.height_at(*position[:2])
        if ground is None or not math.isfinite(ground) or not -100 <= position[2] - ground <= 1500:
            return []  # do not populate during flight/early descent
        cell = position[0] // self.CELL, position[1] // self.CELL
        if cell in self.visited or len(self.visited) >= 1024:
            return self.bots.tick(self) if self.bots else []
        self.visited.add(cell)
        rng = random.Random((self.seed ^ cell[0] * 73856093 ^ cell[1] * 19349663) & (2**64 - 1))
        replies = []
        world = game.ground_loot
        if self.loot and world and world.announced:
            for _ in range(self.clusters):
                # Keep room for manual F6 spawning; picked items release slots.
                if len(world.stacks) > min(110, MAX_GROUND_STACKS - 2):
                    break
                spot = self.choose_spot(position, rng)
                if spot is None:
                    continue
                template = rng.choice(sorted(WEAPONS))
                spec = WEAPONS[template]
                gun = world.add(Item(spec.kind, template, game.inventory.next_uid, 1), spot, spec.capacity)
                game.inventory.next_uid += 1
                ammo = world.add(Item(3, spec.ammunition, game.inventory.next_uid, rng.randint(60, 120)),
                                 (spot[0] + 50, spot[1], spot[2]))
                game.inventory.next_uid += 1
                replies.extend((gun.spawn(), ammo.spawn()))
            if self.extra_items:
                groups=([i for i,v in EXTRA_ITEMS.items() if v.slot==11],
                        [i for i,v in EXTRA_ITEMS.items() if v.kind==5],
                        [i for i,v in EXTRA_ITEMS.items() if v.kind==4],
                        [i for i,v in EXTRA_ITEMS.items() if v.kind==7],
                        [i for i,v in EXTRA_ITEMS.items() if v.slot==10],
                        [i for i,v in EXTRA_ITEMS.items() if v.slot==12])
                for choices in groups:
                    for _ in range(2):
                        if len(world.stacks)>=112:
                            break
                        spot=self.choose_spot(position,rng)
                        if spot is None:
                            continue
                        template=rng.choice(choices)
                        spec=EXTRA_ITEMS[template]
                        quantity=rng.randint(2,5) if spec.kind==7 else 1
                        item=world.add(Item(spec.kind,template,game.inventory.next_uid,quantity),spot)
                        game.inventory.next_uid+=1
                        replies.append(item.spawn())
        if self.vehicles and self.control.vehicle_template is not None:
            for _ in range(self.vehicle_clusters):
                if self.auto_vehicles>=12 or len(self.control.vehicles)>=16:
                    break
                spot = self.choose_spot(position, rng, vehicle=True)
                if spot is not None:
                    replies.extend(self.control.spawn_vehicle(spot,rng.choice(sorted(LAND_VEHICLES)) if self.extra_items else 101))
                    self.auto_vehicles += 1
        if self.bots is not None:
            replies.extend(self.bots.spawn(self, position, rng))
        return replies
