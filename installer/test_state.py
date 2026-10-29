from pathlib import Path
import tempfile
import unittest
from installer.state import Journal, load


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.file=self.root/'output';self.file.write_bytes(b'valid')

    def test_complete_requires_nonempty_unchanged_outputs(self):
        journal=Journal(self.root/'state.json',self.root,{'elf':'a'})
        self.assertFalse(journal.complete('ppu'));journal.finish('ppu',[self.file]);self.assertTrue(journal.complete('ppu'))
        self.file.write_bytes(b'corrupt');self.assertFalse(journal.complete('ppu'))

    def test_input_change_and_downstream_invalidation(self):
        path=self.root/'state.json';journal=Journal(path,self.root,{'sdk':'a'})
        for stage in ('sdk','ppu','spu'):journal.finish(stage,[self.file])
        journal.invalidate_from('ppu',['sdk','ppu','spu'])
        self.assertTrue(journal.complete('sdk'));self.assertFalse(journal.complete('spu'))
        self.assertFalse(Journal(path,self.root,{'sdk':'b'}).complete('sdk'))

    def test_escape_and_missing_output_rejected(self):
        journal=Journal(self.root/'state.json',self.root,{})
        for files in ([],[self.root/'missing'],[self.root.parent/'escape']):
            with self.assertRaises(ValueError):journal.finish('ppu',files)
