import struct
import unittest

from offline_glass import GlassState


class GlassTests(unittest.TestCase):
    def test_uses_original_hit_context_and_records_break_only_once(self):
        actor=0x1000000000100
        pane=52281
        position=(370315,311631,10951)
        glass=GlassState({pane:position})
        context=struct.pack('<QI3f',actor,0,*position)+bytes(48)
        report=struct.pack('>4I',pane,1,1000,72)+context
        self.assertEqual(glass.handle(report,actor+1),[])
        self.assertEqual(glass.handle(report[:16]+struct.pack('<QI3f',actor,0,0,0,0)+bytes(48),actor),[])
        self.assertEqual(glass.handle(report,actor),
                         [(0x6f56,struct.pack('>6I',1,pane,0,1,0,72)+context)])
        self.assertEqual(glass.handle(report,actor),[])
