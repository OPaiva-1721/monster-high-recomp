import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from installer.validate import read_sfo, validate_source, reject_overlap


def sfo(values):
    keys, data, rows = b'', b'', []
    for key, value in values.items():
        raw = value.encode() + b'\0'
        rows.append(struct.pack('<HHIII', len(keys), 0x204, len(raw), len(raw), len(data)))
        keys += key.encode() + b'\0';data += raw
    base = 20 + len(rows) * 16
    return struct.pack('<5I', 0x46535000, 0x101, base, base + len(keys), len(rows)) + b''.join(rows) + keys + data


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()/'cópia com espaço';self.game=self.root/'PS3_GAME'
        (self.game/'USRDIR').mkdir(parents=True)
        (self.game/'PARAM.SFO').write_bytes(sfo({'TITLE_ID':'TEST00001','APP_VER':'01.00'}))
        self.elf=self.game/'USRDIR/EBOOT.elf';self.elf.write_bytes(b'\x7fELFsynthetic')
        self.profile={'title_id':'TEST00001','version':'01.00','elf_sha256':hashlib.sha256(self.elf.read_bytes()).hexdigest()}

    def test_valid_source_and_direct_ps3_game(self):
        for path in (self.root,self.game):self.assertEqual(validate_source(path,self.profile)['elf_sha256'],self.profile['elf_sha256'])

    def test_wrong_title_version_and_hash(self):
        for key in ('title_id','version','elf_sha256'):
            with self.assertRaises(ValueError):validate_source(self.root,{**self.profile,key:'wrong'})

    def test_truncated_sfo(self):
        (self.game/'PARAM.SFO').write_bytes(b'\0PSF')
        with self.assertRaises(ValueError):read_sfo(self.game/'PARAM.SFO')

    def test_missing_elf_and_overlapping_destination(self):
        self.elf.unlink()
        with self.assertRaises(ValueError):validate_source(self.root,self.profile)
        for path in (self.root,self.root/'new',self.root.parent):
            with self.assertRaises(ValueError):reject_overlap(self.root,path)
