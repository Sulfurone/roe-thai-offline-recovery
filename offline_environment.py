"""Thai environment clock initialization, separate from movement attributes."""
import struct
import time


def environment_clock(hour, timestamp=None):
    # Thai registry 0x4816 -> 0x1278B60 -> 0x12BAD70. The first
    # DWORD selects the initial clock slot; the second anchors server time.
    if type(hour) is not int or not 0 <= hour < 24:
        raise ValueError('Environment hour must be an integer from 0 to 23')
    timestamp = int(time.time()) if timestamp is None else timestamp
    if type(timestamp) is not int or not 0 <= timestamp <= 0xffffffff:
        raise ValueError('Environment timestamp must fit an unsigned DWORD')
    return 0x4816, struct.pack('>II', hour, timestamp)
