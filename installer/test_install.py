import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from installer import install
from installer.state import atomic_json, load
from installer.test_validate import sfo


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.root=self.base/'repo';self.dest=self.base/'install';self.source=self.base/'dump'
        self.game=self.source/'PS3_GAME';(self.game/'USRDIR').mkdir(parents=True)
        (self.game/'PARAM.SFO').write_bytes(sfo({'TITLE_ID':'TEST00001','APP_VER':'01.00'}))
        elf=self.game/'USRDIR/EBOOT.elf';elf.write_bytes(b'\x7fELFsynthetic')
        self.root.mkdir();self.port=self.root/'ports/test';self.port.mkdir(parents=True)
        self.patch=self.root/'patches/sdk.patch';self.patch.parent.mkdir();self.patch.write_text('synthetic')
        self.profile={'game':'test','repo':'OPaiva-1721/monster-high-recomp','title_id':'TEST00001','version':'01.00',
            'elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),'sdk_lock':'ports/test/sdk.lock.json',
            'executable':'Test.exe','controls':'controls.ini','jobs':[],'runtime_dlls':['fake.dll'],'minimum_free_bytes':0}
        atomic_json(self.root/'installer/game.json',self.profile);atomic_json(self.root/'installer/build.json',{'commit':'a'*40})
        atomic_json(self.port/'sdk.lock.json',{'upstream':'https://github.com/sp00nznet/ps3recomp','patch':'patches/sdk.patch',
            'sha256':hashlib.sha256(self.patch.read_bytes()).hexdigest(),'base':'b'*40,'expected_tree':'tree'})
        (self.port/'port.ini').write_text('[port]\nTITLE=test\n[cmake]\n[env]\nPERF=0\n')
        (self.port/'controls.ini').write_text('original')
        self.options={key:'fixture' for key in ('compiler','vcvars','ffmpeg','firmware','rpcs3')};self.options['elf']=''
        self.commands=[];self.fail_stage=None
        self.addCleanup(patch.stopall)
        patch.object(install,'doctor',return_value=[]).start();patch.object(install,'check_slot').start()
        patch.object(install,'python_command',return_value=['python']).start()
        patch.object(install.subprocess,'check_output',side_effect=self.output).start()
        patch.object(install.subprocess,'run',return_value=subprocess.CompletedProcess([],0)).start()
        owner=self
        def fake_run(runner,command,cwd=None,env=None):
            runner.check();command=list(map(str,command));owner.commands.append(command)
            if command[:2]==['git','clone']:
                path=Path(command[-1]);path.mkdir(parents=True);(path/'CMakeLists.txt').write_text('sdk')
            if 'venv' in command:
                path=Path(command[-1])/'Scripts/python.exe';path.parent.mkdir(parents=True);path.write_text('python')
            if any('port.py' in x for x in command):
                stage=command[-1]
                if owner.fail_stage==stage:raise RuntimeError('synthetic failure')
                if stage=='lift':folder=Path(cwd)/'build/lift/recompiled';names=['ppu_recomp.h','ppu.cpp']
                elif stage=='lift-spu':folder=Path(cwd)/'build/lift/spu';names=['spu_workloads.c']
                else:folder=Path(cwd)/'build/game';names=['Test.exe','fake.dll']
                folder.mkdir(parents=True,exist_ok=True)
                for name in names:(folder/name).write_text('synthetic '+name)
        patch.object(install.Runner,'run',fake_run).start()

    def output(self,cmd,**kwargs):
        result='tree\n' if 'write-tree' in cmd else b'CMakeLists.txt\0'
        return result if kwargs.get('text') else result.encode() if isinstance(result,str) else result

    def run_install(self):return install.run_install(self.source,self.dest,lambda _:None,options=self.options,root=self.root)

    def test_success_resume_preserves_userdata_and_skips_generation(self):
        self.run_install();first=load(self.dest/'.installer/active.json')
        sentinel=self.dest/'userdata/config/controls.ini';sentinel.write_text('user edit')
        save=self.dest/'userdata/hdd0/save';save.write_bytes(b'save sentinel')
        self.commands.clear();self.run_install()
        self.assertFalse(any('port.py' in ' '.join(c) for c in self.commands))
        self.assertEqual(sentinel.read_text(),'user edit');self.assertEqual(save.read_bytes(),b'save sentinel')
        self.assertEqual(first,load(self.dest/'.installer/active.json'))

    def test_failure_does_not_replace_active_and_retry_resumes(self):
        self.run_install();old=load(self.dest/'.installer/active.json')
        atomic_json(self.root/'installer/build.json',{'commit':'c'*40});self.fail_stage='build'
        with self.assertRaises(RuntimeError):self.run_install()
        self.assertEqual(old,load(self.dest/'.installer/active.json'))
        self.fail_stage=None;self.commands.clear();self.run_install()
        self.assertFalse(any(c[-1] in ('lift','lift-spu') for c in self.commands))
        self.assertEqual(load(self.dest/'.installer/previous.json'),old)

    def test_unknown_destination_space_and_busy_refuse(self):
        self.dest.mkdir();(self.dest/'personal.txt').write_text('keep')
        with self.assertRaises(ValueError):self.run_install()
        self.assertEqual((self.dest/'personal.txt').read_text(),'keep')

    def test_changed_output_rebuilds_from_affected_stage(self):
        self.run_install();app=Path(load(self.dest/'.installer/active.json')['app'])
        (app/'build/lift/spu/spu_workloads.c').write_text('corrupt')
        self.commands.clear();self.run_install()
        self.assertFalse(any(c[-1]=='lift' for c in self.commands))
        self.assertTrue(any(c[-1]=='lift-spu' for c in self.commands))

    def test_embedded_job_requires_correct_hash(self):
        elf=self.game/'USRDIR/EBOOT.elf'
        with self.assertRaises(ValueError):install.extract_jobs(elf,[{'offset':0,'size':4,'sha256':'bad','name':'job.bin'}],self.base/'jobs')
        self.assertFalse((self.base/'jobs').exists())
