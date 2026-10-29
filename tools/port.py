"""Implementation of port.sh. Only the standard library is required."""
import argparse
import configparser
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import math
import signal
import time
import csv
import json


def ensure_game_slot():
    """Read-only Windows guard. Never terminates another process."""
    if os.name == 'nt':
        rows=csv.reader(subprocess.check_output(['tasklist','/FO','CSV','/NH'],text=True).splitlines())
        names={'narutostorm.exe','mygamerecomp.exe','monsterhigh.exe','rpcs3.exe'}
        if any(row and row[0].casefold() in names for row in rows):
            raise ValueError('Another game is running. Close it before launching this port.')


def capture_manifests(directory, frames):
    start, count, step = map(int, frames.split(':'))
    if start < 0 or count < 1 or step < 1:
        raise ValueError('CAP_FRAMES requires start>=0, count>=1, step>=1')
    return [directory / f'frame_{i:02d}' / 'manifest.txt' for i in range(count)]


def report_draws(manifests):
    for manifest in manifests:
        if manifest.is_file():
            count = sum(bool(re.match(r'^op\d+\s+DRAW\b', line))
                        for line in manifest.read_text(encoding='utf-8', errors='replace').splitlines())
            print(f'{manifest.parent.name}: DRAW={count}')
        else:
            print(f'{manifest.parent.name}: manifest missing')


def run_game(cmd, env, cwd, log, seconds, manifests=()):
    """Own the entire process tree, including a launcher that exits early."""
    if seconds is None:
        ensure_game_slot()
        with log.open('wb') as output:
            proc=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=output,stderr=subprocess.STDOUT)
            session=cwd/'interactive-session.json'
            session.write_text(json.dumps({'pid':proc.pid,'command':cmd,'log':str(log),'interactive':True}),encoding='utf-8')
            code=proc.wait()
        if code:raise subprocess.CalledProcessError(code,cmd)
        return
    job = None
    kernel = None
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        for name, types in [('AssignProcessToJobObject', [wintypes.HANDLE, wintypes.HANDLE]),
                            ('TerminateJobObject', [wintypes.HANDLE, wintypes.UINT]),
                            ('CloseHandle', [wintypes.HANDLE])]:
            getattr(kernel, name).argtypes = types
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
    proc = None
    try:
        with log.open('wb') as output:
            proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=output,
                                    stderr=subprocess.STDOUT,
                                    creationflags=4 if job else 0,
                                    start_new_session=not bool(job))
            if job:
                if not kernel.AssignProcessToJobObject(job, int(proc._handle)):
                    raise ctypes.WinError(ctypes.get_last_error())
                ntdll = ctypes.WinDLL('ntdll')
                ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
                if ntdll.NtResumeProcess(int(proc._handle)) != 0:
                    raise OSError('could not resume game process')
            deadline = time.monotonic() + seconds
            while True:
                # The manifest precedes BMP writes; only complete closes a frame.
                if manifests and all(p.with_name('complete').is_file() for p in manifests):
                    break
                if time.monotonic() >= deadline:
                    break
                code = proc.poll()
                if code not in (None, 0):
                    raise subprocess.CalledProcessError(code, cmd)
                # A successful launcher may leave a live child: retain ownership
                # until capture completion or the deadline.
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    finally:
        if job:
            kernel.TerminateJobObject(job, 0)
            kernel.CloseHandle(job)
        elif proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if proc is not None:
            if proc.poll() is None:
                proc.kill()
            proc.wait()

ROOT = Path(__file__).resolve().parents[1]
STAGES = ('decrypt', 'lift', 'lift-spu', 'build', 'run', 'cap')


