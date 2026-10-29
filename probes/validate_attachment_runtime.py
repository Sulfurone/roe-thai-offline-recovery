"""Run Thai part class selection, native constructors, binding and ADS switching.

Uses the owner's private image and numeric ItemTable fields. Engine allocation,
class-registry lookup, inventory/hash storage and model visibility endpoints
are bounded emulator dependencies. Part constructors, RTTI, inventory reader,
slot removal and telescope mode switching execute original instructions.
No live process or renderer is used, and no original assets are exported.
"""
import json
import struct
import sys
from collections import deque

from native_codec_probe import NativeCodec, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX,
                              UC_X86_REG_ESP, UC_X86_REG_EIP)

sys.path.insert(0, str(ROOT))
from offline_inventory import Item, OfflineInventory
from test_equipment_actions import part_request


class Runtime:
    def __init__(self):
        self.c = NativeCodec()
        self.c.uc.mem_map(0, 4096)  # Emulator SEH head; no OS execution.
        self.heap = 0x10b00000
        self.inv, self.actor, self.gun, self.cell, self.manager, self.buckets = range(
            0x10900000, 0x10906000, 0x1000)
        self.rows = {}
        defaults = json.loads((ROOT / 'private/gameplay-catalog/original-item-defaults.json').read_text(encoding='utf8'))
        for table in defaults['tables']:
            for row in table['rows']:
                if row['dwStringID'] in (40305, 40303, 40201, 40403, 40351):
                    address = self.alloc(0x2d0)
                    self.put(address + 8, row['mCategory'], row['mSubCategory'])
                    self.rows[row['dwStringID']] = address
        self.selected_class = None
        self.factories, self.visibility, self.bag_updates = [], [], []
        self.trace = deque(maxlen=32)
        self.c.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: self.trace.append(hex(a)))
        self.hook(0x65ae50, lambda: self.done(self.alloc(self.args(2)[0])))
        self.hook(0x65ae90, lambda: self.done())
        # The object base is outside the tested part initialization; all item
        # fields and Accessory/Telescope constructors themselves remain native.
        self.hook(0x66e890, lambda: self.done(self.this()))
        self.hook(0x7adc10, lambda: self.done(self.rows.get(self.args(1)[0], 0), 4))
        self.hook(0x7ae3b0, self.copy_item_row)
        self.hook(0x65b7c0, self.string)
        self.hook(0x65e150, lambda: self.done(0x10907000, 8))
        self.hook(0x6825f0, self.construct)
        self.hook(0x793e90, lambda: self.done(self.cell, 4))
        self.hook(0x1130200, lambda: self.done(self.actor))
        self.hook(0x11302f0, lambda: self.done(self.inv))
        self.hook(0x1130310, lambda: self.done(0))
        self.hook(0x1130630, lambda: self.done(0))
        self.hook(0xf61c40, self.bag_update)
        self.hook(0x401330, self.empty_ui_string)
        self.hook(0x409190, self.copy_ui_string)
        self.hook(0xf635f0, lambda: self.done())
        self.hook(0xe7ddd0, lambda: self.done(0, 8))
        self.hook(0x12fabd0, lambda: self.done())
        self.c.uc.mem_write(0x2952df6, b'\0')  # Non-Lua UI notification endpoint.
        self.hook(0x13914c0, self.insert_map)
        self.hook(0xb34970, lambda: self.done(0x10908000))
        self.put(0x10908000, 0x10909000)
        self.put(0x10909000 + 0x6c, 0xbae420)
        self.hook(0xbae420, lambda: self.done(0, 4))
        self.hook(0xbae410, self.model_flag)
        # This bounded native config fixture matches the own client's observed
        # M4A1 default scope 40351. It is not a full weapon-table reconstruction.
        self.config_table, config, defaults = self.alloc(0x80), self.alloc(0x450), self.alloc(28)
        self.put(self.config_table + 0x40, config, config + 0x450)
        self.put(config, 10201)
        self.put(config + 0x404, defaults, defaults + 28, defaults + 28)
        self.put(defaults, 0xffffffff, 0xffffffff, 40351,
                 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff)
        self.hook(0x108ccf0, lambda: self.done(self.config_table))
        float_init = self.c.read32(0x281d4c4)
        if not self.c.base <= float_init < self.c.base + self.c.size:
            self.c.external_hooks.add(float_init)
            if not 0x10000000 <= float_init < 0x11000000:
                try:
                    self.c.uc.mem_map(float_init & ~4095, 4096)
                except Exception:
                    pass
        self.hook(float_init, lambda: self.done(0, 4))
        self.put(0x2eedb58, self.manager)
        self.put(self.manager + 0xe4, 0x10906000)
        self.put(0x281d4bc, self.buckets)
        self.put(self.cell, self.gun)
        self.put(self.inv + 0xc, self.actor)
        self.put(self.actor + 0x2f8, 1)
        self.put(self.gun, 0x25a1a48)
        self.put(self.gun + 0x18, 0x100101, 0)
        self.put(self.gun + 0x20, 10201)
        self.slots = self.alloc(28)
        self.put(self.gun + 0x6b4, self.slots, self.slots + 28, self.slots + 28)

    def put(self, address, *values):
        self.c.uc.mem_write(address, struct.pack('<' + 'I' * len(values), *values))

    def alloc(self, size):
        if not 0 < size <= 65536 or self.heap + size >= 0x10f00000:
            raise ValueError('Emulator allocation bound exceeded')
        result = self.heap
        self.heap += (size + 15) & ~15
        self.c.uc.mem_write(result, bytes(size))
        return result

    def this(self):
        return self.c.uc.reg_read(UC_X86_REG_ECX)

    def args(self, n):
        return struct.unpack('<' + 'I' * n, self.c.uc.mem_read(
            self.c.uc.reg_read(UC_X86_REG_ESP) + 4, n * 4))

    def done(self, value=0, cleanup=0):
        sp = self.c.uc.reg_read(UC_X86_REG_ESP)
        self.c.uc.reg_write(UC_X86_REG_EAX, value)
        self.c.uc.reg_write(UC_X86_REG_EIP, self.c.read32(sp))
        self.c.uc.reg_write(UC_X86_REG_ESP, sp + 4 + cleanup)

    def hook(self, address, fn):
        self.c.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: fn(), begin=address, end=address)

    def copy_item_row(self):
        self.c.uc.mem_write(self.this(), bytes(self.c.uc.mem_read(self.args(1)[0], 0x2d0)))
        self.done(self.this(), 4)

    def string(self):
        pointer = self.args(1)[0]
        if pointer:
            name = bytes(self.c.uc.mem_read(pointer, 64)).split(b'\0', 1)[0]
            if name in (b'QSAccessory', b'QSTelescope'):
                self.selected_class = name.decode('ascii')
        self.put(self.this(), pointer or 0)
        self.done(self.this(), 4)

    def construct(self):
        constructors = {'QSAccessory': 0x10629c0, 'QSTelescope': 0x1062a60}
        if self.selected_class not in constructors:
            raise ValueError('Unexpected original factory class selection')
        self.factories.append(self.selected_class)
        # Continue into the original constructor with its existing return
        # address; do not recursively enter Unicorn from a code callback.
        self.c.uc.reg_write(UC_X86_REG_EIP, constructors[self.selected_class])

    def insert_map(self):
        output, record, flag = self.args(3)
        start = self.c.read32(self.this() + 4)
        node = self.alloc(16)
        self.put(node, self.c.read32(record), self.c.read32(record + 4), self.c.read32(start))
        self.put(start, node)
        self.put(output, node, start)
        self.done(output, 12)

    def model_flag(self):
        flag, secondary = self.args(2)
        self.visibility.append((self.this(), flag, secondary))
        self.done(0, 8)

    def empty_ui_string(self):
        self.put(self.this(), 0, 0, 0)
        self.done(self.this(), 4)

    def copy_ui_string(self):
        self.c.uc.mem_write(self.this(), bytes(self.c.uc.mem_read(self.args(1)[0], 12)))
        self.done(self.this(), 4)

    def bag_update(self):
        slot, dto = self.args(2)
        template = self.c.read32(dto + 2)
        self.bag_updates.append(dict(slot=slot, template=template))
        self.done(0, 8)

    def consume(self, packet):
        decoded = self.c.decode_server(*packet)
        if decoded['code'] or decoded['consumed'] != decoded['bytes']:
            raise ValueError('Original inventory decoder rejected response')
        # Execute the real delta callback, its row-context normalization and
        # F636C0/F62E80 routing into F61EC0. Bag storage and UI endpoints are
        # isolated; do not assume that a manually selected gun row is enough.
        self.c.invoke(0x128c9c0, 0, [self.c.ROOT_OBJECT + 6])


