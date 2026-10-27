"""Scan files for TSF4G TDR metalib headers and report their names.

Read-only. Layout source: recovery/private/tsf4g/tdr_metalib_kernel.h
(tagTDRMetaLib32, #pragma pack(4)). All interior pointers are offsets from
the `data` member at 276.
"""
import mmap
import os
import struct
import sys

MAGIC = b'\xd6\x02'
NAME_OFF = 148
NAME_LEN = 128
DATA_OFF = 276


def u32(buf, off):
    return struct.unpack_from('<I', buf, off)[0] if off + 4 <= len(buf) else None


def parse(buf, p):
    if p + DATA_OFF > len(buf):
        return None
    if buf[p:p + 2] != MAGIC:
        return None
    n_build = struct.unpack_from('<h', buf, p + 2)[0]
    arch = struct.unpack_from('<I', buf, p + 4)[0]
    size = struct.unpack_from('<I', buf, p + 8)[0]
    max_meta = u32(buf, p + 40)
    cur_meta = u32(buf, p + 44)
    version = u32(buf, p + 72)
    max_macro = u32(buf, p + 48)
    cur_macro = u32(buf, p + 52)
    free_str_size = u32(buf, p + 100)
    ptr_str = u32(buf, p + 104)
    if not (0 <= n_build < 64):
        return None
    if arch not in (32, 64):
        return None
    if not (DATA_OFF <= size <= 256 * 1024 * 1024):
        return None
    if p + size > len(buf):
        return None
    if not (0 < cur_meta <= max_meta <= 1_000_000):
        return None
    if version > 100 or cur_macro > max_macro or max_macro > 1_000_000:
        return None
    if not (0 < ptr_str <= size and ptr_str + free_str_size <= size):
        return None
    raw_name = buf[p + NAME_OFF:p + NAME_OFF + NAME_LEN]
    name = raw_name.split(b'\0', 1)[0]
    if not name or len(name) > 100:
        return None
    if any(c < 0x20 or c > 0x7e for c in name):
        return None
    return {
        'offset': p,
        'name': name.decode('ascii'),
        'size': size,
        'n_build': n_build,
        'arch': arch,
        'cur_meta': cur_meta,
        'max_meta': max_meta,
        'version': version,
        'ptr_str': ptr_str,
    }


def scan_bytes(buf, limit=None):
    out = []
    start = 0
    while True:
        p = buf.find(MAGIC, start)
        if p < 0:
            break
        info = parse(buf, p)
        if info:
            out.append(info)
            if limit and len(out) >= limit:
                break
            start = p + DATA_OFF
        else:
            start = p + 1
    return out


def scan_file(path, limit=None, marker=None):
    try:
        with open(path, 'rb') as fh:
            if os.fstat(fh.fileno()).st_size == 0:
                return []
            with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                found = scan_bytes(mm, limit)
                if marker:
                    for info in found:
                        span = mm[info['offset']:info['offset'] + info['size']]
                        info['has_marker'] = marker in span
                return found
    except (OSError, ValueError):
        return []


def main():
    roots = sys.argv[1:] or ['.']
    marker = None
    if roots and roots[0].startswith('--marker='):
        marker = roots.pop(0).split('=', 1)[1].encode()
    total = 0
    for root in roots:
        if os.path.isfile(root):
            files = [root]
        else:
            files = []
            for dirpath, _dirs, names in os.walk(root):
                for n in names:
                    files.append(os.path.join(dirpath, n))
        for path in files:
            for info in scan_file(path, marker=marker):
                total += 1
                flag = ''
                if 'has_marker' in info:
                    flag = ' MARKER' if info['has_marker'] else ''
                print(f"{path}\t{info['offset']:#x}\t{info['name']}\t"
                      f"size={info['size']}\tnbuild={info['n_build']}\t"
                      f"meta={info['cur_meta']}/{info['max_meta']}{flag}")
    print(f'# total {total}', file=sys.stderr)


if __name__ == '__main__':
    main()
