import unittest
from lobby_diagnostics import HEADER, ROW, SIZE, decode_lobby


class LobbyDiagnosticsTests(unittest.TestCase):
    def sample(self, status=0, count=1, pid=7, token=b'a'*32):
        raw = HEADER.pack(b'ROELOB2\0', token, pid, 1, status, 0x123456, 0x654321, count)
        return raw + ROW.pack(1050001, 1) + bytes(SIZE - HEADER.size - ROW.size)

    def test_owned_quantity_is_read_from_the_lobby_snapshot(self):
        result = decode_lobby(self.sample(), b'a'*32, 7)
        self.assertEqual(result['status'], 'fields_ready')
        self.assertEqual(result['items'], [dict(template=1050001, quantity=1)])

    def test_absence_is_not_claimed_as_a_valid_inventory(self):
        result = decode_lobby(self.sample(status=1, count=0), b'a'*32, 7)
        self.assertEqual(result['status'], 'inventory_absent')
        self.assertEqual(result['items'], [])

    def test_identity_and_bounds_are_checked(self):
        for raw, token, pid in ((self.sample()[:-1], b'a'*32, 7),
                                (self.sample(), b'b'*32, 7),
                                (self.sample(), b'a'*32, 8),
                                (self.sample(count=1025), b'a'*32, 7),
                                (self.sample(status=5), b'a'*32, 7)):
            with self.assertRaises(ValueError):
                decode_lobby(raw, token, pid)
