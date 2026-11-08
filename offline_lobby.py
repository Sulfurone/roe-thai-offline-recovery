"""Original Thai lobby packets and a separate, local wardrobe inventory.

No matchmaking service or recovered account ownership is implied. Fresh
profiles receive a small local clothing collection and warehouse samples.
The game inventory (owner flag 1) is never read or changed here.
"""
import json
from pathlib import Path
import struct
from offline_inventory import Item, EMPTY

# ItemTable row121: category20, sex0, a single original equipment position.
CLOTHES = {
    15: (1050024, 1050001, 1051001, 1052001),
    16: (1060013, 1060001, 1061001, 1062001),
    17: (1070004, 1070001, 1071001, 1072001),
    18: (1080011, 1080001, 1081001, 1082001),
    19: (1090005, 1090001, 1091001, 1092001),
}
POSITIONS = {template: slot for slot, values in CLOTHES.items() for template in values}
CRATES = frozenset((2010000, 2010001))


def validate_team(body):
    """Validate the bounded solo/membership wire before changing its type."""
    if len(body) < 32 or struct.unpack_from('>I', body)[0]:
        raise ValueError('Need a successful original Thai team template')
    count = struct.unpack_from('>I', body, 28)[0]
    if not 1 <= count <= 4:
        raise ValueError('Team template member count is invalid')
    offset = 32
    for _ in range(count):
        if offset + 12 > len(body):
            raise ValueError('Truncated team member')
        length = struct.unpack_from('>I', body, offset + 8)[0]
        offset += 12
        if not 1 <= length <= 128 or offset + length + 12 > len(body):
            raise ValueError('Invalid team name length')
        name = body[offset:offset + length]
        if not name.endswith(b'\0') or b'\0' in name[:-1]:
            raise ValueError('Invalid team name')
        offset += length + 12
    if offset != len(body):
        raise ValueError('Unknown trailing team layout')


class LobbyInventory:
    def __init__(self):
        self.items = {}
        uid, bag_slot = 0x1d00000000100000, 0
        for slot, values in CLOTHES.items():
            for index, template in enumerate(values):
                key = (1, slot) if index == 0 else (2, bag_slot)
                self.items[key] = Item(20, template, uid, 1)
                uid += 1
                if index:
                    bag_slot += 1
        for slot, template in enumerate(sorted(CRATES)):
            self.items[4, slot] = Item(8, template, uid, 3)
            uid += 1

    @staticmethod
    def fits(key, item):
        container, slot = key
        return (container == 1 and POSITIONS.get(item.template) == slot
                or container == 2 and 0 <= slot < 128 and item.template in POSITIONS
                or container == 4 and 0 <= slot < 128 and item.template in CRATES)

    def full_body(self):
        body = struct.pack('>I', len(self.items))
        for (container, slot), item in sorted(self.items.items()):
            body += bytes((container, slot)) + item.wire()
        return body + bytes(9)  # owner flag 0: lobby, never the game bag

    @staticmethod
    def reply(error=0, template=0):
        return 0x3e81, struct.pack('>BIIB', 1, error, template, 0)

    def transfer(self, body):
        if len(body) not in (10, 18):
            return [], False
        command, src, src_slot, dst, dst_slot, quantity, owner = struct.unpack('>BBHBHHB', body[:10])
        if command != 1 or owner != 0:
            return [], False
        source, destination = (src, src_slot), (dst, dst_slot)
        item, target = self.items.get(source), self.items.get(destination)
        if (quantity != 1 or item is None or item.template not in POSITIONS
                or not self.fits(destination, item)
                or target is not None and not self.fits(source, target)):
            return [self.reply(1)], False
        if source == destination:
            return [self.reply(template=item.template)], False
        updated = dict(self.items)
        updated[destination] = item
        if target is None:
            del updated[source]
        else:
            updated[source] = target
        delta = bytes((2,))
        for container, slot in sorted((source, destination)):
            delta += struct.pack('>HB', slot, container) + updated.get((container, slot), EMPTY).wire()
        self.items = updated
        return [(0x3e82, delta + b'\0'), self.reply(template=item.template)], True


class NativeLobby:
    def __init__(self, team_body, state_file=None):
        validate_team(team_body)
        self.template = bytes(team_body)
        self.state_file = Path(state_file) if state_file else None
        self.mode = 1  # original start handler only sends for 1 (quad) / 2 (duo)
        self.inventory = LobbyInventory()
        self.inventory_sent = False
        self.start_requested = False
        self.in_team = True
        if self.state_file and self.state_file.exists():
            self.load()

    def team_body(self):
        body = bytearray(self.template)
        struct.pack_into('>I', body, 12, self.mode)
        return bytes(body)

    def load(self):
        state = json.loads(self.state_file.read_text(encoding='utf8'))
        if not isinstance(state, dict) or set(state) != {'version', 'mode', 'items'} or state['version'] != 1:
            raise ValueError('Unknown native lobby profile; preserved without rewriting')
        if type(state['mode']) is not int or state['mode'] not in (1, 2):
            raise ValueError('Invalid saved lobby mode')
        if not isinstance(state['items'], list) or len(state['items']) > 128:
            raise ValueError('Invalid saved wardrobe size')
        items, uids, definitions = {}, set(), set()
        for row in state['items']:
            if not isinstance(row, list) or len(row) != 6 or any(type(n) is not int for n in row):
                raise ValueError('Invalid saved wardrobe item')
            container, slot, kind, template, uid, count = row
            item = Item(kind, template, uid, count)
            if (not self.inventory.fits((container, slot), item) or (container, slot) in items
                    or not 0 < uid < 2**64 or uid in uids
                    or template in definitions or kind != (20 if template in POSITIONS else 8)
                    or not 0 < count <= (1 if kind == 20 else 999)):
                raise ValueError('Invalid or duplicate saved wardrobe slot/item')
            items[container, slot] = item
            uids.add(uid)
            definitions.add(template)
        self.mode, self.inventory.items = state['mode'], items

    def save(self):
        if self.state_file is None:
            return
        state = dict(version=1, mode=self.mode, items=[
            [container, slot, item.kind, item.template, item.uid, item.count]
            for (container, slot), item in sorted(self.inventory.items.items())])
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(self.state_file.suffix + '.tmp')
        temporary.write_text(json.dumps(state, indent=2), encoding='utf8')
        temporary.replace(self.state_file)

    def handle(self, message, body):
        """Return None for unrelated game traffic, a list for consumed requests."""
        if message == 0x702f and len(body) == 1:
            replies = [(0x7030, self.team_body())]
            if not self.inventory_sent:
                replies.append((0x5fb, self.inventory.full_body()))
                self.inventory_sent = True
            self.in_team = True
            return replies
        if message in (0x701d, 0x702b) and len(body) == 4:
            mode = struct.unpack('>I', body)[0]
            if mode not in (1, 2):
                return [(0x702c, struct.pack('>II', 1, self.mode))]
            self.mode, self.in_team = mode, True
            self.save()
            return [(0x701e, self.team_body())] if message == 0x701d else [
                (0x702c, struct.pack('>II', 0, mode))]
        if message == 0x7021 and len(body) == 1:
            self.in_team = False
            return [(0x7022, bytes(8))]
        if message == 0x3e80:
            replies, changed = self.inventory.transfer(body)
            if replies:
                if changed:
                    self.save()
                return replies
        return None
