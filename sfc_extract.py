"""Read-only extractor for this client's SFC v2 archives (no extra packages)."""
from pathlib import Path
import argparse
import hashlib
import json
import struct


def lz4_block(data, expected):
    out = bytearray()
    pos = 0

    def length(initial):
        nonlocal pos
        value = initial
        if initial == 15:
            while True:
                if pos >= len(data):
                    raise ValueError("Truncated LZ4 length")
                extra = data[pos]
                pos += 1
                value += extra
                if extra != 255:
                    break
        return value

    while pos < len(data):
        token = data[pos]
        pos += 1
        count = length(token >> 4)
        if pos + count > len(data) or len(out) + count > expected:
            raise ValueError("Invalid LZ4 literals")
        out.extend(data[pos:pos + count])
        pos += count
        if pos == len(data):
            break
        if pos + 2 > len(data):
            raise ValueError("Truncated LZ4 offset")
        distance = int.from_bytes(data[pos:pos + 2], "little")
        pos += 2
        count = length(token & 15) + 4
        if not distance or distance > len(out) or len(out) + count > expected:
            raise ValueError("Invalid LZ4 match")
        # LZ4 permits matches overlapping their destination.
        pattern = bytes(out[-distance:])
        repeats, remainder = divmod(count, distance)
        out.extend(pattern * repeats + pattern[:remainder])
    if len(out) != expected:
        raise ValueError(f"Decoded length {len(out)} differs from {expected}")
    return bytes(out)


def records(data):
    if data[:8] != b"SFC\x1a\x02\0\0\0":
        raise ValueError("Unsupported SFC header")
    pos = 8
    while pos < len(data):
        if pos + 16 > len(data):
            raise ValueError(f"Truncated record at {pos:#x}")
        key = data[pos:pos + 8].hex()
        packed = struct.unpack_from("<I", data, pos + 8)[0]
        end = pos + 12 + packed
        if end + 4 > len(data):
            raise ValueError(f"Record extends past archive at {pos:#x}")
        raw = struct.unpack_from("<I", data, end)[0]
        if raw > 256 * 1024 * 1024:
            raise ValueError("Record exceeds extraction limit")
        decoded = b"" if packed == raw == 0 else lz4_block(data[pos + 12:end], raw)
        yield {"key": key, "offset": pos, "packed": packed, "size": raw}, decoded
        pos = end + 4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = args.archive.resolve()
    output = args.output.resolve()
    if output == source or source.is_relative_to(output):
        raise ValueError("Output must be separate from the source archive")
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for info, decoded in records(source.read_bytes()):
        info["sha256"] = hashlib.sha256(decoded).hexdigest()
        # Keep repeated keys in the manifest; the final occurrence is active.
        (output / (info["key"] + ".bin")).write_bytes(decoded)
        manifest.append(info)
    (output / "manifest.json").write_text(json.dumps({
        "source": str(source), "records": manifest,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }, indent=2), encoding="utf-8")
    print(f"Validated and extracted {len(manifest)} records from {source.name}")


if __name__ == "__main__":
    main()
