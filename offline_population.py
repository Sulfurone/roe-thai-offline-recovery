"""Exploration-time synthetic loot/land vehicles using own-client terrain.

This is a finite local scenario, not the original map's authored spawn data.
Heightfield checks cannot detect buildings, trees or other map props.
"""
import math
import random
import time

from offline_ground_loot import MAX_GROUND_STACKS
from offline_inventory import Item
from offline_weapons import WEAPONS
from offline_motion import actor_motion
from offline_items import SPAWNABLE_EXTRA_ITEMS as EXTRA_ITEMS
from offline_vehicles import SPAWNABLE_LAND_VEHICLES as LAND_VEHICLES
import struct


class WorldPopulation:
    CELL = 15000  # centimetres
    UNLOAD_DISTANCE=45000
    AUTO_GROUND_CAP=384
    EXTRA_PER_GROUP=4

    def __init__(self, control, terrain, seed=1, loot=True, vehicles=True, bots=None, clusters=16,
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
        self.auto_item_ids=set()
        self.auto_vehicle_ids=set()
        self.vehicle_cells={}
        self.upstairs_houses=set()
        self.bots = bots
        self.peer_visibility=None
        self.peer_retry_at=0
        self.peer_attempts=0
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
            for _ in range(12 if peer and self.peer_visibility else 1):
                spot = self.terrain.spawn_spot(position,rng,
                    'vehicle' if vehicle else 'peer' if peer else 'loot',self.spots)
                if spot is None:return None
                if peer and self.peer_visibility and self.peer_visibility.walk(spot,spot) is None:continue
                self.spots.append(spot[:2])
                return spot
            return None
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
            if peer and self.peer_visibility and self.peer_visibility.walk((px,py,height+5),(px,py,height+5)) is None:
                continue
            self.spots.append((px, py))
            return px, py, height + (100 if vehicle else 30)
        return None

    def try_peers(self,position,rng=None):
        if self.bots is None or len(self.bots.actors)>=self.bots.count:return []
        now=time.monotonic()
        if now<self.peer_retry_at:return []
        self.peer_retry_at=now+3
        if rng is None:
            rng=random.Random((self.seed^int(position[0])*73856093^int(position[1])*19349663
                               ^self.peer_attempts*83492791)&(2**64-1))
        self.peer_attempts+=1
        return self.bots.spawn(self,position,rng)

    def observe(self, message, body):
        if message != 0x2a or not hasattr(self.terrain, 'observe') or self.control.gameplay.seated:
            return
        motion = actor_motion(body)
        if motion is None:
            return
        count = struct.unpack_from('>I', body)[0]
        event = body[4 + 19 * (count - 1) + 12] if len(body) != 16 else 0
        self.terrain.observe(motion[0], event)

    def upstairs(self,position):
        """Add bounded upper-floor clusters when background geometry is ready.

        Runs on already visited cells too. Delayed collision work must never
        leave upstairs permanently empty merely because landing spawned first.
        """
        finder=getattr(self.terrain,'indoor_floors',None)
        game=self.control.gameplay
        world=game.ground_loot
        if finder is None or not self.loot or world is None or not world.announced:return []
        replies=[]
        for house,points in finder.ready_buildings(position,self.terrain.houses):
            if house in self.upstairs_houses or not points:continue
            lowest=min(p[2] for p in points)
            choices=[p for p in points if p[2]>=lowest+200]
            rng=random.Random(self.seed^round(house[0])^round(house[1])*73856093)
            rng.shuffle(choices)
            generated=0
            for spot in choices:
                if generated>=4 or len(world.stacks)>self.AUTO_GROUND_CAP-(3 if self.extra_items else 2):break
                if any(math.dist(spot,s.position)<150 for s in world.stacks.values()):continue
                template=rng.choice(sorted(WEAPONS));spec=WEAPONS[template]
                gun=world.add(Item(spec.kind,template,game.inventory.next_uid,1),spot,spec.capacity)
                game.inventory.next_uid+=1
                ammo=world.add(Item(3,spec.ammunition,game.inventory.next_uid,rng.randint(60,120)),
                               (spot[0]+50,spot[1],spot[2]))
                game.inventory.next_uid+=1
                stacks=[gun,ammo]
                if self.extra_items:
                    template=rng.choice(sorted(EXTRA_ITEMS));spec=EXTRA_ITEMS[template]
                    extra=world.add(Item(spec.kind,template,game.inventory.next_uid,1),
                                    (spot[0],spot[1]+45,spot[2]))
                    game.inventory.next_uid+=1;stacks.append(extra)
                self.auto_item_ids.update(s.entity for s in stacks)
                replies.extend(s.spawn() for s in stacks)
                generated+=1
            # Do not mark full-capacity worlds: revisit after the working set
            # unloads or pickups make room. Empty geometry does not get retried.
            if generated or not choices:self.upstairs_houses.add(house)
        return replies

    def tick(self):
        game = self.control.gameplay
        if (not game or not game.actor_ready
                or game.seated and self.control.active_vehicle is None):
            return []
        if (game.require_self_position_for_drop and not game.has_fresh_self_position()
                and self.control.active_vehicle is None):
            return []
        position = game.player_position
        ground = self.terrain.height_at(*position[:2])
        if ground is None or not math.isfinite(ground) or not -100 <= position[2] - ground <= 1500:
            return []  # do not populate during flight/early descent
        replies=self.unload_far(position)+self.upstairs(position)
        cell = position[0] // self.CELL, position[1] // self.CELL
        if cell in self.visited or len(self.visited) >= 1024:
            spawned=self.try_peers(position)
            vehicles=self.try_vehicles(position,random.Random(self.seed^cell[0]*73856093^cell[1]*19349663),cell)
            return replies+vehicles+spawned+(self.bots.tick(self) if self.bots and not spawned else [])
        self.visited.add(cell)
        rng = random.Random((self.seed ^ cell[0] * 73856093 ^ cell[1] * 19349663) & (2**64 - 1))
        world = game.ground_loot
        if self.loot and world and world.announced:
            loot_spots=[]
            for _ in range(self.clusters):
                # Keep room for manual F6 spawning; picked items release slots.
                if len(world.stacks) > min(self.AUTO_GROUND_CAP-2, MAX_GROUND_STACKS - 2):
                    break
                spot = self.choose_spot(position, rng)
                if spot is None:
                    continue
                loot_spots.append(spot)
                template = rng.choice(sorted(WEAPONS))
                spec = WEAPONS[template]
                gun = world.add(Item(spec.kind, template, game.inventory.next_uid, 1), spot, spec.capacity)
                game.inventory.next_uid += 1
                ammo = world.add(Item(3, spec.ammunition, game.inventory.next_uid, rng.randint(60, 120)),
                                 (spot[0] + 50, spot[1], spot[2]))
                game.inventory.next_uid += 1
                self.auto_item_ids.update((gun.entity,ammo.entity))
                replies.extend((gun.spawn(), ammo.spawn()))
            if self.extra_items:
                extra_number=0
                groups=([i for i,v in EXTRA_ITEMS.items() if v.slot==11],
                        [i for i,v in EXTRA_ITEMS.items() if v.kind==5],
                        [i for i,v in EXTRA_ITEMS.items() if v.kind==4],
                        [i for i,v in EXTRA_ITEMS.items() if v.kind==7],
                        [i for i,v in EXTRA_ITEMS.items() if v.slot==10],
                        [i for i,v in EXTRA_ITEMS.items() if v.slot==12])
                for choices in groups:
                    for number in range(self.EXTRA_PER_GROUP):
                        if len(world.stacks)>=self.AUTO_GROUND_CAP:
                            break
                        if not loot_spots:
                            spot=self.choose_spot(position,rng)
                            if spot is None:continue
                            loot_spots.append(spot)
                        # Reuse verified indoor floors. A sparse residential
                        # region can exhaust all entrance candidates on guns,
                        # otherwise silently starving medicine/armor/optics.
                        anchor=loot_spots[extra_number%len(loot_spots)]
                        angle=extra_number*2.399963229728653
                        radius=35+5*((extra_number//len(loot_spots))%3)
                        spot=(anchor[0]+round(radius*math.cos(angle)),
                              anchor[1]+round(radius*math.sin(angle)),anchor[2])
                        extra_number+=1
                        # Each region attempts a common M4-compatible optic;
                        # two unconstrained draws could both be non-optics.
                        template=(40305 if number==0 and 40305 in choices else
                                  rng.choice((40303,40304)) if number==1 and 40305 in choices else rng.choice(choices))
                        spec=EXTRA_ITEMS[template]
                        quantity=rng.randint(2,5) if spec.kind==7 else 1
                        item=world.add(Item(spec.kind,template,game.inventory.next_uid,quantity),spot)
                        game.inventory.next_uid+=1
                        self.auto_item_ids.add(item.entity)
                        replies.append(item.spawn())
        replies.extend(self.try_vehicles(position,rng,cell))
        if self.bots is not None:
            replies.extend(self.try_peers(position,rng))
        return replies

    def try_vehicles(self,position,rng,cell):
        replies=[]
        if self.vehicles and self.control.vehicle_template is not None:
            for _ in range(self.vehicle_clusters-self.vehicle_cells.get(cell,0)):
                if self.auto_vehicles>=12 or len(self.control.vehicles)>=16:
                    break
                spot = self.choose_spot(position, rng, vehicle=True)
                if spot is not None:
                    replies.extend(self.control.spawn_vehicle(spot,rng.choice(sorted(LAND_VEHICLES)) if self.extra_items else 101))
                    self.auto_vehicle_ids.add(self.control.next_vehicle_uid-1)
                    self.auto_vehicles += 1
                    self.vehicle_cells[cell]=self.vehicle_cells.get(cell,0)+1
        return replies

    def unload_far(self,position):
        """Bound the nearby working set, preserving manual loot and the driver.

        Re-entering an unloaded region can populate it again. UID allocators
        remain monotonic; removing a car must never reuse another car's UID.
        """
        replies=[]
        world=self.control.gameplay.ground_loot
        if world is not None:
            self.auto_item_ids.intersection_update(world.stacks)
            for entity in sorted(self.auto_item_ids):
                stack=world.stacks[entity]
                if math.dist(position[:2],stack.position[:2])>self.UNLOAD_DISTANCE:
                    replies.append((0x82b,struct.pack('>Q',entity)))
                    del world.stacks[entity]
                    self.auto_item_ids.remove(entity)
        self.auto_vehicle_ids.intersection_update(self.control.vehicles)
        for uid in sorted(self.auto_vehicle_ids):
            car=self.control.vehicles[uid]
            if (uid!=self.control.active_vehicle and not car.seated
                    and math.dist(position[:2],car.vehicle_position[:2])>self.UNLOAD_DISTANCE):
                replies.append((0x654c,struct.pack('>Q',uid)))
                del self.control.vehicles[uid]
                self.auto_vehicle_ids.remove(uid)
        self.auto_vehicles=len(self.auto_vehicle_ids)
        self.spots=[p for p in self.spots if math.dist(position[:2],p)<=self.UNLOAD_DISTANCE]
        self.visited={cell for cell in self.visited
                      if math.dist(position[:2],((cell[0]+.5)*self.CELL,(cell[1]+.5)*self.CELL))
                      <=self.UNLOAD_DISTANCE+2*self.CELL}
        self.vehicle_cells={cell:count for cell,count in self.vehicle_cells.items() if cell in self.visited}
        return replies
