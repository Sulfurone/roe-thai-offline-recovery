import tempfile
import unittest
from pathlib import Path

from peer_diagnostics import HEADER, ROW, decode_peers, read_peers,VISUAL_HEADER,VISUAL_ROW,decode_visuals,read_visuals
from self_position import SAMPLE


class PeerDiagnosticsTests(unittest.TestCase):
    def fixture(self):
        return HEADER.pack(b'ROEPEER2', b'a'*32, 123, 91, 4, 0, 730, 1000, 0xdd) + b''.join(
            ROW.pack(0x1100+i, 0x10000, 0 if i == 0 else 2,
                     0x10800000 if i == 0 else 0, 0x2300000, 2, 0,
                     0x10801000 if i == 0 else 0, 1 if i == 0 else 0,
                     100., 200., 7000.) for i in range(4))

    def test_present_absent_and_unknown_body_do_not_claim_rendering(self):
        rows = decode_peers(self.fixture(), b'a'*32, 123)['peers']
        self.assertEqual(rows[0]['status'], 'position_ready')
        self.assertEqual(rows[0]['position'], [100., 200., 7000.])
        self.assertEqual(rows[1]['status'], 'actor_absent')
        self.assertIsNone(rows[1]['position'])
        health = decode_peers(self.fixture(), b'a'*32, 123)['player_health']
        self.assertEqual((health['current'], health['maximum']), (730, 1000))

    def test_different_session_uid_or_bad_row_fails_closed(self):
        with self.assertRaises(ValueError): decode_peers(self.fixture(), b'b'*32, 123)
        with self.assertRaises(ValueError): decode_peers(self.fixture(), b'a'*32, 124)
        for offset, value in ((HEADER.size, 1), (HEADER.size+8, 99),
                              (HEADER.size+32, 3), (HEADER.size+12, 0), (56, 1001)):
            raw = bytearray(self.fixture());raw[offset:offset+4] = value.to_bytes(4, 'little')
            with self.assertRaises(ValueError): decode_peers(raw, b'a'*32, 123)

    def test_stale_pair_cannot_be_used_as_live_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            position = Path(folder)/'position.bin'
            position.write_bytes(SAMPLE.pack(b'ROEPOS1\0', b'a'*32, 123, 101, 0, 1, 2, 1., 2., 3., bytes(64)))
            position.with_name('position.bin.peers').write_bytes(self.fixture())
            stamp = position.stat().st_mtime
            self.assertEqual(read_peers(position, now=stamp)['pid'], 123)
            with self.assertRaises(ValueError): read_peers(position, now=stamp+4)

    def test_visual_fields_are_session_bound_and_never_claim_model_rendering(self):
        raw=VISUAL_HEADER.pack(b'ROEVIS2\0',b'a'*32,123,91,5)+b''.join(
            VISUAL_ROW.pack(0x10ff+i if i else 0x100,0x10000,0 if i<2 else 1,
                            0x10800000 if i<2 else 0,0xfffffffd,0x10801000,0x25a1234,0,0x010101,0) for i in range(5))
        result=decode_visuals(raw,b'a'*32,123)
        self.assertEqual(result['actors'][1]['display_mask'],'0xfffffffd')
        self.assertIn('do not prove',result['limitation'])
        for offset,value in ((VISUAL_HEADER.size,7),(VISUAL_HEADER.size+8,3),(VISUAL_HEADER.size+28,256)):
            broken=bytearray(raw);broken[offset:offset+4]=value.to_bytes(4,'little')
            with self.assertRaises(ValueError):decode_visuals(broken,b'a'*32,123)
        with self.assertRaises(ValueError):decode_visuals(raw,b'b'*32,123)
        with tempfile.TemporaryDirectory() as folder:
            position=Path(folder)/'position.bin'
            position.write_bytes(SAMPLE.pack(b'ROEPOS1\0',b'a'*32,123,101,0,1,2,1.,2.,3.,bytes(64)))
            position.with_name('position.bin.visuals').write_bytes(raw)
            stamp=position.stat().st_mtime
            self.assertEqual(read_visuals(position,now=stamp)['pid'],123)
            with self.assertRaises(ValueError):read_visuals(position,now=stamp+4)

    def test_model_snapshot_distinguishes_missing_wrapper_and_missing_model(self):
        from peer_diagnostics import VISUAL_MODEL_ROW
        rows=[]
        for i in range(5):
            rows.append(VISUAL_MODEL_ROW.pack(0x10ff+i if i else 0x100,0x10000,0,
                        0x10800000,0xffffffff,0x10801000,0x2597960,0,0x010101,0,
                        0x10802000 if i else 0,0x10803000 if i==2 else 0,1))
        raw=VISUAL_HEADER.pack(b'ROEVIS3\0',b'a'*32,123,91,5)+b''.join(rows)
        parsed=decode_visuals(raw,b'a'*32,123)['actors']
        self.assertEqual(parsed[0]['model_wrapper'],'0x0')
        self.assertEqual(parsed[1]['render_model'],'0x0')
        self.assertEqual(parsed[2]['render_model'],'0x10803000')
        for offset,value in ((VISUAL_HEADER.size+48,256),(VISUAL_HEADER.size+44,1)):
            broken=bytearray(raw);broken[offset:offset+4]=value.to_bytes(4,'little')
            with self.assertRaises(ValueError):decode_visuals(broken,b'a'*32,123)
        with self.assertRaises(ValueError):decode_visuals(raw[:-4],b'a'*32,123)


if __name__ == '__main__':
    unittest.main()
