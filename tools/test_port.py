"""Pipeline contract tests with fake tools; never opens a game or a ROM."""
import contextlib
import io
import os
import subprocess
import struct
from pathlib import Path
import tempfile
import sys
import time
import unittest
from unittest.mock import patch

import port

class InteractiveProcessTests(unittest.TestCase):
    def test_interactive_waits_without_timeout_or_kill(self):
        with tempfile.TemporaryDirectory() as folder:
            cwd=Path(folder)
            with patch.object(port,'ensure_game_slot') as guard, patch.object(port.subprocess,'Popen') as spawn:
                proc=spawn.return_value;proc.pid=123;proc.wait.return_value=0
                port.run_game(['synthetic-game'],{},cwd,cwd/'run.log',None)
                guard.assert_called_once_with()
                proc.wait.assert_called_once_with()
                proc.kill.assert_not_called()
                self.assertTrue((cwd/'interactive-session.json').exists())

    def test_busy_slot_refuses_without_spawning(self):
        with tempfile.TemporaryDirectory() as folder:
            cwd=Path(folder)
            with patch.object(port,'ensure_game_slot',side_effect=ValueError('busy')), patch.object(port.subprocess,'Popen') as spawn:
                with self.assertRaises(ValueError):port.run_game(['synthetic-game'],{},cwd,cwd/'run.log',None)
                spawn.assert_not_called()


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='port test ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        folder = self.root / 'ports' / 'fixture'
        folder.mkdir(parents=True)
        (folder / 'port.ini').write_text(
            '[port]\nEBOOT_ELF=rom/EBOOT.elf\nEBOOT_BIN=rom/EBOOT.BIN\n'
            '[env]\nPS3_VERBOSE=0\nPAD_SCRIPT=1:0x0008\n', encoding='utf-8')
        self.addCleanup(patch.stopall)
        patch.object(port, 'ROOT', self.root).start()
        patch.dict(os.environ, {}, clear=True).start()
        self.run = patch.object(port.subprocess, 'run').start()
        self.game = patch.object(port, 'run_game').start()
        patch.object(port.shutil, 'copy2').start()
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def test_dry_run_all_stages_has_no_side_effects(self):
        for stage in port.STAGES:
            port.main(['fixture', stage, '--dry-run'])
        self.run.assert_not_called()
        self.game.assert_not_called()
        self.assertFalse((self.root / 'build').exists())

    def test_lift_outputs_and_order(self):
        port.main(['fixture', 'lift'])
        commands = [c.args[0] for c in self.run.call_args_list]
        self.assertEqual([Path(c[1]).name for c in commands],
                         ['ppu_loader.py', 'ppu_lifter.py', 'gen_hle_nids.py'])
        self.assertIn(str(self.root / 'build/fixture-lift/out/EBOOT.functions.json'), commands[1])

    def test_lift_arguments_from_profile(self):
        with patch.dict(os.environ,{'LIFT_ARGS':'--fast-mem --jobs 2 --chunks 48'}):
            port.main(['fixture','lift'])
        command=self.run.call_args_list[1].args[0]
        self.assertEqual(command[-5:],['--fast-mem','--jobs','2','--chunks','48'])

    def test_shared_lift_is_read_only(self):
        with patch.dict(os.environ, {'RECOMP_DIR': str(self.root.parent / 'shared')}):
            with self.assertRaises(ValueError):
                port.main(['fixture', 'lift'])
        self.run.assert_not_called()

    def test_cap_environment_and_cli_overrides(self):
        with patch.dict(os.environ, {'PAD_SCRIPT': '2:0x4000', 'CAP_FRAMES': '42:2:3'}):
            port.main(['fixture', 'cap'])
        call = self.game.call_args
        env = call.args[1]
        self.assertEqual(env['PAD_SCRIPT'], '2:0x4000')
        self.assertEqual(env['RSX_CAP'], '42:2:3')
        self.assertEqual(env['PS3_VERBOSE'], '0')
        self.assertTrue(Path(env['PS3_HDD0_ROOT']).is_relative_to(self.root / 'build'))
        self.assertEqual(Path(call.args[0][-1]).name, 'EBOOT.elf')
        self.assertEqual(call.args[4], 130)
        if os.name == 'nt':
            self.assertIn('port_topng.ps1', str(self.run.call_args))

    def test_seconds_override(self):
        with patch.dict(os.environ, {'RUN_SECONDS': '7'}):
            port.main(['fixture', 'run', '--seconds', '0.2'])
            self.assertEqual(self.game.call_args.args[4], 0.2)
            port.main(['fixture', 'run'])
            self.assertEqual(self.game.call_args.args[4], 7)

    def test_local_ini_overrides_example_and_environment_still_wins(self):
        local=self.root/'ports/fixture/port.local.ini'
        local.write_text('[port]\nEBOOT_ELF=rom/local.elf\nRUN_SECONDS=8\n',encoding='utf-8')
        port.main(['fixture','run'])
        self.assertEqual(Path(self.game.call_args.args[0][-1]).name,'local.elf')
        self.assertEqual(self.game.call_args.args[4],8)
        with patch.dict(os.environ,{'EBOOT_ELF':'rom/override.elf'}):
            port.main(['fixture','run'])
        self.assertEqual(Path(self.game.call_args.args[0][-1]).name,'override.elf')

    def test_relative_runtime_paths_are_relative_to_repository(self):
        ini=self.root/'ports/fixture/port.ini'
        ini.write_text(ini.read_text()+'PS3_VFS_ROOT=rom/fixture/game\nPAD_CONFIG=ports/fixture/controls.ini\n',encoding='utf-8')
        port.main(['fixture','run'])
        env=self.game.call_args.args[1]
        self.assertEqual(Path(env['PS3_VFS_ROOT']),self.root/'rom/fixture/game')
        self.assertEqual(Path(env['PAD_CONFIG']),self.root/'ports/fixture/controls.ini')

    def test_interactive_has_no_timeout_or_scripted_input(self):
        with patch.dict(os.environ,{'PAD_SCRIPT':'1:0x4000','PAD_FILE':'private.txt','PAD_STICK':'0,0,0,0','RSX_GPU_TIMING':'1','PERF':'1'}):
            port.main(['fixture','run','--interactive'])
        args=self.game.call_args.args
        self.assertIsNone(args[4])
        for key in ('PAD_SCRIPT','PAD_FILE','PAD_STICK','RSX_GPU_TIMING'):
            self.assertNotIn(key,args[1])
        self.assertEqual(args[1]['PERF'],'0')

    def test_interactive_only_for_run_without_seconds(self):
        for args in (['fixture','cap','--interactive'],['fixture','run','--interactive','--seconds','4']):
            with self.assertRaises(SystemExit):port.main(args)
        self.game.assert_not_called()

    def test_multi_frame_report_and_sheet_command(self):
        def capture(*args):
            for i, manifest in enumerate(args[5]):
                manifest.parent.mkdir(parents=True)
                manifest.write_text('header DRAW\nop000 CLEAR\n' + 'op001 DRAW  rt=0\n' * i)
        self.game.side_effect = capture
        with patch.dict(os.environ, {'CAP_FRAMES': '42:5:3'}):
            port.main(['fixture', 'cap'])
        self.assertIn('frame_00: DRAW=0', self.output.getvalue())
        self.assertIn('frame_04: DRAW=4', self.output.getvalue())
        if os.name == 'nt':
            self.assertEqual(self.run.call_args.args[0][-2:], ['-FrameCount', '5'])

    def test_missing_manifest_report(self):
        port.report_draws([self.root / 'frame_00/manifest.txt'])
        self.assertIn('frame_00: manifest missing', self.output.getvalue())

    def test_invalid_seconds(self):
        for seconds in ('0', '-1', 'nan', 'inf'):
            with self.assertRaises(ValueError):
                port.main(['fixture', 'run', '--seconds', seconds])
        self.game.assert_not_called()

    def test_stale_capture_rejected(self):
        manifest = self.root / 'build/fixture-cap/frame_00/manifest.txt'
        manifest.parent.mkdir(parents=True)
        manifest.write_text('old capture')
        with self.assertRaises(ValueError):
            port.main(['fixture', 'cap'])
        self.game.assert_not_called()

    def test_capture_timeout_still_converts(self):
        with patch.dict(os.environ, {'RUN_SECONDS': '.1'}):
            port.main(['fixture', 'cap'])
        self.assertEqual(self.game.call_args.args[4], .1)
        if os.name == 'nt':
            self.assertIn('port_topng.ps1', str(self.run.call_args))

    def test_build_never_runs_game(self):
        port.main(['fixture', 'build'])
        self.assertTrue(self.run.called)
        for call in self.run.call_args_list:
            self.assertNotIn('EBOOT.elf', ' '.join(call.args[0]))

    def test_external_hdd_rejected(self):
        with patch.dict(os.environ, {'HDD0_DIR': str(self.root.parent / 'user-hdd')}):
            with self.assertRaises(ValueError):
                port.main(['fixture', 'run'])
        self.run.assert_not_called()

    def test_tool_failure_stops_lift(self):
        self.run.side_effect = port.subprocess.CalledProcessError(7, 'fake loader')
        with self.assertRaises(port.subprocess.CalledProcessError):
            port.main(['fixture', 'lift'])
        self.assertEqual(self.run.call_count, 1)

    def test_spu_includes_dumped_jobs(self):
        jobs = self.root / 'build/fixture-lift/spujobs'
        jobs.mkdir(parents=True)
        (jobs / 'spujob_FAKE_1.bin').write_bytes(b'fixture')
        port.main(['fixture', 'lift-spu'])
        commands = [c.args[0] for c in self.run.call_args_list]
        self.assertEqual([Path(c[1]).name for c in commands],
                         ['extract_spu_images.py', 'build_spu_workloads.py', 'lift_spurs_jobs.py'])
        self.assertEqual(commands[-1][-2:], ['--sdk', str(self.root / 'external/ps3recomp')])


