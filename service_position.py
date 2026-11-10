"""Poll the validated coordinate feed without blocking socket dispatch."""
import threading
import time


class BufferedPositionFeed:
    def __init__(self, feed):
        self.feed = feed
        self.latest = None
        self.sequence = 0
        self.pid = None
        self.status = None
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.poll, name='position-files', daemon=True)
        self.thread.start()

    def poll(self):
        while not self.stopped.is_set():
            started = time.monotonic()
            position = self.feed.take()
            if position is not None and time.monotonic() - started <= 1:
                self.latest = (started, position, self.feed.sequence,
                               self.feed.pid, self.feed.status)
            self.stopped.wait(.05)

    def take(self):
        sample = self.latest
        if sample is None or time.monotonic() - sample[0] > 1 or sample[2] <= self.sequence:
            return None
        _, position, self.sequence, self.pid, self.status = sample
        return position

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=.5)
