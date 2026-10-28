import tempfile
from pathlib import Path
import unittest

from ingame_bridge import IngameMailbox, IngameInstallation
from offline_control import ControlHub


class IngameBridgeTests(unittest.TestCase):
    def test_partial_authenticated_command_and_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            mailbox = IngameMailbox(Path(folder) / 'private')
            hub = ControlHub()
            hub.update(connected=True, ready=True)
            line = f'{mailbox.token}\t1\tweather\t2\t30\t0\t0\n'
            mailbox.command_path.write_bytes(line[:20].encode())
            mailbox.poll(hub)
            self.assertIsNone(hub.take())
            with mailbox.command_path.open('ab') as f:
                f.write(line[20:].encode())
            mailbox.poll(hub)
            command = hub.take()
            self.assertEqual(command['weather_id'], 2)
            hub.finish(command['id'], 'sent', '晴天已发送')
            mailbox.publish(hub.snapshot())
            self.assertIn('status=sent', mailbox.status_path.read_text(encoding='utf-8'))
            with mailbox.command_path.open('ab') as f:
                f.write(line.encode())
            mailbox.poll(hub)
            self.assertIsNone(hub.take())
            self.assertEqual(mailbox.last_result[1], 'failed')

    def test_wrong_session_and_offline_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            mailbox = IngameMailbox(Path(folder) / 'private')
            hub = ControlHub()
            mailbox.command_path.write_text('wrong\t1\tweapon\t10201\t60\t3\t1\n', encoding='ascii')
            mailbox.poll(hub)
            self.assertIsNone(hub.take())
            with mailbox.command_path.open('ab') as f:
                f.write(f'{mailbox.token}\t1\tweapon\t10201\t60\t3\t1\n'.encode())
            mailbox.poll(hub)
            self.assertIsNone(hub.take())
            self.assertEqual(mailbox.last_result[1], 'failed')

    def test_installation_preserves_existing_marker_and_cleans_owned_lua(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            game = root / 'game'
            game.mkdir()
            (game / 'Europa_Client.exe').write_bytes(b'test identity only; never executed')
            (game / 'FileDriven').mkdir()
            marker = game / 'FileDriven/_GM_CONTROL_'
            marker.write_bytes(b'user-owned')
            mailbox = IngameMailbox(root / 'private')
            with IngameInstallation(game, mailbox):
                self.assertTrue((game / 'ROE_OfflineMenu.lua').is_file())
                self.assertTrue((game / 'Data/ScriptCustom/ROE_OfflineMenu.lua').is_file())
                self.assertIn('ROE_OfflineMenu.lua', (game / 'Data/ScriptCustom/LoadConfig.lua').read_text())
                self.assertEqual(marker.read_bytes(), b'user-owned')
            self.assertFalse((game / 'ROE_OfflineMenu.lua').exists())
            self.assertFalse((game / 'Data/ScriptCustom/ROE_OfflineMenu.lua').exists())
            self.assertFalse((game / 'Data/ScriptCustom/LoadConfig.lua').exists())
            self.assertEqual(marker.read_bytes(), b'user-owned')

    def test_installation_rolls_back_collision_and_retains_edited_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            game = root / 'game'
            game.mkdir()
            (game / 'Europa_Client.exe').write_bytes(b'test identity only; never executed')
            custom = game / 'Data/ScriptCustom/ROE_OfflineMenu.lua'
            custom.parent.mkdir(parents=True)
            custom.write_text('user-owned', encoding='utf-8')
            mailbox = IngameMailbox(root / 'private')
            with self.assertRaises(ValueError):
                with IngameInstallation(game, mailbox):
                    pass
            self.assertFalse((game / 'ROE_OfflineMenu.lua').exists())
            self.assertEqual(custom.read_text(), 'user-owned')
            # Use a separate temporary client; the conflicting file belongs to the test user.
            game2 = root / 'game2'
            game2.mkdir()
            (game2 / 'Europa_Client.exe').write_bytes(b'test identity only; never executed')
            installation = IngameInstallation(game2, IngameMailbox(root / 'private'))
            with installation:
                (game2 / 'ROE_OfflineMenu.lua').write_text('edited after install', encoding='utf-8')
            self.assertEqual((game2 / 'ROE_OfflineMenu.lua').read_text(), 'edited after install')
            self.assertEqual(len(installation.owned), 1)


if __name__ == '__main__':
    unittest.main()
