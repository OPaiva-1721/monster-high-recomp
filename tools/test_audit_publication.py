"""Publication checks use synthetic repositories, never user game data."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from audit_publication import audit_repository

class PublicationAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.git('init','-q');self.git('config','user.name','fixture');self.git('config','user.email','fixture@example.invalid')
    def git(self,*args):
        return subprocess.run(['git','-C',str(self.root),*args],check=True,capture_output=True)
    def commit(self,name,data):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        self.git('add','--',name);self.git('commit','-qm','synthetic fixture')
    def test_source_is_allowed(self):
        self.commit('tools/example.py',b'print("hello")\n')
        self.assertEqual(audit_repository(self.root,True)['blockers'],[])
    def test_history_retains_removed_game_data(self):
        self.commit('assets/game.iso',b'synthetic not a real game')
        self.git('rm','assets/game.iso');self.git('commit','-qm','remove fixture')
        self.assertEqual(audit_repository(self.root,False)['blockers'],[])
        self.assertTrue(any('assets/game.iso'==x['path'] for x in audit_repository(self.root,True)['blockers']))
    def test_history_checks_all_paths_for_same_blob(self):
        self.commit('game.iso',b'synthetic shared content')
        self.git('mv','game.iso','source.txt');self.git('commit','-qm','rename fixture')
        self.assertTrue(any(x['path']=='game.iso' for x in audit_repository(self.root,True)['blockers']))
    def test_generated_and_renamed_binary_are_rejected(self):
        self.commit('ports/demo/recompiled/ppu_recomp.h',b'// synthetic generated file')
        self.commit('ordinary.txt',bytes([0x7f,69,76,70])+b'synthetic binary')
        paths={x['path'] for x in audit_repository(self.root,True)['blockers']}
        self.assertEqual(paths,{'ports/demo/recompiled/ppu_recomp.h','ordinary.txt'})
    def test_secret_value_is_not_in_report(self):
        fake=('gh'+'p_'+'A'*36).encode()
        self.commit('config.txt',fake)
        report=audit_repository(self.root,True)
        self.assertTrue(report['blockers'])
        self.assertNotIn(fake.decode(),json.dumps(report))
    def test_untracked_file_not_published_and_rom_readme_allowed(self):
        self.commit('rom/LEIA-ME.md',b'Use your own copy.')
        (self.root/'local.iso').write_bytes(b'private fixture')
        self.assertEqual(audit_repository(self.root,True)['blockers'],[])

if __name__=='__main__':unittest.main()
