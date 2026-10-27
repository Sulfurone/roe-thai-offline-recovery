import socket
import struct
import unittest
from pathlib import Path

from tpdu import auth_info, decrypt, encrypt, frame, read_frame


ROOT = Path(__file__).resolve().parent


class ProtocolTests(unittest.TestCase):
    def test_captured_authentication_frame(self):
        original = (ROOT / 'logs/20261026-102842/connection-1.bin').read_bytes()
        sender, receiver = socket.socketpair()
        self.addCleanup(sender.close)
        self.addCleanup(receiver.close)
        for block in [original[:2], original[2:9], original[9:35], original[35:]]:
            sender.sendall(block)
        command, extension, body, enc_length, wire = read_frame(receiver)
        self.assertEqual((command, body, enc_length, wire), (3, b'', 0, original))
        self.assertEqual(auth_info(extension), {
            'encryption_method': 3, 'service_id': 0, 'auth_type': 3,
            'uid': 1, 'signature_length': 72,
        })

    def test_real_client_padding_and_application_message(self):
        data = (ROOT / 'logs/handshake-20261026-105018/1-received.bin').read_bytes()
        offset = 0
        found = False
        while offset < len(data):
            magic, version, command, enc_length, head, body = struct.unpack_from('>BBBBII', data, offset)
            self.assertEqual((magic, version), (85, 14))
            packet = data[offset:offset + head + body]
            if command == 0:
                plain = decrypt(packet[head:], bytes(16))[enc_length:]
                self.assertEqual(int.from_bytes(plain[:4], 'big'), len(plain))
                self.assertEqual(int.from_bytes(plain[4:6], 'big'), 0x02f0)
                found = True
            offset += head + body
        self.assertTrue(found)

    def test_padding_boundaries_and_wrong_key(self):
        for size in range(65):
            with self.subTest(size=size):
                message = bytes(range(size))
                self.assertEqual(decrypt(encrypt(message, bytes(16)), bytes(16)), message)
        with self.assertRaises(ValueError):
            decrypt(encrypt(b'challenge', bytes(16)), bytes([1]) * 16)

    def test_invalid_and_truncated_frames(self):
        for packet in [b'BAD\0' + struct.pack('>II', 12, 0),
                       b'\x55\x0e\0\0' + struct.pack('>II', 11, 0),
                       b'\x55\x0e\0\0' + struct.pack('>II', 12, 2**24)]:
            sender, receiver = socket.socketpair()
            try:
                sender.sendall(packet)
                with self.assertRaises(ValueError):
                    read_frame(receiver)
            finally:
                sender.close()
                receiver.close()
        sender, receiver = socket.socketpair()
        try:
            sender.sendall(frame(0, body=b'abcd')[:-1])
            sender.close()
            with self.assertRaises(EOFError):
                read_frame(receiver)
        finally:
            sender.close()
            receiver.close()


if __name__ == '__main__':
    unittest.main()
