"""Bounded reversible-object state for this local Thai scene prototype.

Thai 6F55 uses DWORD state/count, unlike the 2022 reference. Its callback
requires a nonempty part-state vector before applying reversible state.
One zero/default part value is a live-test candidate. Destruction,
catalogue authority, persistence and full scene collision are not restored.
"""
import struct


class DoorState:
    def __init__(self):
        self.states = {}

    def handle(self, body):
        if len(body) != 8:
            return []
        entity, state = struct.unpack('>II', body)
        if not 0 < entity < 2**24 or state not in (0, 1, 2):
            return []
        if entity not in self.states and len(self.states) >= 4096:
            return []
        self.states[entity] = state
        # entity, reversible state, part-state count, candidate part state,
        # optional destruction-union tag. Original E14140 -> 1288110.
        return [(0x6f55, struct.pack('>5I', entity, state, 1, 0, 0))]
