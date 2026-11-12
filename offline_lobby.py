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
_catalog = json.loads(Path(__file__).with_name('lobby_clothes.json').read_text(encoding='utf8'))
POSITIONS = dict(_catalog['items'])
if (_catalog['version'] != 1 or len(POSITIONS) != 770
        or any(type(template) is not int or type(slot) is not int or slot not in (13, 14, 15, 16, 17, 18, 19, 22)
               for template, slot in POSITIONS.items())):
    raise ValueError('Unknown Thai wardrobe catalogue')
CRATES = frozenset((2010000, 2010001))


def lobby_item_wire(item):
    # OBJECT_INFO native +0x0E / wire +14 is the expiration timestamp,
    # not the item quantity. FE8200 treats zero as permanent. Quantity is
    # encoded by the item union and has already been written by Item.wire.
    return item.wire(expiration=0)


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
        self.unlock_all()

    def worn_clothes(self):
        return tuple((key, item) for key, item in sorted(self.items.items())
                     if key[0] == 1 and POSITIONS.get(item.template) == key[1])

    def unlock_all(self):
        owned = {item.template for item in self.items.values()}
        uid = max((item.uid for item in self.items.values()), default=0x1d00000000100000) + 1
        slot = 0
        for template in sorted(POSITIONS):
            if template in owned:
                continue
            while (2, slot) in self.items:
                slot += 1
            if slot >= 1024 or uid >= 2**64:
                raise ValueError('Local wardrobe capacity/UID limit exceeded')
            self.items[2, slot] = Item(20, template, uid, 1)
            uid += 1

    @staticmethod
    def fits(key, item):
        container, slot = key
        return (container == 1 and POSITIONS.get(item.template) == slot
                or container == 2 and 0 <= slot < 1024 and item.template in POSITIONS
                or container == 4 and 0 <= slot < 128 and item.template in CRATES)

    def full_body(self):
        rows = [(key, item) for key, item in sorted(self.items.items()) if key[1] < 256]
        if len(rows) > 397:
            raise ValueError('Original full inventory row limit exceeded')
        body = struct.pack('>I', len(rows))
        for (container, slot), item in rows:
            body += bytes((container, slot)) + lobby_item_wire(item)
        return body + bytes(9)  # owner flag 0: lobby, never the game bag

    def snapshot(self):
        # Full DTO has byte slots; delta DTO has ushort slots and 128 rows.
        # Never wrap a large slot or overrun the original per-packet bounds.
        replies = [(0x5fb, self.full_body())]
        rows = [(key, item) for key, item in sorted(self.items.items()) if key[1] >= 256]
        for start in range(0, len(rows), 128):
            chunk = rows[start:start + 128]
            body = bytes((len(chunk),))
            for (container, slot), item in chunk:
                body += struct.pack('>HB', slot, container) + lobby_item_wire(item)
            replies.append((0x3e82, body + b'\0'))
        return replies

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
            delta += struct.pack('>HB', slot, container) + lobby_item_wire(updated.get((container, slot), EMPTY))
        self.items = updated
        # F61C40 cannot remove an empty bag slot >=256. Rebuild its original
        # full cache followed by bounded deltas instead of leaving a ghost.
        if src_slot >= 256 or dst_slot >= 256:
            return self.snapshot() + [self.reply(template=item.template)], True
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
        self.member_count = struct.unpack_from('>I', team_body, 28)[0]
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
        if not isinstance(state['items'], list) or len(state['items']) > 1024:
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
        self.inventory.unlock_all()

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

    def request_start(self, message, body):
        if self.start_requested or message not in (0x6e29, 0x7037) or len(body) != 4:
            return None
        mode = struct.unpack('>I', body)[0]
        if message == 0x7037:
            # This lobby sometimes presents Ready instead of Matchmaking.
            # In a one-member offline room there is nobody else to wait for.
            if mode != 1 or not self.in_team or self.member_count != 1:
                return None
        elif mode not in (1, self.mode + 1):
            return None
        self.start_requested = True
        return mode

    def handle(self, message, body):
        """Return None for unrelated game traffic, a list for consumed requests."""
        if message == 0x702f and len(body) == 1:
            replies = [(0x7030, self.team_body())]
            if not self.inventory_sent:
                replies.extend(self.inventory.snapshot())
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


def world_with_wardrobe(body, clothes):
    """Project equipped wardrobe slots into the Thai single-actor world record."""
    # The 32838 fixture uses 24-byte empty equipment slots. The occupancy
    # byte is followed by three big-endian item fields only when nonzero.
    record_offset = 12
    first_wearable = record_offset + 1564
    if (len(body) != 2022 or body[:12] != struct.pack('>III', 0, 1, 1)
            or body[record_offset + 1] not in (0, 1)
            or any(body[first_wearable + (slot - 13) * 24] for slot in set(POSITIONS.values()))):
        raise ValueError('Wardrobe needs the Thai 32838 one-player world template with empty clothing slots')
    # Keep the complete actor UID. Its high bytes are also used by the lobby
    # to identify the local team leader and by gameplay to route player updates.
    result = bytearray(body)
    for (container, slot), item in reversed(clothes):
        if container != 1 or POSITIONS.get(item.template) != slot:
            raise ValueError('Invalid equipped wardrobe slot')
        offset = first_wearable + (slot - 13) * 24
        result[offset:offset + 1] = struct.pack('>BIII', 1, item.template, 1, 0)
    return bytes(result)
