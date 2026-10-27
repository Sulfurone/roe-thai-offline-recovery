"""Read-only string extractor for local PE analysis (ASCII + UTF-16LE)."""
import re
import sys

PAT = re.compile(rb'[\x20-\x7e]{4,}')


def strings(data):
    out = []
    for m in PAT.finditer(data):
        out.append((m.start(), 'ascii', m.group().decode('ascii')))
    wide = re.compile(rb'(?:[\x20-\x7e]\x00){4,}')
    for m in wide.finditer(data):
        out.append((m.start(), 'utf16', m.group().decode('utf-16le')))
    out.sort()
    return out


def main():
    path, needle = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None
    data = open(path, 'rb').read()
    for offset, kind, text in strings(data):
        if needle is None or needle.lower() in text.lower():
            print(f'{offset:08x} {kind} {text}')


if __name__ == '__main__':
    main()
