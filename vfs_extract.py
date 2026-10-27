"""Read-only VFS v2 extraction for the verified early Thai client.

Format reference: Luigi Auriemma / Ekey, dzs_qq.bms 0.3.3, preserved in
references/dzs_qq.bms. Only bounded, size-verified zlib/raw entries are supported.
Encrypted content or unknown chunk encodings are rejected rather than guessed.
"""
import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import struct
import zlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

KEY = b'(VFS_DEFAULT_AES_KEY)'.ljust(32, b'\0')


def decrypt_table(data):
    boundary = len(data) // 16 * 16
    context = Cipher(algorithms.AES(KEY), modes.ECB()).decryptor()
    return context.update(data[:boundary]) + context.finalize() + data[boundary:]


class Archive:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        data = self.data
        if data[:8] != b'vfs \x02\0\0\0':
            raise ValueError('Unsupported VFS header')
        info = struct.unpack_from('<Q', data, 32)[0]
        info_size = struct.unpack_from('<I', data, 40)[0]
        names = struct.unpack_from('<Q', data, 44)[0]
        names_size = struct.unpack_from('<I', data, 52)[0]
        encrypted = data[56]
        if names + names_size > len(data) or int.from_bytes(data[names:names+2], 'little') >= 256:
            shift = len(data) - names_size - names
            info += shift
            names += shift
        if not 0 <= info <= info + info_size <= names <= names + names_size <= len(data):
            raise ValueError('VFS tables extend beyond the archive')
        self.names = []
        pos = names
        while pos < names + names_size:
            size = struct.unpack_from('<H', data, pos)[0]
            pos += 2
            if not size or pos + size > names + names_size:
                raise ValueError('Invalid VFS name length')
            raw = data[pos:pos+size]
            pos += size
            raw = raw if raw == b'\\' else decrypt_table(raw)
            # A few sound filenames contain bytes outside valid GB18030. Keep
            # their index entry but never silently use a replacement file path.
            try:
                name = raw.split(b'\0')[0].decode('gb18030')
            except UnicodeDecodeError:
                name = None
            self.names.append(name)
        self.entries = []
        pos = info
        while pos < info + info_size:
            packed, checksum = struct.unpack_from('<HI', data, pos)
            pos += 6
            if packed < 28 or pos + packed > info + info_size:
                raise ValueError('Invalid VFS index entry length')
            raw = data[pos:pos+packed]
            pos += packed
            raw = decrypt_table(raw) if encrypted else raw
            index, size, compressed, align, offset, flags = struct.unpack_from('<IIIIQI', raw)
            if index >= len(self.names):
                raise ValueError('VFS name index is out of bounds')
            self.entries.append(dict(name=self.names[index], index=index, size=size,
                                     compressed=compressed, alignment=align,
                                     offset=offset, flags=flags, table_checksum=checksum))

    def extract(self, entry):
        offset, size, compressed = entry['offset'], entry['size'], entry['compressed']
        if not offset:
            raise ValueError('Directory or missing entry')
        if size > 128 * 1024 * 1024:
            raise ValueError('Entry exceeds extraction limit')
        if self.data[offset:offset+4] != b'data':
            raise ValueError('Missing VFS data marker')
        start = offset + 16
        if not entry['flags'] & 1 and size == compressed:
            result = self.data[start:start+size]
        else:
            payload = self.data[start:start+compressed]
            if not payload.startswith(b'\x78'):
                raise ValueError('Unsupported encrypted or chunked VFS entry')
            decoder = zlib.decompressobj()
            result = decoder.decompress(payload, size + 1)
            if not decoder.eof:
                raise ValueError('Truncated VFS zlib stream')
        if len(result) != size:
            raise ValueError('VFS decoded size mismatch')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--pattern', help='Only extract names matching this regex')
    args = parser.parse_args()
    source, output = args.archive.resolve(), args.output.resolve()
    if source.is_relative_to(output):
        raise ValueError('Output must be separate from the source archive')
    archive = Archive(source)
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for entry in archive.entries:
        result = dict(entry)
        if entry['offset'] and entry['name'] and args.pattern and re.search(args.pattern, entry['name'], re.I):
            path = PureWindowsPath(entry['name'].lstrip('\\'))
            if path.drive or '..' in path.parts or any(':' in part for part in path.parts):
                raise ValueError('Unsafe VFS path')
            try:
                decoded = archive.extract(entry)
                destination = output.joinpath(*path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(decoded)
                result['sha256'] = hashlib.sha256(decoded).hexdigest()
                result['extracted'] = True
            except (ValueError, zlib.error) as error:
                result['error'] = str(error)
        manifest.append(result)
    (output / 'vfs-manifest.json').write_text(json.dumps({
        'source': str(source), 'entries': manifest,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'indexed': len(manifest), 'extracted': sum(x.get('extracted', False) for x in manifest),
                      'rejected': sum('error' in x for x in manifest)}))


if __name__ == '__main__':
    main()
