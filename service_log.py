"""Write ordered diagnostics outside the gameplay thread."""
import json
import queue
import threading

TRANSPORT_EVENTS = {'received', 'application_message', 'sent', 'self_position_updated',
                    'actor_motion_ack_sent', 'bot_ai_response_sent'}

class ServiceLog:
    def __init__(self, path):
        self.path = path
        self.pending = queue.Queue(maxsize=8192)
        self.error = None
        self.thread = threading.Thread(target=self.write, name='service-log', daemon=True)
        self.thread.start()

    def emit(self, record):
        if self.error is not None:
            raise OSError('Diagnostic writer failed') from self.error
        try:
            self.pending.put_nowait(record)
        except queue.Full:
            raise OSError('Diagnostic writer queue is full')

    def write(self):
        try:
            with self.path.open('w', encoding='utf8') as output:
                while True:
                    record = self.pending.get()
                    if record is None:
                        return
                    encoded = json.dumps(record)
                    output.write(encoded + '\n')
                    if record['event'] not in TRANSPORT_EVENTS:
                        print(encoded, flush=True)
                    if self.pending.empty():
                        output.flush()
        except Exception as error:
            self.error = error

    def close(self):
        while self.thread.is_alive():
            try:
                self.pending.put(None, timeout=.1)
                break
            except queue.Full:
                continue
        self.thread.join()
        if self.error is not None:
            raise OSError('Diagnostic writer failed') from self.error
