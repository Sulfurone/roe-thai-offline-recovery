"""Opt-in synthetic loot bundle at a dead local bot's position.

Each entry reuses the existing finite 0x821 ground entity; the original death
parcel/container slot-list protocol is not encoded. The weapon, its loaded
magazine and the remaining reserve come from the local BotAI loadout, so the
bundle is conserved and appears at most once per peer. This is not original
drop distribution, death-box rules or match rewards.
"""
from offline_ground_loot import MAX_GROUND_STACKS
from offline_inventory import Item
from offline_weapons import AMMO_STACK_MAX, WEAPONS


class DeathLoot:
    def __init__(self, gameplay, bots, ai):
        if gameplay is None or bots is None or ai is None:
            raise ValueError('Death loot needs a gameplay session, a peer roster and local AI')
        self.gameplay, self.bots, self.ai = gameplay, bots, ai
        self.last = None

    def packets(self, uid):
        self.last = None
        if type(uid) is not int or not 0 < uid < 2 ** 64:
            raise ValueError('Invalid death owner')
        g = self.gameplay
        world = g.ground_loot if g is not None else None
        inventory = g.inventory if g is not None else None
        actor = self.bots.actors.get(uid)
        brain = self.ai.brains.get(uid)
        # Loot is only announced with the rest of the world, and only for a
        # peer whose equipment message was actually sent.
        if world is None or inventory is None or not world.announced:
            return []
        if actor is None or brain is None or not brain.equipped:
            return []
        weapon = getattr(brain, 'weapon', 10201)
        spec = WEAPONS.get(weapon)
        if (spec is None or type(brain.magazine) is not int
                or not 0 <= brain.magazine <= spec.capacity):
            return []
        reserve = max(0, min(int(brain.reserve), AMMO_STACK_MAX))
        count = 1 + bool(reserve)
        position = actor.get('position')
        if (not isinstance(position, tuple) or len(position) != 3
                or any(type(value) is not int or abs(value) >= 2_000_000 for value in position)):
            return []
        if (len(world.stacks) > MAX_GROUND_STACKS - count
                or world.next_entity + count > 2 ** 32
                or inventory.next_uid + count >= 2 ** 64):
            self.last = dict(uid=uid, dropped=False, reason='capacity')
            return []
        x, y, z = position
        stack = world.add(Item(spec.kind, weapon, inventory.next_uid, 1), position,
                          brain.magazine)
        replies = [stack.spawn()]
        entities = [stack.entity]
        inventory.next_uid += 1
        if reserve:
            ammo = world.add(Item(3, spec.ammunition, inventory.next_uid, reserve),
                             (x + 100, y, z))
            replies.append(ammo.spawn())
            entities.append(ammo.entity)
            inventory.next_uid += 1
        self.last = dict(uid=uid, dropped=True, weapon=weapon, magazine=brain.magazine,
                         ammunition=spec.ammunition, reserve=reserve, entities=entities,
                         position=list(position), original_parcel=False)
        return replies
