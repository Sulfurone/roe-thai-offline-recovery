"""Search candidate hash functions that map VFS names to SFC record keys."""
import hashlib
import json
import struct
import sys

ROOT = r'F:\roe'
SFC_PATHS = [
    ROOT + r'\32838\SFC\Script.sfc',
    ROOT + r'\32838\data_org_dyn.sfc',
    ROOT + r'\32838\data_dyn.sfc',
]
NAME_FILES = [
    ROOT + r'\recovery\references\data_bas_0-names.json',
    ROOT + r'\recovery\references\data_bas_2-names.json',
    ROOT + r'\recovery\references\data_bas_3-names.json',
    ROOT + r'\recovery\references\data_bas_4-names.json',
]


def record_keys(path):
    data = open(path, 'rb').read()
    pos = 8
    out = []
    while pos < len(data):
        key = data[pos:pos + 8]
        packed = struct.unpack_from('<I', data, pos + 8)[0]
        end = pos + 12 + packed
        out.append(key)
        pos = end + 4
    return out


def fnv1a(b):
    h = 0xcbf29ce484222325
    for c in b:
        h = ((h ^ c) * 0x100000001b3) & 0xffffffffffffffff
    return h


def crc64(b, poly):
    crc = 0
    for c in b:
        crc ^= c << 56
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xffffffffffffffff if crc & 0x8000000000000000 else (crc << 1) & 0xffffffffffffffff
    return crc


def xxh64(b, seed=0):
    P1 = 11400714785074694791; P2 = 14029467366897019727
    P3 = 1609587929392839161; P4 = 9650029242287828579; P5 = 2870177450012600261
    M = 0xffffffffffffffff

    def rotl(x, r):
        return ((x << r) | (x >> (64 - r))) & M

    def rnd(acc, inp):
        acc = (acc + inp * P2) & M
        return (rotl(acc, 31) * P1) & M

    n = len(b); i = 0
    if n >= 32:
        v1 = (seed + P1 + P2) & M; v2 = (seed + P2) & M; v3 = seed; v4 = (seed - P1) & M
        while i <= n - 32:
            v1 = rnd(v1, struct.unpack_from('<Q', b, i)[0]); v2 = rnd(v2, struct.unpack_from('<Q', b, i + 8)[0])
            v3 = rnd(v3, struct.unpack_from('<Q', b, i + 16)[0]); v4 = rnd(v4, struct.unpack_from('<Q', b, i + 24)[0])
            i += 32
        h = (rotl(v1, 1) + rotl(v2, 7) + rotl(v3, 12) + rotl(v4, 18)) & M
        for v in (v1, v2, v3, v4):
            h ^= rnd(0, v); h = (h * P1 + P4) & M
    else:
        h = (seed + P5) & M
    h = (h + n) & M
    while i <= n - 8:
        h ^= rnd(0, struct.unpack_from('<Q', b, i)[0]); h = (rotl(h, 27) * P1 + P4) & M; i += 8
    if i <= n - 4:
        h ^= (struct.unpack_from('<I', b, i)[0] * P1) & M; h = (rotl(h, 23) * P2 + P3) & M; i += 4
    while i < n:
        h ^= (b[i] * P5) & M; h = (rotl(h, 11) * P1) & M; i += 1
    h ^= h >> 33; h = (h * P2) & M; h ^= h >> 29; h = (h * P3) & M; h ^= h >> 32
    return h


def murmur64a(b, seed=0):
    m = 0xc6a4a7935bd1e995; r = 47; M = 0xffffffffffffffff
    h = (seed ^ (len(b) * m)) & M; i = 0
    while i + 8 <= len(b):
        k = struct.unpack_from('<Q', b, i)[0]; i += 8
        k = (k * m) & M; k ^= k >> r; k = (k * m) & M
        h ^= k; h = (h * m) & M
    rest = b[i:]
    for j, c in enumerate(rest):
        h ^= c << (8 * j)
    if rest:
        h = (h * m) & M
    h ^= h >> r; h = (h * m) & M; h ^= h >> r
    return h


FUNCS = {
    'fnv1a': fnv1a,
    'crc64ecma': lambda b: crc64(b, 0x42F0E1EBA9EA3693),
    'crc64iso': lambda b: crc64(b, 0xD800000000000000),
    'xxh64': xxh64,
    'murmur': murmur64a,
    'md5b': lambda b: int.from_bytes(hashlib.md5(b).digest()[:8], 'little'),
    'md5be': lambda b: int.from_bytes(hashlib.md5(b).digest()[:8], 'big'),
    'md5l': lambda b: int.from_bytes(hashlib.md5(b).digest()[-8:], 'little'),
    'sha1b': lambda b: int.from_bytes(hashlib.sha1(b).digest()[:8], 'little'),
    'sha256b': lambda b: int.from_bytes(hashlib.sha256(b).digest()[:8], 'little'),
    'sha1be': lambda b: int.from_bytes(hashlib.sha1(b).digest()[:8], 'big'),
}


def variants(s):
    bases = []
    p = s.lstrip('\\')
    bases.append(p)
    bases.append(p.replace('\\', '/'))
    if p.lower().startswith('data\\'):
        bases.append(p[5:])
        bases.append(p[5:].replace('\\', '/'))
    for base in list(bases):
        bases.append(base.lower())
        bases.append(base.upper())
    seen = set()
    for base in bases:
        for enc in (base.encode('ascii', 'ignore'),):
            if enc not in seen and enc:
                seen.add(enc)
                yield enc
        try:
            e = base.encode('gb18030')
            if e not in seen and e:
                seen.add(e)
                yield e
        except UnicodeEncodeError:
            pass


def main():
    keys = set()
    for p in SFC_PATHS:
        ks = record_keys(p)
        keys.update(ks)
        print(p, len(ks))
    print('total keys', len(keys))
    names = set()
    for p in NAME_FILES:
        names.update(x for x in json.load(open(p, encoding='utf-8')) if x)
    print('names', len(names))
    masked = {k[:7]: k for k in keys}
    found = 0
    for name in names:
        for v in variants(name):
            for fn, f in FUNCS.items():
                h = f(v)
                kb = h.to_bytes(8, 'little')
                if kb in keys:
                    print('FULL', fn, repr(name), repr(v), kb.hex())
                    found += 1
                elif kb[:7] in masked:
                    print('MASK', fn, repr(name), repr(v), masked[kb[:7]].hex())
                    found += 1
                if found >= 20:
                    return
    print('found', found)


if __name__ == '__main__':
    main()
