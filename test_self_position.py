"""Fresh local coordinate records, drop conservation and reversible loading."""
import copy
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from self_position import PositionFeed,SAMPLE,PositionInstallation
from test_control_panel import ready_game


def sample(token='a'*32,pid=42,sequence=1,status=0,position=(100001.,200002.,7003.)):
    return SAMPLE.pack(b'ROEPOS1\0',token.encode(),pid,sequence,status,0x10800000,0x1000000,*position,bytes(64))


class SelfPositionTests(unittest.TestCase):
    def test_nonce_freshness_sequence_and_process_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'position.bin'
            feed=PositionFeed(path,'a'*32)
            def write(body,stamp=100):
                path.write_bytes(body);os.utime(path,(stamp,stamp))
            write(sample())
            self.assertEqual(feed.take(100),(100001,200002,7003))
            self.assertIsNone(feed.take(100))
            write(sample(sequence=2,position=(101001.,200002.,7003.)))
            self.assertEqual(feed.take(100),(101001,200002,7003))
            for body in (sample(sequence=3,pid=43),sample(token='b'*32,sequence=3),sample(sequence=3,status=2),
                         sample(sequence=3,position=(float('nan'),2.,3.)),bytes(136),sample(sequence=3)[:-1]):
                write(body);self.assertIsNone(feed.take(100))
            write(sample(sequence=3),98)
            self.assertIsNone(feed.take(100))

    def test_fresh_self_position_drives_drop_and_repickup_after_old_packet(self):
        game=ready_game()
        game.require_self_position_for_drop=True
        old=game.player_position
        current=(old[0]+15000,old[1]+10000,old[2])
        with patch('offline_gameplay.time.monotonic',return_value=100):
            self.assertTrue(game.accept_self_position(current))
            # A sparse/keyframe DTO does not replace the separate live sample.
            game.player_position=old
            original=game.inventory.items[2,0]
            game.handle(0x3e80,struct.pack('>BBHHQB',2,2,0,5,0,1))
        stack=list(game.ground_loot.stacks.values())[-1]
        self.assertEqual(stack.position,(*current[:2],current[2]+30))
        self.assertEqual(stack.item.count,5)
        self.assertEqual(game.last_drop_event['source'],'client_self_read')
        camera=(*current[:2],current[2]+170)
        replies=game.handle(0x3b63,struct.pack('>IIQBHB3iB',stack.entity,0,0,0,0,1,*camera,0))
        self.assertEqual(replies[0][0],0x3e82)
        self.assertEqual(sum(i.count for i in game.inventory.items.values() if i.template==original.template),original.count)

    def test_missing_or_stale_self_position_never_removes_the_item(self):
        for stamp in (None,98):
            game=ready_game();game.require_self_position_for_drop=True
            game.self_position_at=stamp
            game.self_position=(100000,200000,7000)
            inventory=copy.deepcopy(game.inventory.items)
            ground=copy.deepcopy(game.ground_loot.stacks)
            with patch('offline_gameplay.time.monotonic',return_value=100):
                replies=game.handle(0x3e80,struct.pack('>BBHHQB',2,2,0,5,0,1))
            self.assertEqual(replies,[game.inventory.delta([(2,0)]),game.inventory.reply(2,1)])
            self.assertEqual(game.inventory.items,inventory)
            self.assertEqual(game.ground_loot.stacks,ground)
            self.assertEqual(game.last_drop_event['reason'],'self_position_not_fresh')

    def test_missing_live_position_does_not_populate_or_manually_spawn_at_old_point(self):
        from control_actions import ControlSession
        from offline_population import WorldPopulation
        from test_population import Surface
        game=ready_game();game.require_self_position_for_drop=True
        game.player_position=(100000,200000,7250)
        control=ControlSession(game)
        population=WorldPopulation(control,Surface(),42,vehicles=False)
        self.assertEqual(population.tick(),[])
        self.assertIsNone(control.snapshot()['position'])
        with self.assertRaisesRegex(ValueError,'尚未同步'):
            control.execute(dict(action='item',template=70001))
        self.assertEqual(control.execute(dict(action='weather',weather_id=2))[0][0][0],0x4817)
        game.accept_self_position((100010,200000,7250))
        self.assertTrue(population.tick())
        self.assertEqual(control.snapshot()['position'],[100010,200000,7250])

    def test_self_read_cannot_replace_flight_or_unready_actor(self):
        game=ready_game()
        for ready,seated in ((False,False),(True,True)):
            game.actor_ready,game.seated=ready,seated
            original=game.player_position
            self.assertFalse(game.accept_self_position((1,2,3)))
            self.assertEqual(game.player_position,original)

    def test_forwarder_install_restore_is_hash_checked_and_keeps_running_game_files(self):
        import self_position
        with tempfile.TemporaryDirectory() as folder:
            game=Path(folder)/'game';game.mkdir()
            (game/'Europa_Client.exe').write_bytes(b'synthetic exe never executed')
            original=b'original two-export fixture';proxy=b'own forwarder fixture'
            (game/'DataEngine.dll').write_bytes(original)
            built=Path(folder)/'observer.dll';built.write_bytes(proxy)
            work=Path(folder)/'session'
            with patch.object(self_position,'ORIGINAL_SHA',self_position.sha(original)), \
                 patch.object(self_position,'verify_proxy'),patch.object(self_position,'verify_built'), \
                 patch.object(self_position,'game_stopped',return_value=True):
                observer=PositionInstallation(game,work,built)
                observer.__enter__()
                self.assertEqual((game/'DataEngine.dll').read_bytes(),proxy)
                self.assertEqual((game/'_ROE_Original_DataEngine.dll').read_bytes(),original)
                with patch.object(self_position,'game_stopped',return_value=False):
                    self.assertFalse(observer.restore())
                    self.assertEqual((game/'DataEngine.dll').read_bytes(),proxy)
                self.assertTrue(observer.restore())
                self.assertEqual((game/'DataEngine.dll').read_bytes(),original)
                self.assertFalse((game/'_ROE_Original_DataEngine.dll').exists())

    def test_startup_rejects_an_old_library_after_source_change_or_failed_build(self):
        import json
        import self_position
        with tempfile.TemporaryDirectory() as folder:
            dll=Path(folder)/'own.dll';dll.write_bytes(b'own synthetic module')
            sources={'own-test-source':'a'*64}
            record=dict(format='roe-self-position-build-v1',dll_sha256=self_position.sha(dll.read_bytes()),
                        sources=sources,accessor_tests_passed=True)
            manifest=dll.with_suffix('.build.json')
            manifest.write_text(json.dumps(record),encoding='utf8')
            with patch.object(self_position,'source_digests',return_value=sources):
                self_position.verify_built(dll)
                dll.write_bytes(b'old module')
                with self.assertRaises(ValueError):self_position.verify_built(dll)
            with patch.object(self_position,'source_digests',return_value={'own-test-source':'b'*64}):
                with self.assertRaises(ValueError):self_position.verify_built(dll)


if __name__=='__main__':unittest.main()
