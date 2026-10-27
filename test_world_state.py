import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from offline_gameplay import OfflineGameplay
from offline_world_state import MAX_WORLD_BYTES
from test_ground_loot import request,drop


class WorldStateTests(unittest.TestCase):
    def open(self,path):
        game=OfflineGameplay(inventory_enabled=True,ground_loot_enabled=True,world_file=path)
        game.handle(0x2a,struct.pack('>I3i',1,325800,271700,6488))
        return game

    def test_restart_keeps_ground_stack_and_does_not_regenerate_picked_seed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'world.json'
            game=self.open(path)
            game.handle(0x3b63,request())
            game.handle(0x3e80,drop())
            saved=path.read_bytes()
            restored=self.open(path)
            self.assertEqual(restored.reserve,160)
            self.assertEqual(restored.ground_loot.stacks,game.ground_loot.stacks)
            self.assertNotIn(0x400001,restored.ground_loot.stacks)
            self.assertEqual(path.read_bytes(),saved)
            self.assertFalse(restored.save_state())
            restored.handle(0x3b63,request(0x400002))
            reopened=self.open(path)
            self.assertEqual(reopened.reserve,180)
            self.assertEqual(reopened.ground_loot.stacks,{})
            self.assertEqual(reopened.ground_loot.next_entity,0x400003)
            self.assertFalse(path.with_suffix('.json.tmp').exists())

    def test_world_profile_preserves_fired_ammo_and_slot_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'world.json'
            game=self.open(path)
            game.handle(0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,7,0))
            game.handle(0x49c,struct.pack('>I',1))
            game.handle(0x3e80,struct.pack('>BBHBHHB',1,1,1,1,2,1,1))
            game.handle(0x49e,struct.pack('>I',2))
            restored=self.open(path)
            self.assertEqual((restored.magazine,restored.reserve,restored.selected_slot),(30,119,2))
            self.assertEqual(restored.inventory.weapon_slot(),2)
            self.assertEqual(len(restored.ground_loot.stacks),1)

    def test_failed_commit_restores_both_sides_and_returns_no_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'world.json'
            game=self.open(path)
            saved=path.read_bytes()
            before=game.state_payload()
            for message,body in [(0x3b63,request()),(0x3e80,drop()),
                                 (0x11d3,struct.pack('>6fIB',1,2,3,1,102,3,7,0))]:
                with patch('offline_world_state.write_atomic',side_effect=OSError('test disk write failed')):
                    with self.assertRaisesRegex(OSError,'test disk write failed'):
                        game.handle(message,body)
                self.assertEqual(game.state_payload(),before)
                self.assertEqual(path.read_bytes(),saved)
                self.assertTrue(game.ground_loot.announced)

    def test_failed_atomic_replace_keeps_last_complete_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'world.json'
            game=self.open(path)
            before=path.read_bytes()
            with patch.object(Path,'replace',side_effect=OSError('replace failed')):
                with self.assertRaisesRegex(OSError,'replace failed'):
                    game.handle(0x3e80,drop())
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(game.reserve,120)
            # An uncommitted temp file is not loaded on the next start.
            self.assertEqual(self.open(path).reserve,120)

    def test_invalid_cross_container_identities_and_unknown_map_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'world.json'
            valid=json.loads(self.open(path).state_payload())
            mutations=[
                lambda x:x.update(map_id=1),lambda x:x.update(version=True),
                lambda x:x['ground']['stacks'][0]['item'].update(uid=x['inventory']['items'][0]['uid']),
                lambda x:x['ground']['stacks'][0]['item'].update(count=1000),
                lambda x:x['ground']['stacks'][0]['position'].__setitem__(0,True),
                lambda x:x['ground'].update(next_entity=0x400001),
                lambda x:x['ground']['stacks'].append(copy.deepcopy(x['ground']['stacks'][0]))]
            for mutate in mutations:
                data=copy.deepcopy(valid)
                mutate(data)
                text=json.dumps(data)
                path.write_text(text,encoding='utf-8')
                with self.assertRaises(ValueError):self.open(path)
                self.assertEqual(path.read_text(encoding='utf-8'),text)

    def test_corrupt_and_oversized_profiles_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'world.json'
            for content in ('{broken','x'*(MAX_WORLD_BYTES+1)):
                path.write_text(content,encoding='utf-8')
                with self.assertRaises(ValueError):self.open(path)
                self.assertEqual(path.read_text(encoding='utf-8'),content)

    def test_inventory_only_profile_remains_separate_and_unmodified(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'inventory.json'
            old=OfflineGameplay(inventory_enabled=True,state_file=path)
            old.save_state()
            content=path.read_bytes()
            with self.assertRaises(ValueError):self.open(path)
            self.assertEqual(path.read_bytes(),content)
            with self.assertRaises(ValueError):
                OfflineGameplay(inventory_enabled=True,world_file=Path(temporary)/'new.json')


if __name__=='__main__':unittest.main()
