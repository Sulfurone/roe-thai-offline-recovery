import mmap
import os
import struct
import sys
import time

MAGIC = b'\xd6\x02'
NAME_OFF = 148
NAME_LEN = 128
DATA_OFF = 276
NEEDLES = [b'CREATE_ACTOR', b'XY_ACTOR_FULL_GAME_DATA', b'LOGIN_WORLD_RSP',
           b'stRole_data', b'LOGIN_MSGID_CREATE_ACTOR']


def u32(buf, off):
    return struct.unpack_from('<I', buf, off)[0]


def parse(buf, p):
    if p + DATA_OFF > len(buf):
        return None
    if buf[p:p + 2] != MAGIC:
        return None
    n_build = struct.unpack_from('<h', buf, p + 2)[0]
    arch = u32(buf, p + 4)
    size = u32(buf, p + 8)
    if not (0 <= n_build < 64):
        return None
    if arch not in (32, 64):
        return None
    if not (DATA_OFF <= size <= 64 * 1024 * 1024):
        return None
    if p + size > len(buf):
        return None
    max_meta = u32(buf, p + 40)
    cur_meta = u32(buf, p + 44)
    if not (0 < cur_meta <= max_meta <= 1_000_000):
        return None
    raw_name = buf[p + NAME_OFF:p + NAME_OFF + NAME_LEN]
    name = raw_name.split(b'\0', 1)[0]
    if not name or len(name) > 100:
        return None
    if any(c < 0x20 or c > 0x7e for c in name):
        return None
    return {'offset': p, 'name': name.decode('ascii', 'replace'), 'size': size,
            'meta': cur_meta, 'arch': arch}


def scan_file(path, out):
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    if size < DATA_OFF:
        return
    try:
        with open(path, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as buf:
                found = []
                start = 0
                while True:
                    p = buf.find(MAGIC, start)
                    if p < 0:
                        break
                    info = parse(buf, p)
                    if info:
                        found.append(info)
                    start = p + 1
                for needle in NEEDLES:
                    if buf.find(needle) >= 0:
                        out.write(f'STRING {needle.decode()} in {path}\n')
                        out.flush()
                for info in found:
                    out.write(f'METALIB {info["name"]} off={info["offset"]} size={info["size"]} '
                              f'meta={info["meta"]} arch={info["arch"]} file={path}\n')
                    out.flush()
    except (OSError, ValueError):
        pass


def main():
    root = sys.argv[1]
    out_path = sys.argv[2]
    skip_over = 900 * 1024 * 1024
    t0 = time.time()
    with open(out_path, 'w', encoding='utf-8', errors='replace') as out:
        for dirpath, dirnames, filenames in os.walk(root):
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                try:
                    if os.path.getsize(p) > skip_over:
                        continue
                except OSError:
                    continue
                scan_file(p, out)
        out.write(f'done elapsed={time.time()-t0:.1f}s\n')
    print('done', time.time() - t0)


if __name__ == '__main__':
    main()