def main():
    r = Runtime()
    inventory = OfflineInventory()
    gun = inventory.items[1, 1]
    inventory.weapon_magazines[gun.uid] = 19
    checks = []
    for template in (40305, 40303, 40201, 40403):
        # Actual original class factory, constructors and hierarchy comparison.
        r.factories.clear()
        address = r.c.invoke(0xfe8740, 0, [template, 1])
        expected = 'QSTelescope' if template in (40305, 40303) else 'QSAccessory'
        expected_vtable = 0x25cebc8 if expected == 'QSTelescope' else 0x25ceb10
        if (r.factories != [expected] or r.c.read32(address) != expected_vtable
                or r.c.read32(address + 0x20) != template):
            raise ValueError('Native part class differs from factory selection')
        kind = r.c.invoke(0x1062730, address, [])
        actual_kind = r.c.invoke(r.c.read32(expected_vtable + 4), address, [])
        if not r.c.invoke(0x67b4c0, actual_kind, [kind]) & 255:
            raise ValueError('Original hierarchy rejected native part as Accessory')
        checks.append(dict(template=template, native_class=expected))

    # Replay real server mutations through the original F61EC0, without RTTI,
    # part-factory, slot-getter, attach or detach stubs.
    r.c.invoke(0x111abd0, r.gun, [2])
    initial = r.c.read32(r.slots + 8)
    if not initial or r.c.read32(initial + 0x20) != 40351:
        raise ValueError('Native configured default scope was not installed')
    sequence = []
    for template in (40305, 40303):
        inventory.items[2, 1] = Item(4, template, inventory.next_uid, 1)
        inventory.next_uid += 1
        replies = inventory.handle(part_request(0, 2, 1, gun.uid, 3, 2))
        if [mid for mid, _ in replies] != [0x3e82, 0x3e81]:
            raise ValueError('Service rejected scope install/replace')
        r.consume(replies[0])
        scope = r.c.read32(r.slots + 8)
        if (not scope or r.c.read32(scope) != 0x25cebc8
                or r.c.read32(scope + 0x20) != template or r.c.read32(r.gun + 0x60) != 19):
            raise ValueError('Original consumer did not bind selected telescope')
        for mode in (0, 1, 0):
            r.c.invoke(0x1119b50, r.gun, [mode])
            if bytes(r.c.uc.mem_read(scope + 0x5c, 1))[0] != mode:
                raise ValueError('Original telescope ADS setter did not accept mode')
        # Supply two inert model proxies, record the original mode-switch
        # boundary calls and execute its original selected-model getter.
        model_vtable, normal, zoom = r.alloc(0x100), r.alloc(0x100), r.alloc(0x100)
        r.put(model_vtable + 0xac, 0xbae410)
        r.put(normal, model_vtable); r.put(zoom, model_vtable)
        r.put(scope + 0x48, normal); r.put(scope + 0x58, zoom)
        for mode in (0, 1, 0):
            r.visibility.clear()
            r.c.invoke(0x1119b50, r.gun, [mode])
            selected = r.c.invoke(0x1062850, scope, [])
            if (selected != (zoom if mode else normal) or
                    r.visibility != [(zoom, mode, 0), (normal, 1-mode, 0)]):
                raise ValueError('Native ADS model-selection boundary differs')
        # The next real detach runs with the isolated owner/model absence.
        r.put(scope + 0x48, 0); r.put(scope + 0x58, 0)
        sequence.append(dict(scope=template, loaded=19, native_ads_modes=[0, 1, 0],
                             complementary_model_boundary_calls=True))
    replies = inventory.handle(part_request(gun.uid, 3, 2, 0, 2, 2))
    r.consume(replies[0])
    restored = r.c.read32(r.slots + 8)
    if (not restored or r.c.read32(restored + 0x20) != 40351
            or inventory.items[2, 2].template != 40303
            or r.c.invoke(0x1119180, r.gun, [2, 1]) != 0):
        raise ValueError('Detach did not restore/filter the configured default scope')
    # Negative control: a generic accessory cannot masquerade as a telescope
    # merely because it is placed in the scope slot of this synthetic gun.
    generic = r.c.invoke(0xfe8740, 0, [40201, 1])
    r.put(r.slots + 8, generic)
    r.visibility.clear()
    r.c.invoke(0x1119b50, r.gun, [1])
    if r.visibility:
        raise ValueError('Native telescope RTTI accepted generic accessory')
    if r.bag_updates != [dict(slot=1, template=0), dict(slot=1, template=40305), dict(slot=2, template=40303)]:
        raise ValueError('Original delta callback did not route all changed bag rows')
    report = dict(passed=True, factory_checks=checks, native_bind_sequence=sequence,
                  detached=True, configured_default_restored=40351,
                  original_delta_callback=True, bag_boundary_updates=r.bag_updates,
                  generic_accessory_ads_rejected=True,
                  limitation='Native delta callback/context/weapon routing/class selection/constructors/RTTI/slot binding/default fallback/ADS getter and complementary model boundary calls; synthetic registry, allocation, table and bag storage/UI, seeded M4A1 default config and inert model proxies, absent owner. No renderer or model-loading proof. Default fixture matches the independently observed own-client default.')
    path = ROOT / 'private/typed-gameplay/attachment-runtime-validation.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
