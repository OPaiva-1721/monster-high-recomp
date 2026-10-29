import hashlib
import io
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from installer.update import safe_extract, latest_commit


def blob(body):return hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
def archive(items):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,body in items:z.writestr(name,body)
    return out.getvalue()


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.dest=Path(self.tmp.name)/'stage'

    def test_verified_snapshot(self):
        safe_extract(archive([('root/a.txt',b'good')]),self.dest,{'a.txt':blob(b'good')})
        self.assertEqual((self.dest/'a.txt').read_bytes(),b'good')

    def test_paths_links_hash_and_incomplete_rejected_before_writes(self):
        cases=[archive([(name,b'bad')]) for name in ('root/../escape','/root/a','root/a:b','root/CON','root/a.','root/a\\b')]
        cases += [archive([('root/a.txt',b'bad')]),archive([]),archive([('root/a.txt',b'good'),('other/a.txt',b'good')])]
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            link=zipfile.ZipInfo('root/a.txt');link.create_system=3;link.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(link,'elsewhere')
        cases.append(stream.getvalue())
        for data in cases:
            with self.subTest(data=len(data)),self.assertRaises(ValueError):safe_extract(data,self.dest,{'a.txt':blob(b'good')})
            self.assertFalse(self.dest.exists())

    def test_unknown_repository_never_requests_network(self):
        with patch('installer.update.request') as network:
            with self.assertRaises(ValueError):latest_commit('someone/else')
            network.assert_not_called()
