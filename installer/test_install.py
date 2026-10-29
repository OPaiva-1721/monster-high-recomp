import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
import os
import shutil
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch
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
        (self.root/'tools').mkdir()
        for name in ('port.py','lift_spurs_jobs.py'):(self.root/'tools'/name).write_text('synthetic generator')
        self.options={key:'fixture' for key in ('compiler','vcvars','ffmpeg','firmware','rpcs3')};self.options['elf']=''
        self.commands=[];self.environments=[];self.fail_stage=None
        self.addCleanup(patch.stopall)
        patch.object(install,'doctor',return_value=[]).start();patch.object(install,'check_slot').start()
        patch.object(install,'python_command',return_value=['python']).start()
        patch.object(install.subprocess,'check_output',side_effect=self.output).start()
        patch.object(install.subprocess,'run',return_value=subprocess.CompletedProcess([],0)).start()
        owner=self
        def fake_run(runner,command,cwd=None,env=None):
            runner.check();command=list(map(str,command));owner.commands.append(command);owner.environments.append(env)
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

    def test_decryptor_copies_runtime_without_original_settings(self):
        runtime=self.base/'user-rpcs3';runtime.mkdir()
        rpc=runtime/'rpcs3.exe';rpc.write_bytes(b'synthetic exe')
        (runtime/'Qt6Core.dll').write_bytes(b'synthetic DLL')
        (runtime/'config').mkdir();(runtime/'config/user.yml').write_text('personal settings')
        copied=install.isolated_decryptor(rpc,self.dest)
        self.assertNotEqual(copied,rpc);self.assertEqual(copied.read_bytes(),rpc.read_bytes())
        self.assertTrue((copied.parent/'portable').is_dir())
        self.assertFalse((copied.parent/'config').exists())
        self.assertEqual((runtime/'config/user.yml').read_text(),'personal settings')

    def test_cmd_metacharacters_refused_without_creating_destination(self):
        for char in '&|<>^':
            self.dest=self.base/('port'+char+'command')
            with self.assertRaises(ValueError):self.run_install()
            self.assertFalse(self.dest.exists())

    def test_source_cmd_metacharacters_refused_before_commands(self):
        unsafe=self.base/'dump&command';self.source.rename(unsafe);self.source=unsafe
        with self.assertRaises(ValueError):self.run_install()
        self.assertFalse(self.commands);self.assertFalse(self.dest.exists())

    def test_engine_root_cmd_metacharacters_refused_before_commands(self):
        unsafe=self.base/'repo&command';self.root.rename(unsafe);self.root=unsafe
        with self.assertRaises(ValueError):self.run_install()
        self.assertFalse(self.commands);self.assertFalse(self.dest.exists())

    def test_maintenance_environment_cannot_redirect_lift(self):
        with patch.dict('os.environ',{'LIFT_DIR':'old-maintainer-path','SYMBOL_PREFIX':'old_prefix','TITLE':'old_title'}):self.run_install()
        for command,env in zip(self.commands,self.environments):
            if any('port.py' in item for item in command):
                for name in ('LIFT_DIR','SYMBOL_PREFIX','TITLE'):self.assertTrue(name not in env,name+' must not be inherited')

    def test_source_update_reuses_verified_generation_when_inputs_unchanged(self):
        self.run_install()
        atomic_json(self.root/'installer/build.json',{'commit':'d'*40})
        self.commands.clear();self.run_install()
        self.assertFalse(any(c[-1] in ('lift','lift-spu') for c in self.commands))
        self.assertTrue(any(c[-1]=='build' for c in self.commands))

    def test_insufficient_space_leaves_destination_absent(self):
        self.profile['minimum_free_bytes']=1024
        atomic_json(self.root/'installer/game.json',self.profile)
        with patch.object(install.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError,'insuficiente'):self.run_install()
        self.assertFalse(self.dest.exists())

    def test_busy_game_does_not_create_installation(self):
        with patch.object(install,'check_slot',side_effect=RuntimeError('game occupied')):
            with self.assertRaises(RuntimeError):self.run_install()
        self.assertFalse(self.dest.exists())

    def test_existing_lock_is_preserved(self):
        self.run_install()
        lock=self.dest/'.installer/install.lock';lock.mkdir()
        old=load(self.dest/'.installer/active.json')
        with self.assertRaisesRegex(ValueError,'bloqueada'):self.run_install()
        self.assertTrue(lock.is_dir());self.assertEqual(old,load(self.dest/'.installer/active.json'))

    def test_network_failure_preserves_active_and_save(self):
        self.run_install();old=load(self.dest/'.installer/active.json')
        save=self.dest/'userdata/hdd0/save';save.write_bytes(b'keep')
        with patch.object(install,'profile',return_value=self.profile),patch('installer.update.latest_commit',side_effect=OSError('offline')):
            with self.assertRaises(OSError):install.update_install(self.dest)
        self.assertEqual(old,load(self.dest/'.installer/active.json'));self.assertEqual(save.read_bytes(),b'keep')

    def test_update_executes_pinned_new_engine_and_requires_activation(self):
        self.run_install();old=load(self.dest/'.installer/active.json');commit='f'*40
        observed=[]
        def download(repo,rev,path):
            self.assertEqual((repo,rev),(self.profile['repo'],commit));shutil.copytree(self.root,path)
        def run(runner,command,cwd=None,env=None):
            observed.append(list(map(str,command)))
        with patch.object(install,'profile',side_effect=lambda root=None:self.profile if root is None else load(Path(root)/'installer/game.json')),patch('installer.update.latest_commit',return_value=commit),patch('installer.update.download_snapshot',side_effect=download),patch.object(install.Runner,'run',run):
            with self.assertRaisesRegex(ValueError,'ativar'):install.update_install(self.dest,lambda _:None)
        self.assertEqual(old,load(self.dest/'.installer/active.json'))
        command=observed[0]
        self.assertEqual(command[0],str(self.dest/'.installer/python/Scripts/python.exe') if os.name=='nt' else str(self.dest/'.installer/python/bin/python'))
        self.assertTrue(Path(command[1]).is_relative_to(self.dest/'.installer/downloads'))
        self.assertEqual(load(Path(command[1]).parent/'build.json')['commit'],commit)
        self.assertIn('--firmware',command);self.assertIn('--source',command)


