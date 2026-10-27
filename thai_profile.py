"""Persist character submissions captured from Thai build 0.2.15.5 only.

The request and its name field are verified from a native client submission.
This is not yet a complete server-side character database or roster serializer.
"""
import base64
import datetime
import hashlib
import json
from pathlib import Path
import struct

CLIENT_SHA256 = 'ff980bec18fe325d2cfb0b624f0a3b3c9911ccbb4cdbc16c5d40b3a47852619a'


def parse_create_request(packet):
    if len(packet) < 34 or int.from_bytes(packet[:4], 'big') != len(packet):
        raise ValueError('Invalid Thai application packet length')
    if packet[4:6] != b'\x02\xf9' or packet[22:26] != b'\0\0\x02\xf9':
        raise ValueError('Not a Thai character creation request')
    body = packet[26:]
    prefix, name_length = struct.unpack_from('>II', body)
    if not 2 <= name_length <= 128 or 8 + name_length > len(body):
        raise ValueError('Invalid Thai character name length')
    name_bytes = body[8:8 + name_length]
    if not name_bytes.endswith(b'\0') or b'\0' in name_bytes[:-1]:
        raise ValueError('Invalid Thai character name terminator')
    name = name_bytes[:-1].decode('utf-8')
    if any(ord(ch) < 32 for ch in name):
        raise ValueError('Control character in character name')
    return {'name': name, 'name_length_bytes': name_length,
            'opaque_prefix_field': prefix, 'appearance_bytes': len(body) - 8 - name_length}


def save_submission(packet, folder):
    parsed = parse_create_request(packet)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    record = {'format': 'thai-0.2.15.5-character-submission-v1',
              'status': 'submission_saved_not_yet_a_playable_character',
              'uid': 1, 'client_sha256': CLIENT_SHA256,
              'saved_at': datetime.datetime.now().astimezone().isoformat(),
              'request_sha256': hashlib.sha256(packet).hexdigest(),
              'request_base64': base64.b64encode(packet).decode('ascii'), **parsed}
    # Replace atomically; a failed experiment must not truncate an older record.
    temporary = folder / 'uid-1-submission.json.tmp'
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(folder / 'uid-1-submission.json')
    return record