def main(argv=None):
    ap = argparse.ArgumentParser(description='Execute one independent port stage (never runs prerequisites).')
    ap.add_argument('game')
    ap.add_argument('stage', choices=STAGES)
    ap.add_argument('--dry-run', action='store_true', help='print commands without writing or executing anything')
    ap.add_argument('--seconds', type=float, help='run/cap time limit (default: RUN_SECONDS or 130)')
    ap.add_argument('--interactive', action='store_true', help='run without scripted input, capture diagnostics or time limit')
    args = ap.parse_args(argv)
    if args.interactive and (args.stage!='run' or args.seconds is not None):
        ap.error('--interactive requires run and cannot be combined with --seconds')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', args.game):
        ap.error('invalid game name')
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.optionxform = str
    ini = ROOT / 'ports' / args.game / 'port.ini'
    if not cfg.read(ini, encoding='utf-8'):
        ap.error(f'missing {ini}')
    # Personal paths stay outside Git; environment variables remain highest priority.
    cfg.read(ini.with_name('port.local.ini'), encoding='utf-8')

    def value(key, default=None):
        result = os.environ.get(key, cfg.get('port', key, fallback=default))
        if result is None:
            raise ValueError(f'missing [port] {key}')
        return result

    def path(key, default=None):
        p = Path(value(key, default))
        return (ROOT / p).resolve()

    sdk = path('PS3RECOMP_DIR', 'external/ps3recomp')
    lift = path('LIFT_DIR', f'build/{args.game}-lift')
    recomp = path('RECOMP_DIR', str(lift / 'recompiled'))
    spu = path('SPU_DIR', str(lift / 'spu'))
    build = path('BUILD_DIR', f'build/{args.game}-win')
    elf = path('EBOOT_ELF')
    python = value('PYTHON', sys.executable)

    def owned(p):
        # Generated output must stay in this worktree's build/, including symlinks.
        p.resolve().relative_to((ROOT / 'build').resolve())

    def mkdir(p):
        owned(p)
        if not args.dry_run:
            p.mkdir(parents=True, exist_ok=True)

    def run(cmd, env=None, cwd=ROOT):
        cmd = [str(x) for x in cmd]
        print(subprocess.list2cmdline(cmd), flush=True)
        if not args.dry_run:
            subprocess.run(cmd, cwd=cwd, env=env, check=True)

    def tool(name, *params):
        run([python, sdk / 'tools' / name, *params])

    if args.stage == 'decrypt':
        source = path('EBOOT_BIN')
        # RPCS3 writes next to its input: copy into our build tree first.
        out = path('DECRYPT_DIR', f'build/{args.game}-decrypt')
        mkdir(out)
        target = out / 'EBOOT.BIN'
        if not args.dry_run:
            if target.exists() or target.with_suffix('.elf').exists():
                raise ValueError(f'decrypt output already exists: {out}; choose another DECRYPT_DIR')
            shutil.copy2(source, target)
        run([value('RPCS3', 'C:/dev/rpcs3/rpcs3.exe'), '--decrypt', target])
        print(f'ELF output: {target.with_suffix(".elf")}; set EBOOT_ELF to this path for subsequent stages')
    elif args.stage == 'lift':
        owned(lift)
        mkdir(recomp)
        tool('ppu_loader.py', elf, '-o', lift / 'out')
        stem = elf.stem
        tool('ppu_lifter.py', elf, '--functions', lift / 'out' / f'{stem}.functions.json',
             '--hle-stubs', lift / 'out' / f'{stem}.imports.json', '--output', recomp,
             *value('LIFT_ARGS', '').split())
        tool('gen_hle_nids.py', '--all', '--out', recomp / 'ppu_hle_nids.cpp')
    elif args.stage == 'lift-spu':
        mkdir(spu)
        images = lift / 'images'
        mkdir(images)
        tool('extract_spu_images.py', elf, '--output', images)
        prefix = value('SYMBOL_PREFIX', args.game.replace('-', '_'))
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', prefix):
            raise ValueError('invalid SYMBOL_PREFIX')
        tool('build_spu_workloads.py', '--images', images, '--lifted', spu,
             '--out', spu / 'spu_workloads.c', '--register-fn', prefix + '_spu_register_all',
             '--constructor', '--title', value('TITLE', args.game))
        jobs = path('JOBS_DIR', str(lift / 'spujobs'))
        if list(jobs.glob('spujob_*.bin')):
            run([python, ROOT / 'tools/lift_spurs_jobs.py', '--jobs', jobs, '--out', spu, '--prefix', prefix])
        else:
            print(f'No dumped SPURS jobs in {jobs}; run separately with SPU_DUMP_MISS to collect them.')
    elif args.stage == 'build':
        mkdir(build)
        cmd = ['cmake', '-S', ROOT / 'ports' / args.game, '-B', build, '-G', 'Ninja',
               '-DCMAKE_BUILD_TYPE=RelWithDebInfo', f'-DPS3RECOMP_DIR={sdk.as_posix()}',
               f'-DRECOMP_DIR={recomp.as_posix()}', f'-DSPU_DIR={spu.as_posix()}',
               '-DPORT_BOOT_HARNESS=ON', '-DPORT_ENABLE_SPU=ON']
        if cfg.has_section('cmake'):
            cmd += [f'-D{k}={v.replace("{ROOT}", ROOT.as_posix())}' for k, v in cfg.items('cmake')]
        commands = [cmd, ['cmake', '--build', build, '--', '-k', '0']]
        if os.name == 'nt':
            vcvars = value('VCVARS64', 'C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Auxiliary/Build/vcvars64.bat')
            # Python starts cmd directly, avoiding MSYS argument conversion.
            script = build / 'port-build.cmd'
            lines = ['@echo off', f'call "{vcvars}" >nul || exit /b 1']
            lines += [subprocess.list2cmdline([str(x) for x in c]) + ' || exit /b 1' for c in commands]
            if args.dry_run:
                print('\n'.join(lines))
            else:
                script.write_text('\n'.join(lines) + '\n', encoding='utf-8')
                run(['cmd.exe', '/d', '/c', str(script)])
        else:
            for command in commands:
                run(command)
        dll_dir = value('RUNTIME_DLL_DIR', '')
        if dll_dir:
            for name in value('RUNTIME_DLLS', '').split():
                source = ROOT / dll_dir / name
                print(f'copy {source} -> {build}')
                if not args.dry_run:
                    shutil.copy2(source, build / name)
    else:
        seconds = args.seconds if args.seconds is not None else float(value('RUN_SECONDS', '130'))
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('seconds must be finite and positive')
        if args.interactive:seconds=None
        cap = path('CAP_DIR', f'build/{args.game}-cap')
        mkdir(cap)
        manifests = []
        hdd = path('HDD0_DIR', f'build/{args.game}-hdd0')
        mkdir(hdd)
        env = os.environ.copy()
        if cfg.has_section('env'):
            for key, val in cfg.items('env'):
                env.setdefault(key, val)
        for key in ('PS3_VFS_ROOT', 'PS3_DEV_FLASH', 'PAD_CONFIG'):
            if env.get(key):
                env[key] = str((ROOT / env[key].replace('{ROOT}', ROOT.as_posix())).resolve())
        if args.interactive:
            for key in list(env):
                if key.startswith(('PAD_SCRIPT','PAD_FILE','PAD_STICK','PAD_SWEEP','PAD_AUTOPRESS','PAD_NO_KEYBOARD',
                                   'RSX_CAP','RSX_GPU_TIMING','RSX_PRESENT_SAMPLES','RSX_WAIT_STATS','RSX_FP_TEX_DIAG',
                                   'PS3_DEBUG','PS3_HLE_ARGS','CELLMARK_','GAME_CAP','GCM_TRACE','GCM_LOOP_STATS',
                                   'GCM_REFLOG','GCM_REFPUB','PPU_SPINBT','SPU_DUMP_MISS')) or key in ('PERF','FRAMEHIST','VTXSTAT','DRAWSTAT','FP_DUMP','SPURS_EF_STATS'):
                    env.pop(key)
            env['PERF']='0'
        env['PS3_HDD0_ROOT'] = str(hdd)
        if args.stage == 'cap':
            cap = path('CAP_DIR', f'build/{args.game}-cap')
            mkdir(cap)
            env['RSX_CAP'] = value('CAP_FRAMES', '1500:1:1')
            env['RSX_CAP_DIR'] = str(cap)
            manifests = capture_manifests(cap, env['RSX_CAP'])
            if any(p.exists() for p in manifests):
                raise ValueError('capture manifests already exist; choose another CAP_DIR')
        for key in sorted(set(cfg.options('env') if cfg.has_section('env') else []) |
                          {'PS3_HDD0_ROOT'} | ({'RSX_CAP', 'RSX_CAP_DIR'} if args.stage == 'cap' else set())):
            if key in env:
                print(f'{key}={env[key]}')
        cmd = [str(path('EXE', str(build / 'MyGameRecomp.exe'))), str(elf)]
        print(subprocess.list2cmdline(cmd), flush=True)
        if not args.dry_run:
            run_game(cmd, env, build, cap / 'run.log', seconds, manifests)
        if args.stage == 'cap':
            if not args.dry_run:
                report_draws(manifests)
            if os.name == 'nt':
                command = ['powershell.exe', '-NoProfile', '-File', ROOT / 'tools/port_topng.ps1', '-Directory', cap]
                if len(manifests) > 1:
                    command += ['-FrameCount', str(len(manifests))]
                run(command)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, configparser.Error, subprocess.CalledProcessError) as exc:
        print(f'port: {exc}', file=sys.stderr)
        sys.exit(1)
