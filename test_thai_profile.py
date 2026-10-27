import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from thai_profile import parse_create_request, save_submission

ROOT = Path(__file__).resolve().parent


class ThaiSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.packet = (ROOT / 'profiles/uid-1-create-request.bin').read_bytes()

    def test_native_submission_name_and_appearance_boundaries(self):
        record = parse_create_request(self.packet)
        self.assertTrue(record['name'])
        self.assertEqual(len(record['name'].encode('utf-8')) + 1, record['name_length_bytes'])
        self.assertEqual(record['appearance_bytes'], 1240)

    def test_malformed_and_wrong_message_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_create_request(self.packet[:-1])
        wrong = bytearray(self.packet)
        wrong[5] = 0xf0
        with self.assertRaises(ValueError):
            parse_create_request(wrong)
        wrong = bytearray(self.packet)
        wrong[30:34] = (0xffffffff).to_bytes(4, 'big')
        with self.assertRaises(ValueError):
            parse_create_request(wrong)

    def test_saved_record_preserves_exact_native_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = save_submission(self.packet, temporary)
            loaded = json.loads((Path(temporary) / 'uid-1-submission.json').read_text(encoding='utf-8'))
            self.assertEqual(record, loaded)
            self.assertEqual(base64.b64decode(loaded['request_base64']), self.packet)
            self.assertEqual(loaded['request_sha256'], hashlib.sha256(self.packet).hexdigest())
            self.assertFalse((Path(temporary) / 'uid-1-submission.json.tmp').exists())
            self.assertEqual(loaded['status'], 'submission_saved_not_yet_a_playable_character')


if __name__ == '__main__':
    unittest.main()