class RunnerTests(unittest.TestCase):
    def test_ctrl_c_cancels_only_runner_child(self):
        with tempfile.TemporaryDirectory() as folder:
            process=Mock(pid=123,returncode=1);process.poll.return_value=None
            cancel=Mock();cancel.is_set.side_effect=[False,True];cancel.wait.side_effect=KeyboardInterrupt
            with patch.object(install.subprocess,'Popen',return_value=process),patch.object(install.Runner,'stop_owned') as stop:
                with self.assertRaises(install.Cancelled):install.Runner(Path(folder)/'log',cancel).run(['synthetic'])
            cancel.set.assert_called_once();self.assertEqual(stop.call_args.args[0],process)

    @unittest.skipUnless(os.name=='nt','Windows shortcut')
    def test_real_shortcut_with_spaces_and_accents(self):
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/'Instalação com espaços';app=dest/'app/revisão'
            script=app/'installer/install.py';script.parent.mkdir(parents=True)
            script.write_text("from pathlib import Path\nimport sys\nPath('ran.txt').write_text(sys.argv[-1],encoding='utf-8')\n",encoding='utf-8')
            install.create_shortcuts(dest,app,Path(sys.executable))
            subprocess.run(['cmd','/d','/c',str(dest/'Jogar.cmd')],cwd=dest,check=True,capture_output=True)
            self.assertEqual((dest/'ran.txt').read_text(encoding='utf-8'),str(dest))

    def test_cancel_real_owned_process(self):
        with tempfile.TemporaryDirectory() as folder:
            cancel=threading.Event();timer=threading.Timer(1,cancel.set);timer.start()
            try:
                with self.assertRaises(install.Cancelled):
                    install.Runner(Path(folder)/'log',cancel).run([sys.executable,'-c','import time;time.sleep(30)'])
            finally:timer.cancel()
