"""Wall-clock cadence for optional work between ordered client packets.

Input messages are never skipped or reordered. Missed background intervals
are coalesced into one current update, rather than replayed as a backlog.
"""
import time


class ServiceCadence:
    INTERVALS = dict(position=.05, control=.1, population=.2, ai=.05,
                     zones=.1, capture_flush=1., statistics=5.)

    def __init__(self):
        self.next = {name: 0. for name in self.INTERVALS}

    def due(self, name, now=None):
        interval = self.INTERVALS[name]
        now = time.monotonic() if now is None else now
        if now < self.next[name]:
            return False
        self.next[name] = now + interval
        return True
