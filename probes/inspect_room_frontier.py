"""Inspect local packet captures and room strings; no live memory or UI access."""
from pathlib import Path
import argparse
import collections
import json
import struct

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('capture', type=Path)
a = p.parse_args()
image = (root / 'private/runtime-diag-1/thai-self-image.bin').read_bytes()[16:]
strings = {}
for address in (0x25a6d10, 0x25e3fe4, 0x25e3fd4, 0x261b818, 0x261b12c):
    strings[hex(address)] = image[address-0x400000:address-0x400000+256].split(b'\0',1)[0].decode('utf-8','replace')
data = a.capture.read_bytes()
offset = 0
counts = collections.Counter()
examples = {}
while offset + 26 <= len(data):
    length, message = struct.unpack_from('>IH', data, offset)
    if not 26 <= length <= 1048576:
        raise ValueError(f'Invalid frame length {length} at {offset}')
    if offset + length > len(data):
        break  # Concurrent capture may have an incomplete last frame.
    counts[hex(message)] += 1
    if message not in (0x3783, 0x1f6a):
        examples.setdefault(hex(message), data[offset+26:offset+length].hex())
    offset += length
print(json.dumps({'strings':strings, 'counts':dict(counts), 'example_bodies':examples,
                  'consumed':offset, 'bytes':len(data)}, indent=2))
