"""Keep menu command/status file I/O off the gameplay thread."""
import threading


class BufferedMailbox:
    def __init__(self, mailbox, hub):
        self.mailbox, self.hub = mailbox, hub
        self.latest = None
        self.error = None
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.run, name='menu-files', daemon=True)
        self.thread.start()

    def run(self):
        try:
            while True:
                self.mailbox.poll(self.hub)
                snapshot = self.latest
                if snapshot is not None:
                    self.mailbox.publish(snapshot)
                if self.stopped.wait(.05):
                    if self.latest is not None:
                        self.mailbox.publish(self.latest)
                    return
        except (OSError, ValueError) as error:
            self.error = error

    def poll(self, hub):
        if self.error is not None:
            raise OSError('Menu file worker failed') from self.error

    def publish(self, snapshot):
        self.latest = snapshot

    def close(self):
        self.stopped.set()
        self.thread.join()
