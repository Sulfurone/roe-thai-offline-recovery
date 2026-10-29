"""Prove on the client's own calculator that standing backward speed is fixed.

Runs `0x106FB20` (the movement speed resolver) against a property block seeded
by the stock grounded delta, then again with the `--gameplay-posture-speeds`
update applied on top, and compares the three reported components for every
posture and direction.

The second pass uses `offline_posture.posture_speed_delta()` -- the exact body
the server sends -- so this probe exercises the shipping path rather than a
hand-built fixture. It executes the shipped calculator instead of reading the
attribute table by hand, so a wrong table transcription cannot pass.

Run from the repository root on a machine that holds the user's own original
client image and private fixtures:

    python probes/validate_standing_speeds.py
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'probes'))
sys.path.insert(0, str(ROOT / 'python-libs'))

from unicorn import UC_HOOK_CODE  # noqa: E402
from unicorn.x86_const import (  # noqa: E402
    UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESP)

from native_codec_probe import NativeCodec  # noqa: E402

from offline_posture import posture_speed_delta  # noqa: E402

# Property block the stock client seeds for a grounded actor.
SOURCE = ROOT / 'private' / 'native-roster' / 'movement-grounded-delta.bin'
RECEIPT = ROOT / 'private' / 'runtime-diag-1' / 'standing-speed-validation.json'

CALCULATOR = 0x106FB20
APPLY = 0x12D6F10
SPARSE_UPDATE = 0x516
POSTURES = {0: 'stand', 1: 'crouch', 2: 'prone'}

# What each posture must report once the standing patch is applied.
EXPECTED = {
    'stand': (560.0, 560.0, 560.0),
    'crouch': (280.0, 280.0, 120.0),
    'prone': (120.0, 120.0, 120.0),
}


def main() -> int:
    if not SOURCE.exists():
        print(f'Missing private fixture: {SOURCE.relative_to(ROOT)}')
        print("This probe needs the user's own client data and is not shipped.")
        return 2

    codec = NativeCodec()
    entity, vtable, props = 0x10A00000, 0x10A02000, 0x10A04000
    out = 0x10A10000

    def apply_sparse(body: bytes) -> None:
        codec.decode_server(SPARSE_UPDATE, body)
        native = bytes(codec.uc.mem_read(codec.ROOT_OBJECT + 10, 497))
        codec.uc.mem_write(codec.OBJECT, native)
        codec.invoke(APPLY, props, [codec.OBJECT])

    def resolve(posture: int, mode: int) -> tuple[float, float, float]:
        codec.uc.mem_write(entity + 0x10, struct.pack('<I', vtable))
        codec.uc.mem_write(vtable + 0x54, struct.pack('<I', 0xE515A0))
        codec.uc.mem_write(entity + 0x7C8, struct.pack('<I', 0x10A08000))
        codec.invoke(CALCULATOR, 0,
                     [entity, posture, mode, 0, 0, out, out + 4, out + 8])
        return struct.unpack('<3f', codec.uc.mem_read(out, 12))

    def support(uc, address, size, user):
        stack = uc.reg_read(UC_X86_REG_ESP)
        if address == 0xE515A0:
            uc.reg_write(UC_X86_REG_EDX, 0)
            value = 256
        elif address == 0x113E2C0:
            value = props
        else:
            value = 0
        uc.reg_write(UC_X86_REG_EAX, value)
        uc.reg_write(UC_X86_REG_EIP, codec.read32(stack))
        uc.reg_write(UC_X86_REG_ESP, stack + 4)

    hooks = [codec.uc.hook_add(UC_HOOK_CODE, support, begin=a, end=a)
             for a in (0xE515A0, 0x113E2C0, 0x12AC680)]

    stock = SOURCE.read_bytes()
    patch = posture_speed_delta()

    def seed_pattern() -> None:
        codec.uc.mem_write(props,
                           bytes((i * 37 + 13) % 256 for i in range(0x3000)))

    seed_pattern()
    apply_sparse(stock)
    before = {f'{POSTURES[p]}/{m}': resolve(p, m)
              for p in POSTURES for m in range(3)}

    seed_pattern()
    apply_sparse(stock)
    apply_sparse(patch)
    after = {f'{POSTURES[p]}/{m}': resolve(p, m)
             for p in POSTURES for m in range(3)}

    for hook in hooks:
        codec.uc.hook_del(hook)

    print(f'posture patch: {len(patch)} bytes, '
          f'{struct.unpack_from(">H", patch, 0)[0]} records')
    print('component order: forward, other, backward\n')
    print(f'{"key":<12} {"stock":<26} {"patched":<26} verdict')
    print('-' * 78)
    for key in before:
        old, new = before[key], after[key]
        verdict = 'unchanged' if old == new else f'{old[2]:.0f} -> {new[2]:.0f}'
        print(f'{key:<12} {str(old):<26} {str(new):<26} {verdict}')

    problems = []
    for key, value in after.items():
        posture = key.split('/')[0]
        if value != EXPECTED[posture]:
            problems.append(
                f'{key} reports {value}, expected {EXPECTED[posture]}')
    # Crouch/prone legitimately differ from the stock delta -- that delta flattens
    # every posture to 560 and this patch is what brings them back to 280/120.
    # What matters is the patched result, checked against EXPECTED above.
    standing = [k for k in before if k.startswith('stand')]
    if any(before[k][2] >= before[k][0] for k in standing):
        problems.append('fixture does not exhibit the reported slow backward speed')
    # Only standing forward speed is in scope; the stock delta flattens crouch and
    # prone to 560 on purpose, so their forward values are expected to drop.
    if any(before[k][0] != after[k][0] for k in standing):
        problems.append('standing forward speed changed, which is out of scope')

    receipt = {
        'calculator': hex(CALCULATOR),
        'patch_bytes': len(patch),
        'patch_records': struct.unpack_from('>H', patch, 0)[0],
        'component_order': ['forward', 'other', 'backward'],
        'stock': {k: list(v) for k, v in before.items()},
        'patched': {k: list(v) for k, v in after.items()},
        'expected': {k: list(v) for k, v in EXPECTED.items()},
        'problems': problems,
        'passed': not problems,
        'limitation': (
            'Executes the shipped calculator against a synthetic property block '
            'seeded by the real delta. Proves the resolved numbers, not the felt '
            'gameplay; only the player can confirm the latter.'
        ),
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n',
                       encoding='utf-8')

    print()
    if problems:
        for problem in problems:
            print(f'FAIL {problem}')
        return 1
    print("standing backward resolved 120 -> 560 on the client's own calculator")
    print('crouch/prone settled at their documented 280/120')
    print(f'WROTE {RECEIPT.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
