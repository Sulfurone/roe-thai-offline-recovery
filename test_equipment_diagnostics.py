"""Observer-session binding and partial native equipment-state diagnostics."""
import tempfile
import unittest
from pathlib import Path

from equipment_diagnostics import HEADER, ROW, decode_equipment, read_equipment
from self_position import SAMPLE


class EquipmentDiagnosticsTests(unittest.TestCase):
    def fixture(self, scope=True):
        return HEADER.pack(b'ROEEQP1\0', b'a'*32, 123, 91, 2, 0x10800000) + ROW.pack(
            1, 0, 0x10801000, 0x25a1a48, 0x100101, 0, 10201, 0x10802000, 0x10803000,
            19, 30, 0, 0x10804000 if scope else 0, 0x25cebc8 if scope else 0,
            40303 if scope else 0, 0x10802000 if scope else 0,
            0x10805000 if scope else 0, 0x10806000 if scope else 0,
            1 if scope else 0, 0 if scope else 0xffffffff, 1 if scope else 0xffffffff
        ) + ROW.pack(2, 2, *([0]*17), 0xffffffff, 0xffffffff)

    def test_native_fields_and_absent_scope_are_distinguished_without_render_claim(self):
        result = decode_equipment(self.fixture(), b'a'*32, 123)
        weapon = result['weapons'][0]
        self.assertEqual((weapon['template'], weapon['scope_template'], weapon['loaded']), (10201, 40303, 19))
        self.assertTrue(weapon['ads_mode'])
        self.assertEqual(weapon['ads_model_flag'], 1)
        self.assertEqual(result['weapons'][1]['status'], 'slot_absent')
        self.assertIn('not rendered', result['limitation'])
        empty = decode_equipment(self.fixture(False), b'a'*32, 123)['weapons'][0]
        self.assertEqual(empty['scope'], '0x0')
        self.assertIsNone(empty['normal_model_flag'])

    def test_identity_layout_and_ready_ranges_fail_closed(self):
        for token, pid in ((b'b'*32, 123), (b'a'*32, 124)):
            with self.assertRaises(ValueError):
                decode_equipment(self.fixture(), token, pid)
        with self.assertRaises(ValueError):
            decode_equipment(self.fixture()[:-1], b'a'*32, 123)
        for offset, value in ((44, 0), (48, 3), (HEADER.size, 2),
                              (HEADER.size+4, 9), (HEADER.size+8, 0),
                              (HEADER.size+36, 31), (HEADER.size+72, 2),
                              (HEADER.size+76, 256)):
            raw = bytearray(self.fixture())
            raw[offset:offset+4] = value.to_bytes(4, 'little')
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                decode_equipment(raw, b'a'*32, 123)

    def test_stale_or_other_session_file_is_not_live_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            position = Path(folder)/'position.bin'
            position.write_bytes(SAMPLE.pack(b'ROEPOS1\0', b'a'*32, 123, 101, 0, 1, 2, 1., 2., 3., bytes(64)))
            equipment = position.with_name('position.bin.equipment')
            equipment.write_bytes(self.fixture())
            stamp = position.stat().st_mtime
            self.assertEqual(read_equipment(position, now=stamp)['pid'], 123)
            with self.assertRaises(ValueError):
                read_equipment(position, now=stamp+4)
            raw = bytearray(self.fixture());raw[8:40] = b'b'*32
            equipment.write_bytes(raw)
            with self.assertRaises(ValueError):
                read_equipment(position, now=stamp)


if __name__ == '__main__':
    unittest.main()
