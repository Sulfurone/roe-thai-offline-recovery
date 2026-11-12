"""Wall-clock cadence for optional work between ordered client packets.

Input messages are never skipped or reordered. Missed background intervals
are coalesced into one current update, rather than replayed as a backlog.
"""
import time


class ServiceCadence:
    INTERVALS = dict(position=.05, control=.1, population=.2, world_send=.04, ai=.05, combat=.05,
                     zones=.1, capture_flush=1., statistics=5.)

    def __init__(self):
        self.next = {name: 0. for name in self.INTERVALS}
        self.background_wait_until = None

    def background_ready(self, input_ready, now):
        """Give waiting client packets one interval before optional work."""
        if not input_ready:
            self.background_wait_until = None
            return True
        if self.background_wait_until is None:
            self.background_wait_until = now + self.INTERVALS['world_send']
            return False
        if now < self.background_wait_until:
            return False
        self.background_wait_until = now + self.INTERVALS['world_send']
        return True

    def due(self, name, now=None):
        interval = self.INTERVALS[name]
        now = time.monotonic() if now is None else now
        if now < self.next[name]:
            return False
        self.next[name] = now + interval
        return True
