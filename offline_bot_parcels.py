"""Session-local Thai death containers backed by the existing pickup logic."""
import math
import struct

from offline_ground_loot import GroundStack
from offline_inventory import Item


class BotParcels:
    def __init__(self, game, bots, ai):
        self.game, self.bots, self.ai = game, bots, ai
        self.parcels = {}
        self.owners = set()
        self.opened = set()

    def drop(self, uid):
        brain = self.ai.brains.get(uid)
        world = self.game.ground_loot
        if uid in self.owners or brain is None or not brain.equipped or world is None:
            return []
        if len(self.parcels) >= 4:
            return []
        entity = world.next_entity
        world.next_entity += 1
        position = self.bots.actors[uid]['position']
        items = {}
        inventory = self.game.inventory
        for template, kind, count, magazine in ((10201, 1, 1, brain.magazine),
                                                (30001, 3, brain.reserve, 0)):
            if not count:
                continue
            item = Item(kind, template, inventory.next_uid, count)
            inventory.next_uid += 1
            slot = len(items) + 1
            items[slot] = GroundStack(entity, position, item, magazine)
        self.parcels[entity] = (position, items)
        self.owners.add(uid)
        name = b'OfflineBotLoot\0'
        body = struct.pack('>IQI', 30201002, entity, len(name)) + name
        body += struct.pack('>I', 1) + b'\0' + struct.pack('>I', 1) + b'\0'
        body += struct.pack('>3iBfI', *position, 0, 0., 1)
        body += struct.pack('>IQB5I', 0, 0, 1, 0, 0, entity, 0, 0)
        body += bytes(4) + struct.pack('>IB', 0, 0)
        return [(0x821, body)]

    def contents(self, entity):
        _, items = self.parcels[entity]
        body = struct.pack('>II', entity, len(items))
        for slot, stack in items.items():
            body += struct.pack('>II', slot, stack.item.kind)
            body += struct.pack('>II', stack.item.template, stack.item.count)
            if stack.item.kind in (1, 2):
                body += bytes(4)
        return 0x3b61, body

    def handle(self, message, body):
        if message == 0xbce and len(body) in (16, 24):
            entity, owner = struct.unpack_from('>QQ', body)
            if entity not in self.parcels:
                return None
            position, _ = self.parcels[entity]
            if owner != self.game.actor_uid or math.dist(position, self.game.player_position) > 500:
                return []
            self.opened.add(entity)
            return [self.contents(entity)]
        if message != 0x3b63 or len(body) not in (33, 41):
            return None
        entity, slot = struct.unpack_from('>II', body)
        if entity not in self.parcels:
            return None
        position, items = self.parcels[entity]
        if entity not in self.opened or slot not in items:
            return [self.contents(entity)]
        world = self.game.ground_loot
        # Reuse the validated item transfer, distance, identity and capacity
        # checks without announcing a separate single-item ground object.
        virtual = world.next_entity
        world.next_entity += 1
        stack = items[slot]
        world.stacks[virtual] = GroundStack(virtual, position, stack.item, stack.magazine)
        request = struct.pack('>II', virtual, 0) + body[8:]
        try:
            replies = world.pickup(request, self.game.inventory, self.game.actor_uid,
                                   self.game.player_position,
                                   self.game.actor_ready and not self.game.seated and self.game.vitals.current > 0)
            if virtual in world.stacks:
                return [self.contents(entity)]
            del items[slot]
            notice = struct.pack('>II', entity, slot) + replies[-1][1][8:]
            return [replies[0], (0x3b64, notice), self.contents(entity)]
        finally:
            world.stacks.pop(virtual, None)
