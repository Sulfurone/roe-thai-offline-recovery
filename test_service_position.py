import threading
import time
import unittest
from types import SimpleNamespace
from service_position import BufferedPositionFeed


class PositionBufferTests(unittest.TestCase):
    def test_slow_file_reader_does_not_block_take_or_replay_sequences(self):
        entered=threading.Event()
        release=threading.Event()
        delivered=threading.Event()
        def take():
            entered.set()
            if not release.wait(2):return None
            delivered.set()
            return (100,200,300)
        feed=BufferedPositionFeed(SimpleNamespace(take=take,sequence=5,pid=10,status=0))
        try:
            self.assertTrue(entered.wait(1))
            self.assertIsNone(feed.take())
            release.set()
            self.assertTrue(delivered.wait(1))
            limit=time.monotonic()+1
            while feed.latest is None and time.monotonic()<limit:time.sleep(.001)
            self.assertEqual(feed.take(),(100,200,300))
            self.assertEqual((feed.sequence,feed.pid),(5,10))
            self.assertIsNone(feed.take())
            row=feed.latest
            feed.latest=(time.monotonic()-2,row[1],6,*row[3:])
            self.assertIsNone(feed.take())
        finally:
            release.set()
            feed.close()
