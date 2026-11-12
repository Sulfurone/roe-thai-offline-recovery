"""Session-local Thai death containers backed by the existing pickup logic."""
import math
import struct

from offline_ground_loot import GroundStack,PICKUP_DISTANCE
from offline_inventory import Item
from offline_bot_ai import BOT_COMBAT_RESERVE
from offline_bots import BotRoster
from offline_items import SPAWNABLE_EXTRA_ITEMS
from offline_weapons import AMMUNITION,WEAPONS,is_weapon


class BotParcels:
    def __init__(self, game, bots, ai):
        self.game, self.bots, self.ai = game, bots, ai
        self.parcels = {}
        self.owners = set()
        self.opened = set()

    def drop(self, uid):
        world = self.game.ground_loot
        if uid in self.owners or uid not in self.bots.actors or world is None:
            return []
        if len(self.parcels) >= BotRoster.MAX_COUNT or world.next_entity >= 2**32:
            return []
        loadout = self.ai.loadouts[uid]
        brain = self.ai.brains.get(uid)
        primary,secondary = WEAPONS[loadout.primary],WEAPONS[loadout.secondary]
        supplies = dict(loadout.supplies)
        supplies[primary.ammunition] += brain.reserve if brain is not None else BOT_COMBAT_RESERVE
        loot = [(loadout.primary, primary.kind, 1, brain.magazine if brain is not None else primary.capacity),
                (loadout.secondary, secondary.kind, 1, secondary.capacity)]
        loot.extend((template,3 if template in AMMUNITION else SPAWNABLE_EXTRA_ITEMS[template].kind,count,0)
                    for template,count in supplies.items())
        entity = world.next_entity
        world.next_entity += 1
        position = self.bots.actors[uid]['position']
        items = {}
        inventory = self.game.inventory
        for template, kind, count, magazine in loot:
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
            # The native parcel list uses kinds 1/2 for guns and the
            # generic two-word variant 3 for every other template.
            weapon = is_weapon(stack.item)
            kind = stack.item.kind if weapon else 3
            body += struct.pack('>4I',slot,kind,stack.item.template,stack.item.count)
            if weapon:
                body += bytes(4)
        return 0x3b61, body

    def handle(self, message, body):
        if message == 0xbce and len(body) in (16, 24):
            entity, owner = struct.unpack_from('>QQ', body)
            if entity not in self.parcels:
                return None
            position, _ = self.parcels[entity]
            feet = self.game.self_position if self.game.has_fresh_self_position() else self.game.player_position
            if (owner != self.game.actor_uid or not self.game.actor_ready or self.game.seated
                    or not self.game.vitals.current or math.dist(position,feet)>PICKUP_DISTANCE):
                return []
            self.opened.add(entity)
            return [self.contents(entity)]
        if message != 0x3b63 or len(body) not in (33, 41):
            return None
        entity, slot = struct.unpack_from('>II', body)
        if entity not in self.parcels:
            return None
        _, items = self.parcels[entity]
        if entity not in self.opened or slot not in items:
            return [self.contents(entity)]
        world = self.game.ground_loot
        # Temporarily expose this slot to the normal gameplay pickup path.
        # It also selects the first equipped gun and refreshes ammo state.
        world.stacks[entity] = items[slot]
        request = struct.pack('>II',entity,0) + body[8:]
        try:
            replies = self.game.handle(0x3b63,request)
            if entity in world.stacks:
                return [self.contents(entity)]
            del items[slot]
            notice = struct.pack('>II', entity, slot) + replies[-1][1][8:]
            return [replies[0], (0x3b64, notice), self.contents(entity)]
        finally:
            world.stacks.pop(entity,None)
