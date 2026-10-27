"""Local TPDU v14 framing and AES codec used by the preservation experiment.

Wire layout reference: ndoa/Kelbi, metalib/protocalhandler_tqqapi.xml (MIT).
AES/tsf4g padding reference: Arrowgene.MonsterHunterOnline TqqApi/Crypto.
This module does not authenticate against any external service.
"""
import struct
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

HEADER = struct.Struct('>BBBBII')
IV = bytes(range(16))
MAX_FRAME = 1024 * 1024


def frame(command, extension=b'', body=b'', encrypted_header_length=0):
    if len(extension) + len(body) + 12 > MAX_FRAME:
        raise ValueError('Frame is too large')
    return HEADER.pack(85, 14, command, encrypted_header_length, 12 + len(extension), len(body)) + extension + body


def read_frame(connection):
    def exact(size):
        data = bytearray()
        while len(data) < size:
            part = connection.recv(size - len(data))
            if not part:
                raise EOFError('Connection ended')
            data.extend(part)
        return bytes(data)

    header = exact(12)
    magic, version, command, encrypted_length, head_length, body_length = HEADER.unpack(header)
    if magic != 85 or version != 14:
        raise ValueError('Unsupported TPDU magic/version')
    if head_length < 12 or head_length + body_length > MAX_FRAME:
        raise ValueError('Invalid TPDU frame length')
    if encrypted_length > body_length:
        raise ValueError('Encrypted header exceeds body')
    extension = exact(head_length - 12)
    body = exact(body_length)
    return command, extension, body, encrypted_length, header + extension + body


def encrypt(data, key):
    if len(key) != 16:
        raise ValueError('AES key must be 16 bytes')
    padding = 16 - len(data) % 16
    if padding < 6:
        padding += 16
    padded = data + bytes(padding - 6) + b'tsf4g' + bytes([padding])
    cipher = Cipher(algorithms.AES(key), modes.CBC(IV)).encryptor()
    return cipher.update(padded) + cipher.finalize()


def decrypt(data, key):
    if len(key) != 16 or not data or len(data) % 16:
        raise ValueError('Invalid AES key or ciphertext length')
    cipher = Cipher(algorithms.AES(key), modes.CBC(IV)).decryptor()
    plain = cipher.update(data) + cipher.finalize()
    padding = plain[-1]
    if not 6 <= padding <= 21 or padding > len(plain) or plain[-6:-1] != b'tsf4g':
        raise ValueError('Invalid tsf4g padding (key or ciphertext mismatch)')
    # The observed RoE client uses nonzero/random filler before the marker.
    # Only the marker and padding length carry protocol meaning.
    return plain[:-padding]


def auth_info(extension):
    if len(extension) < 17:
        raise ValueError('Truncated authentication header')
    method, service, auth_type, uid = struct.unpack_from('>IIII', extension)
    size = extension[16]
    if len(extension) != 17 + size:
        raise ValueError('Signature length mismatch')
    return {'encryption_method': method, 'service_id': service, 'auth_type': auth_type,
            'uid': uid, 'signature_length': size}