@unittest.skipUnless(os.name == 'nt', 'System.Drawing converter requires Windows')
class SheetTests(unittest.TestCase):
    def test_45_full_size_24bit_bitmaps(self):
        converter = Path(__file__).resolve().with_name('port_topng.ps1')
        with tempfile.TemporaryDirectory(prefix='full size sheet test ') as folder:
            root = Path(folder)
            width, height = 1280, 720
            size = width * height * 3
            header = (struct.pack('<2sIHHI', b'BM', 54 + size, 0, 0, 54)
                      + struct.pack('<IiiHHIIiiII', 40, width, height, 1, 24,
                                    0, size, 2835, 2835, 0, 0))
            for frame in range(5):
                directory = root / f'frame_{frame:02d}'
                directory.mkdir()
                # Match the real capture: nine uncompressed 24-bit BMPs/frame.
                for image in range(9):
                    name = 'backbuffer' if image == 0 else f'rt_{image}'
                    pixels = bytes((image * 20, 0, 30 + frame * 40)) * (width * height)
                    (directory / f'{name}.bmp').write_bytes(header + pixels)
            # Model an interrupted RT write and an invalid backbuffer. The sheet
            # must still render the other slots and leave the missing one black.
            (root / 'frame_04/rt_truncated.bmp').write_bytes(header + bytes(1990602))
            (root / 'frame_02/backbuffer.bmp').write_bytes(b'invalid BMP')
            fixture = root / 'verify.ps1'
            fixture.write_text(r'''
param($Directory, $Converter)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
& $Converter -Directory $Directory -FrameCount 5
$pngs = @(Get-ChildItem -LiteralPath $Directory -Filter '*.png' -Recurse)
if ($pngs.Count -ne 45) { throw "Expected 44 PNGs + sheet; got $($pngs.Count)" }
foreach ($file in $pngs) {
    $bitmap = $null
    try {
        $bitmap = [System.Drawing.Image]::FromFile($file.FullName)
        if ($file.Name -eq 'sheet.png') {
            if ($bitmap.Width -ne 800 -or $bitmap.Height -ne 226) { throw 'wrong sheet dimensions' }
            for ($i = 0; $i -lt 5; $i++) {
                $pixel = $bitmap.GetPixel([int](($i % 4)*200+100), [int]([Math]::Floor($i/4.0)*113+56))
                $expected = if ($i -eq 2) { 0 } else { 30 + $i * 40 }
                if ($pixel.R -ne $expected) { throw "wrong sheet slot $i" }
            }
        } elseif ($bitmap.Width -ne 1280 -or $bitmap.Height -ne 720) {
            throw "wrong PNG dimensions: $($file.FullName)"
        }
    } finally { if ($null -ne $bitmap) { $bitmap.Dispose() } }
}
# Repeat through the existing-output path and verify all handles are released
# in the same process (including the sheet), before PowerShell exits.
& $Converter -Directory $Directory -FrameCount 5
foreach ($file in Get-ChildItem -LiteralPath $Directory -Recurse -File) {
    if ($file.Extension -notin '.bmp', '.png') { continue }
    $stream = [IO.File]::Open($file.FullName, [IO.FileMode]::Open,
                            [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $stream.Dispose()
}
''', encoding='utf-8')
            result = subprocess.run(
                ['powershell.exe', '-NoProfile', '-File', str(fixture), folder, str(converter)],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('rt_truncated.bmp', result.stdout)
            self.assertIn('Skipping invalid BMP', result.stdout)
            self.assertIn('Missing backbuffer: frame_02', result.stdout)

    def test_synthetic_backbuffers_layout_and_preservation(self):
        converter = Path(__file__).resolve().with_name('port_topng.ps1')
        with tempfile.TemporaryDirectory(prefix='sheet test ') as folder:
            # No game data: five solid-color BMPs, with one missing slot.
            script = r'''
param($Directory, $Converter)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
for ($i = 0; $i -lt 5; $i++) {
    if ($i -eq 2) { continue }
    $frame = Join-Path $Directory ('frame_{0:D2}' -f $i)
    New-Item -ItemType Directory -Path $frame | Out-Null
    $b = New-Object System.Drawing.Bitmap(16, 9)
    $g = [System.Drawing.Graphics]::FromImage($b)
    $g.Clear([System.Drawing.Color]::FromArgb(255, (30 + $i * 40), 0, 0))
    $g.Dispose()
    $b.Save((Join-Path $frame 'backbuffer.bmp'), [System.Drawing.Imaging.ImageFormat]::Bmp)
    $b.Dispose()
}
& $Converter -Directory $Directory -FrameCount 5
$sheetPath = Join-Path $Directory 'sheet.png'
$sheet = [System.Drawing.Image]::FromFile($sheetPath)
try {
    if ($sheet.Width -ne 800 -or $sheet.Height -ne 226) { throw 'wrong dimensions' }
    foreach ($i in 0,1,2,3,4) {
        $expected = if ($i -eq 2) { 0 } else { 30 + $i * 40 }
        $pixel = $sheet.GetPixel([int](($i % 4)*200+100), [int]([Math]::Floor($i/4.0)*113+56))
        if ($pixel.R -ne $expected) { throw "wrong slot $i" }
    }
} finally { $sheet.Dispose() }
$before = [Convert]::ToBase64String([IO.File]::ReadAllBytes($sheetPath))
& $Converter -Directory $Directory -FrameCount 5
if ($before -ne [Convert]::ToBase64String([IO.File]::ReadAllBytes($sheetPath))) { throw 'overwritten sheet' }
if (-not (Test-Path (Join-Path $Directory 'frame_04/backbuffer.bmp'))) { throw 'removed BMP' }
if (-not (Test-Path (Join-Path $Directory 'frame_04/backbuffer.png'))) { throw 'missing PNG' }
'''
            fixture = Path(folder) / 'fixture.ps1'
            fixture.write_text(script, encoding='utf-8')
            subprocess.run(['powershell.exe', '-NoProfile', '-File', str(fixture),
                            folder, str(converter)], check=True, capture_output=True)


class GameProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fake game ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def execute(self, source, seconds=0.5, manifests=()):
        script = self.root / 'fake.py'
        script.write_text(source, encoding='utf-8')
        before = time.monotonic()
        port.run_game([sys.executable, str(script)], os.environ.copy(),
                      self.root, self.root / 'run.log', seconds, manifests)
        return time.monotonic() - before

    def test_timeout_logs_both_streams(self):
        elapsed = self.execute('import time, sys\nprint("stdout", flush=True)\n'
                               'print("stderr", file=sys.stderr, flush=True)\ntime.sleep(60)\n')
        self.assertLess(elapsed, 5)
        self.assertIn('stdout', (self.root / 'run.log').read_text())
        self.assertIn('stderr', (self.root / 'run.log').read_text())

    def test_waits_for_all_complete_markers_then_stops(self):
        manifests = port.capture_manifests(self.root, '42:2:3')
        elapsed = self.execute('from pathlib import Path\nimport time\n'
                               'for i in range(2):\n'
                               ' p=Path(f"frame_{i:02d}/manifest.txt")\n'
                               ' p.parent.mkdir()\n p.write_text("DRAW")\n'
                               'for i in reversed(range(2)):\n'
                               ' time.sleep(.2)\n Path(f"frame_{i:02d}/complete").touch()\n'
                               'time.sleep(60)\n', seconds=5, manifests=manifests)
        self.assertTrue(all(p.exists() for p in manifests))
        self.assertTrue(all(p.with_name('complete').exists() for p in manifests))
        self.assertLess(elapsed, 4)

    def test_manifest_without_complete_obeys_deadline(self):
        manifests = port.capture_manifests(self.root, '42:1:3')
        elapsed = self.execute('from pathlib import Path\nimport time\n'
                               'Path("frame_00").mkdir()\n'
                               'Path("frame_00/manifest.txt").write_text("DRAW")\n'
                               'time.sleep(60)\n', seconds=.7, manifests=manifests)
        self.assertTrue(manifests[0].exists())
        self.assertFalse(manifests[0].with_name('complete').exists())
        self.assertGreaterEqual(elapsed, .7)
        self.assertLess(elapsed, 5)

    def test_exited_launcher_child_is_killed(self):
        child = self.root / 'child.py'
        child.write_text('from pathlib import Path\nimport time\n'
                         'while True:\n Path("heartbeat").write_text(str(time.time_ns()))\n time.sleep(.02)\n')
        self.execute('import subprocess, sys\nsubprocess.Popen([sys.executable, "child.py"])\n', seconds=1)
        heartbeat = self.root / 'heartbeat'
        self.assertTrue(heartbeat.exists())
        first = heartbeat.read_bytes()
        time.sleep(.2)
        self.assertEqual(first, heartbeat.read_bytes())

    def test_failure_is_not_success(self):
        with self.assertRaises(port.subprocess.CalledProcessError):
            self.execute('raise SystemExit(7)\n', seconds=5)


if __name__ == '__main__':
    unittest.main()
