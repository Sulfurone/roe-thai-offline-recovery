"""Execute the Thai loader's two resource-wait branches in offline emulation.

Resource objects, allocation and downstream engine methods are synthetic. This
proves the two completion conditions, not real asset loading or visible pixels.
Requires the privately supplied original client image; writes no game files.
"""
import json
import struct

from native_codec_probe import NativeCodec, ROOT
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EIP, UC_X86_REG_ESP

c = NativeCodec()
c.uc.mem_map(0, 4096)  # Synthetic SEH head, never an OS callback.
actor, vtable, entry, resource, runtime, data, component = range(0x10900000, 0x10907000, 0x1000)
boundaries = []


def put(address, *values):
    c.uc.mem_write(address, struct.pack('<' + 'I' * len(values), *values))


def finish(value=0, cleanup=0):
    sp = c.uc.reg_read(UC_X86_REG_ESP)
    c.uc.reg_write(UC_X86_REG_EAX, value)
    c.uc.reg_write(UC_X86_REG_EIP, c.read32(sp))
    c.uc.reg_write(UC_X86_REG_ESP, sp + 4 + cleanup)


def hook(address, name, value=0, cleanup=0):
    def boundary(*_):
        boundaries.append(name)
        finish(value() if callable(value) else value, cleanup)
    c.uc.hook_add(UC_HOOK_CODE, boundary, begin=address, end=address)


stub = 0x10908000
c.external_hooks.update((stub, stub + 16))
c.uc.mem_write(stub, b'\xc3' * 32)
put(actor, vtable)
put(vtable + 0xbc, 0xcf1770)  # Original +34 bit20 getter: normal loading.
put(vtable + 0x268, stub)
put(vtable + 0x354, stub + 16)
hook(stub, 'component_lookup', cleanup=4)
hook(stub + 16, 'component_notification')
hook(0x65ae50, 'allocate', component)
hook(0xa2f210, 'component_construct', component, 4)
hook(0x95eba0, 'resource_component_link', cleanup=4)
hook(0x65b7c0, 'intern', lambda: c.uc.reg_read(UC_X86_REG_ECX), 4)
hook(0xd04100, 'post_component_init')
hook(0x401330, 'string_construct', lambda: c.uc.reg_read(UC_X86_REG_ECX), 4)
hook(0x673550, 'string_format')
put(actor + 0x500, resource)
put(actor + 0x50c, runtime)
checks = []
for name, callback, ready, expected in (
    ('actor_pending', 0xd07530, False, 0),
    ('actor_ready', 0xd07530, True, 1),
    ('runtime_pending', 0xd0b270, False, 0),
    ('runtime_ready_empty_set', 0xd0b270, True, 1),
):
    c.uc.mem_write(entry, bytes(16))
    c.uc.mem_write(resource + 0x21, bytes([ready]))
    put(runtime + 0x18, data if ready else 0)
    boundaries.clear()
    c.invoke(callback, 0, [actor, entry])
    done = c.uc.mem_read(entry + 4, 1)[0]
    if done != expected:
        raise ValueError((name, done, expected))
    if not ready and boundaries:
        raise ValueError(('Pending resources reached downstream methods', name, boundaries))
    checks.append(dict(case=name, completed=done, synthetic_boundaries=list(boundaries)))

report = dict(passed=True, checks=checks,
              limitation='Original completion branches with synthetic resources and downstream methods; no real loading or rendering')
path = ROOT / 'private/typed-gameplay/model-resource-waits-validation.json'
path.write_text(json.dumps(report, indent=2), encoding='utf8')
print(json.dumps(report))
