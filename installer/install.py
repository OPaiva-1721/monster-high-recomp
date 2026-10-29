"""Resumable installer and launcher. No game is run during installation."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from installer.state import Journal, atomic_json, load
from installer.validate import digest, inside, read_sfo, reject_overlap, source_root, validate_source
from installer.game_process import single_game, wait_owned

ROOT = Path(__file__).resolve().parents[1]
ORDER = ['sdk', 'ppu', 'spu', 'build', 'ready']


class Cancelled(RuntimeError):
    pass


class Runner:
    def __init__(self, log, cancel=None, emit=None):
        self.log, self.cancel = Path(log), cancel or threading.Event()
        self.emit = emit or (lambda event: None)

    def check(self):
        if self.cancel.is_set():
            raise Cancelled('Instalação cancelada. É possível retomar.')

    def run(self, command, cwd=None, env=None):
        self.check()
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open('ab') as stream:
            stream.write(('\n> ' + subprocess.list2cmdline(list(map(str, command))) + '\n').encode('utf-8'))
            stream.flush()
            process = subprocess.Popen(list(map(str, command)), cwd=cwd, env=env,
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else 0)
            try:
                while process.poll() is None:
                    if self.cancel.wait(.2):
                        self.stop_owned(process, stream)
                        self.check()
            except KeyboardInterrupt:
                self.cancel.set()
                self.stop_owned(process, stream)
                self.check()
            if process.returncode:
                raise RuntimeError(f'Comando falhou ({process.returncode}). Consulte {self.log}')

    @staticmethod
    def stop_owned(process, stream):
        # Only the tree created by this Runner is eligible for cancellation.
        if process.poll() is not None:
            return
        if os.name == 'nt':
            try:
                result = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                        stdout=stream, stderr=subprocess.STDOUT, timeout=10,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode and process.poll() is None:
                    process.terminate()
            except (OSError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    process.terminate()
        else:
            process.terminate()
        process.wait(timeout=10)


def profile(root=ROOT):
    return load(Path(root) / 'installer/game.json')


def locate_vcvars():
    vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    if vswhere.is_file():
        result = subprocess.run([str(vswhere), '-latest', '-products', '*', '-requires',
                                 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'],
                                capture_output=True, text=True, errors='replace', check=False)
        candidate = Path(result.stdout.strip()) / 'VC/Auxiliary/Build/vcvars64.bat'
        if candidate.is_file():
            return str(candidate)
    return ''


def detect_options():
    vcvars = os.environ.get('VCVARS64') or locate_vcvars()
    compiler = os.environ.get('CLANG_CL') or shutil.which('clang-cl') or ''
    if not compiler and vcvars:
        candidate = Path(vcvars).parents[3] / 'VC/Tools/Llvm/x64/bin/clang-cl.exe'
        if candidate.is_file():
            compiler = str(candidate)
    return {'vcvars': vcvars, 'compiler': compiler,
            'ffmpeg': os.environ.get('FFMPEG_ROOT', ''), 'firmware': os.environ.get('PS3_DEV_FLASH', ''),
            'rpcs3': os.environ.get('RPCS3', '') or shutil.which('rpcs3') or '', 'elf': ''}


def python_command():
    if not getattr(sys, 'frozen', False):
        return [sys.executable]
    for command in (['py', '-3.12'], ['python']):
        try:
            result = subprocess.run(command + ['-c', 'import sys;print(sys.executable);assert sys.version_info >= (3,12)'],
                                    capture_output=True, text=True, check=True, timeout=15)
            executable = result.stdout.strip().splitlines()[-1]
            if Path(executable).is_file():
                return [executable]
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
    raise ValueError('Instale Python 3.12+ com acesso pelo PATH ou launcher py.')


def doctor(options):
    problems = []
    if os.name != 'nt':
        problems.append('Esta versão requer Windows x64.')
    for tool in ('git', 'cmake', 'ninja'):
        if not shutil.which(tool):
            problems.append(f'{tool} não encontrado no PATH.')
    try:
        python_command()
    except ValueError as error:
        problems.append(str(error))
    for key, description in [('vcvars', 'vcvars64.bat do Visual Studio Build Tools'), ('compiler', 'clang-cl.exe')]:
        if not Path(options.get(key) or '__missing__').is_file():
            problems.append('Selecione ' + description)
    ff = Path(options.get('ffmpeg') or '__missing__')
    for name in ('avcodec-62.dll', 'avutil-60.dll', 'swresample-6.dll'):
        if not (ff / 'bin' / name).is_file():
            problems.append('FFmpeg 8.1 compartilhado: bin/' + name + ' ausente.')
    if not (ff / 'include/libavcodec/avcodec.h').is_file():
        problems.append('Headers FFmpeg ausentes (include/libavcodec/avcodec.h).')
    if not (Path(options.get('firmware') or '__missing__') / 'sys/external/libspurs_jq.sprx').is_file():
        # The runtime may not need every firmware module, but a real dev_flash is required.
        problems.append('Selecione dev_flash do seu firmware instalado no RPCS3.')
    return problems


def check_slot():
    from tools.port import ensure_game_slot
    ensure_game_slot()


def revision(root):
    if (Path(root) / '.git').exists():
        return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    value = load(Path(root) / 'installer/build.json', {}).get('commit')
    if not value or len(value) != 40:
        raise ValueError('Revisão do pacote ausente.')
    return value


def isolated_decryptor(rpc, dest):
    """Read only the selected executable/dependencies; never reuse its settings."""
    rpc = Path(rpc).resolve()
    runtime = inside(dest, Path(dest) / '.installer/tools' / ('rpcs3-' + digest(rpc)[:16]))
    runtime.mkdir(parents=True, exist_ok=True)
    dependencies = [rpc, *rpc.parent.glob('*.dll')]
    for folder in ('qt', 'plugins', 'platforms', 'imageformats', 'styles', 'tls'):
        source = rpc.parent / folder
        if source.is_dir():
            dependencies.extend(p for p in source.rglob('*') if p.is_file() and p.suffix.lower() in ('.dll', '.json'))
    for source in dependencies:
        target = inside(dest, runtime / source.relative_to(rpc.parent))
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or digest(target) != digest(source):
            shutil.copy2(source, target)
    inside(dest, runtime / 'portable').mkdir(exist_ok=True)
    return runtime / rpc.name


def prepare_source(source, dest, game, options, runner):
    game_dir = source_root(source)
    sfo = read_sfo(game_dir / 'PARAM.SFO')
    if (sfo.get('TITLE_ID'), sfo.get('APP_VER')) != (game['title_id'], game['version']):
        raise ValueError('Edição ou versão incompatível.')
    elf = options.get('elf') or game_dir / 'USRDIR/EBOOT.elf'
    if not Path(elf).is_file():
        check_slot()
        rpc = Path(options.get('rpcs3') or '__missing__')
        if not rpc.is_file():
            raise ValueError('Informe RPCS3 para decifrar cópia do EBOOT.BIN, ou selecione seu EBOOT.elf.')
        target = dest / '.installer/decrypt' / game['elf_sha256'] / 'EBOOT.BIN'
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.with_suffix('.elf').exists():
            shutil.copyfile(game_dir / 'USRDIR/EBOOT.BIN', target)
            private_rpc = isolated_decryptor(rpc, dest)
            runner.run([private_rpc, '--decrypt', target], cwd=target.parent)
        elf = target.with_suffix('.elf')
    return validate_source(source, game, elf)


def configure_checkout(root, app, info, options, python):
    game = profile(root)
    ini = configparser.ConfigParser(interpolation=None)
    ini.optionxform = str
    ini.read(Path(root) / 'ports' / game['game'] / 'port.ini', encoding='utf-8')
    ini['port'].update({'EBOOT_ELF': info['elf'], 'PS3RECOMP_DIR': str(app / 'external/ps3recomp'),
                        'RECOMP_DIR': str(app / 'build/lift/recompiled'), 'LIFT_DIR': str(app / 'build/lift'),
                        'SPU_DIR': str(app / 'build/lift/spu'), 'JOBS_DIR': str(app / 'build/lift/spujobs'),
                        'BUILD_DIR': str(app / 'build/game'), 'EXE': str(app / 'build/game' / game['executable']),
                        'PYTHON': python, 'VCVARS64': options['vcvars'],
                        'RUNTIME_DLL_DIR': str(Path(options['ffmpeg']) / 'bin')})
    ini['cmake'].update({'CMAKE_C_COMPILER': options['compiler'], 'CMAKE_CXX_COMPILER': options['compiler'],
                         'PS3RECOMP_FFMPEG_INCLUDE_DIR': str(Path(options['ffmpeg']) / 'include'),
                         'PORT_LAUNCHER': 'OFF', 'CMAKE_C_FLAGS': ''})
    if game['game'] == 'naruto-storm':
        ini['cmake']['CMAKE_RUNTIME_OUTPUT_DIRECTORY'] = str(app / 'build/game')
    # Local generated configuration is never part of a release or the user dump.
    path = app / 'ports' / game['game'] / 'port.local.ini'
    with path.open('w', encoding='utf-8') as stream:
        ini.write(stream)


def copy_sources(root, app):
    # Source-only allowlist, not copytree(checkout): ignored games/builds cannot leak.
    app.mkdir(parents=True, exist_ok=True)
    for folder in ('installer', 'tools', 'ports', 'patches'):
        for path in (Path(root) / folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc' and path.name != 'port.local.ini':
                target = app / path.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)


def extract_jobs(elf, specs, output):
    body = Path(elf).read_bytes()
    paths = []
    for job in specs:
        raw = body[job['offset']:job['offset'] + job['size']]
        if len(raw) != job['size'] or hashlib.sha256(raw).hexdigest() != job['sha256']:
            raise ValueError('Job extraído diverge do ELF suportado.')
        output.mkdir(parents=True, exist_ok=True)
        target = output / job['name']
        target.write_bytes(raw)
        paths.append(target)
    return paths


def generation_fingerprint(root, game):
    ini = configparser.ConfigParser(interpolation=None)
    ini.read(Path(root) / 'ports' / game['game'] / 'port.ini', encoding='utf-8')
    value = {'format': 1, 'elf': game['elf_sha256'], 'jobs': game['jobs'],
             'sdk': digest(Path(root) / game['sdk_lock']),
             'tools': {name: digest(Path(root) / 'tools' / name) for name in ('port.py','lift_spurs_jobs.py')},
             'args': {name: ini.get('port', name, fallback='') for name in ('LIFT_ARGS','SYMBOL_PREFIX','TITLE')}}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def run_install(source, dest, emit=print, *, options=None, root=ROOT, cancel=None):
    root, dest = Path(root).resolve(), Path(dest).resolve()
    game = profile(root)
    options = dict(options or detect_options())
    reject_overlap(source_root(source), dest)
    # Only verified updater snapshots may live inside an existing installation.
    if not root.is_relative_to(dest / '.installer/downloads'):
        reject_overlap(root, dest)
    for value in [str(root), str(source_root(source)), str(dest), *[str(v) for v in options.values()]]:
        if any(char in value for char in ('%', '!', '\r', '\n', '"', '&', '|', '<', '>', '^')):
            raise ValueError('Caminho/opção contém caractere não suportado por cmd.exe.')
    problems = doctor(options)
    if problems:
        raise ValueError('\n'.join(problems))
    check_slot()
    if dest.exists() and any(dest.iterdir()) and not (dest / '.installer/owner.json').is_file():
        raise ValueError('Destino não vazio e não reconhecido; escolha outra pasta.')
    for relative in ('.installer', 'app', 'userdata', 'userdata/config', 'userdata/hdd0'):
        candidate = dest / relative
        if candidate.exists() and candidate.resolve() != candidate.absolute():
            raise ValueError('Link/junction não permitido nos diretórios gerenciados.')
    owner = load(dest / '.installer/owner.json', {'repo': game['repo'], 'schema': 1})
    if owner != {'repo': game['repo'], 'schema': 1}:
        raise ValueError('Destino pertence a outro port ou formato.')
    free_root = dest
    while not free_root.exists():
        free_root = free_root.parent
    if shutil.disk_usage(free_root).free < game['minimum_free_bytes']:
        raise ValueError('Espaço insuficiente: reserve pelo menos ' + str(game['minimum_free_bytes'] // 2**30) + ' GiB.')
    dest.mkdir(parents=True, exist_ok=True)
    atomic_json(dest / '.installer/owner.json', owner)
    lock_dir = dest / '.installer/install.lock'
    try:
        lock_dir.mkdir()
    except FileExistsError:
        raise ValueError('Instalação já bloqueada. Se o instalador foi encerrado à força, feche-o e remova somente .installer/install.lock.')
    try:
        return _install_locked(source, dest, emit, options, root, game, cancel)
    finally:
        lock_dir.rmdir()


def _install_locked(source, dest, emit, options, root, game, cancel):
    runner = Runner(dest / '.installer/install.log', cancel, emit)
    emit({'stage': 'validate', 'status': 'running', 'message': 'Validando sua cópia'})
    info = prepare_source(source, dest, game, options, runner)
    rev = revision(root)
    identity = {'commit': rev, 'source': info, 'options': options,
                'profile': digest(root / 'installer/game.json'), 'sdk': digest(root / game['sdk_lock'])}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    app = inside(dest, dest / 'app' / (rev[:12] + '-' + key))
    copy_sources(root, app)
    atomic_json(app / 'installer/build.json', {'commit': rev})
    journal = Journal(dest / '.installer' / (key + '.json'), app, identity)
    generation_key = generation_fingerprint(root, game)
    old_active = load(dest / '.installer/active.json', {})
    py = dest / '.installer/python' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not py.exists():
        runner.run(python_command() + ['-m', 'venv', '--without-pip', py.parents[1]])
    configure_checkout(root, app, info, options, str(py))
    sdk = app / 'external/ps3recomp'
    sdk_lock = load(root / game['sdk_lock'])
    if sdk_lock['upstream'] != 'https://github.com/sp00nznet/ps3recomp':
        raise ValueError('Origem SDK não permitida.')
    patch = inside(root, root / sdk_lock['patch'])
    if digest(patch) != sdk_lock['sha256']:
        raise ValueError('SHA-256 do patch SDK divergente.')

    def step(name, action):
        runner.check()
        if journal.complete(name):
            emit({'stage': name, 'status': 'cached', 'message': 'Saídas conferidas; etapa reutilizada'})
            return
        journal.invalidate_from(name, ORDER)
        emit({'stage': name, 'status': 'running', 'message': 'Executando ' + name})
        paths = action()
        runner.check()
        journal.finish(name, paths, allow_empty=name == 'sdk')
        emit({'stage': name, 'status': 'complete', 'message': 'Etapa concluída: ' + name})

    def sdk_action():
        if sdk.exists():
            # An interrupted clone/patch is kept for inspection; no silent reset/delete.
            tree = subprocess.run(['git', '-C', str(sdk), 'write-tree'], capture_output=True, text=True)
            diff = subprocess.run(['git', '-C', str(sdk), 'diff', '--quiet'], capture_output=True)
            if tree.returncode == 0 and diff.returncode == 0 and tree.stdout.strip() == sdk_lock['expected_tree']:
                return write_sdk_marker()
            raise ValueError('SDK parcial encontrado; preserve o log e escolha um destino novo para refazer esta etapa.')
        staging = app / 'external' / ('.sdk-staging-' + uuid.uuid4().hex[:8])
        runner.run(['git', 'clone', '--no-checkout', sdk_lock['upstream'], staging])
        runner.run(['git', '-C', staging, 'config', 'core.autocrlf', 'false'])
        runner.run(['git', '-C', staging, 'checkout', '--detach', sdk_lock['base']])
        runner.run(['git', '-C', staging, 'apply', '--check', patch])
        runner.run(['git', '-C', staging, 'apply', patch])
        runner.run(['git', '-C', staging, 'add', '-A'])
        tree = subprocess.check_output(['git', '-C', str(staging), 'write-tree'], text=True).strip()
        if tree != sdk_lock['expected_tree']:
            raise ValueError('Árvore SDK não corresponde ao lock.')
        staging.rename(sdk)
        return write_sdk_marker()

    def write_sdk_marker():
        atomic_json(app / '.sdk-ready.json', sdk_lock)
        names = subprocess.check_output(['git', '-C', str(sdk), 'ls-files', '-z']).split(b'\0')
        return [app / '.sdk-ready.json', *[sdk / p.decode('utf-8') for p in names if p]]

    def pipeline(stage):
        environment = os.environ.copy()
        environment['CMAKE_BUILD_PARALLEL_LEVEL'] = '2'
        # A maintainer's debug environment must not alter a reproducible install.
        for key in list(environment):
            if key in ('TITLE','SYMBOL_PREFIX','RECOMP_DIR','LIFT_DIR','SPU_DIR','JOBS_DIR','BUILD_DIR','EXE','EBOOT_ELF','EBOOT_BIN','PS3RECOMP_DIR','LIFT_ARGS','PYTHON','HDD0_DIR','VCVARS64','RUNTIME_DLL_DIR'):
                environment.pop(key)
        runner.run([py, app / 'tools/port.py', game['game'], stage], cwd=app, env=environment)

    def reuse_generation(stage):
        if old_active.get('generation_key') != generation_key:
            return None
        old_app = inside(dest, old_active['app'])
        if old_app == app:
            return None
        manifest_path = old_app / '.generation.json'
        if not manifest_path.is_file() or digest(manifest_path) != old_active.get('generation_manifest_sha256'):
            return None
        records = load(manifest_path).get(stage, {})
        if not records:
            return None
        candidates = []
        for relative, sha in records.items():
            path = inside(old_app, old_app / relative)
            if not path.is_relative_to(old_app / 'build/lift') or not path.is_file() or digest(path) != sha:
                return None
            candidates.append((path, inside(app, app / relative)))
        paths = []
        for source_file, target in candidates:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_file, target)
            paths.append(target)
        emit({'stage': stage, 'status': 'reused', 'message': 'Geração anterior conferida e reutilizada'})
        return paths

    def ppu_action():
        reused = reuse_generation('ppu')
        if reused:
            return reused
        pipeline('lift')
        files = list((app / 'build/lift/recompiled').glob('*'))
        if not any(p.name == 'ppu_recomp.h' for p in files) or not any(p.suffix in ('.c', '.cpp') for p in files):
            raise ValueError('Geração PPU incompleta.')
        return [p for p in files if p.is_file()]

    def spu_action():
        reused = reuse_generation('spu')
        if reused:
            return reused
        extract_jobs(info['elf'], game['jobs'], app / 'build/lift/spujobs')
        pipeline('lift-spu')
        files = [p for p in (app / 'build/lift/spu').rglob('*') if p.is_file()]
        if not any(p.name == 'spu_workloads.c' for p in files):
            raise ValueError('Registro SPU ausente.')
        if game['jobs'] and not any(p.name == 'spurs_jobs_register.c' for p in files):
            raise ValueError('Registro de jobs ausente.')
        return files

    def build_action():
        pipeline('build')
        folder = app / 'build/game'
        executable = folder / game['executable']
        if not executable.is_file():
            raise ValueError('Executável esperado não foi gerado: ' + game['executable'])
        return [executable, *[folder / name for name in game['runtime_dlls']]]

    def ready_action():
        config_dir = dest / 'userdata/config'
        config_dir.mkdir(parents=True, exist_ok=True)
        controls = config_dir / game['controls']
        if not controls.exists():
            shutil.copyfile(root / 'ports' / game['game'] / game['controls'], controls)
        (dest / 'userdata/hdd0').mkdir(parents=True, exist_ok=True)
        # Relative guest IO can still create gamedata; its CWD is stable userdata.
        atomic_json(app / '.generation.json', {stage: journal.data['steps'][stage]['outputs'] for stage in ('ppu','spu')})
        config = {'source': info, 'options': options, 'app': str(app), 'repo': game['repo'], 'commit': rev,
                  'generation_key': generation_key, 'generation_manifest_sha256': digest(app / '.generation.json'),
                  'executable_sha256': digest(app / 'build/game' / game['executable'])}
        atomic_json(app / '.ready.json', config)
        return [app / '.ready.json', app / '.generation.json']

    for name, action in [('sdk', sdk_action), ('ppu', ppu_action), ('spu', spu_action), ('build', build_action), ('ready', ready_action)]:
        step(name, action)
    # Active installation changes only after all new outputs have been verified.
    previous = load(dest / '.installer/active.json')
    if previous and previous.get('app') != str(app):
        atomic_json(dest / '.installer/previous.json', previous)
    create_shortcuts(dest, app, py)
    atomic_json(dest / '.installer/active.json', load(app / '.ready.json'))
    emit({'stage': 'complete', 'status': 'complete', 'message': 'Instalação concluída. Você pode jogar.'})
    return 0


def create_shortcuts(dest, app, py):
    # Fixed script strings; paths are rejected above if cmd expansion is unsafe.
    play = '@echo off\r\nchcp 65001 >nul\r\n"' + str(py) + '" "' + str(app / 'installer/install.py') + '" launch --dest "' + str(dest) + '"\r\n'
    update = play.replace(' launch --dest ', ' update --dest ')
    (dest / 'Jogar.cmd').write_text(play, encoding='utf-8')
    (dest / 'Atualizar.cmd').write_text(update, encoding='utf-8')


def launch(dest):
    with single_game():
        return _launch(dest)


def _launch(dest):
    dest = Path(dest).resolve()
    config = load(dest / '.installer/active.json')
    if not config:
        raise ValueError('Instalação não concluída.')
    app = inside(dest, config['app'])
    game = profile(app)
    executable = app / 'build/game' / game['executable']
    if digest(executable) != config['executable_sha256']:
        raise ValueError('Executável modificado/incompleto; repare a instalação.')
    validate_source(config['source']['game_path'], game, config['source']['elf'])
    check_slot()
    ini = configparser.ConfigParser(interpolation=None)
    ini.optionxform = str
    ini.read(app / 'ports' / game['game'] / 'port.ini', encoding='utf-8')
    env = os.environ.copy()
    for key in list(env):
        if key == 'PAD_NO_KEYBOARD' or key.startswith(('PAD_SCRIPT', 'PAD_FILE', 'PAD_STICK', 'PAD_SWEEP', 'RSX_CAP', 'PS3_DEBUG')):
            env.pop(key)
    env.update(dict(ini['env']))
    env.update({'PS3_VFS_ROOT': str(Path(config['source']['game_path']).parent),
                'PS3_DEV_FLASH': config['options']['firmware'], 'PS3_HDD0_ROOT': str(dest / 'userdata/hdd0'),
                'PAD_CONFIG': str(dest / 'userdata/config' / game['controls']), 'PERF': '0'})
    with (dest / '.installer/game.log').open('ab') as log:
        process = subprocess.Popen([str(executable), config['source']['elf']], cwd=dest / 'userdata',
                                   env=env, stdout=log, stderr=subprocess.STDOUT)
        atomic_json(dest / '.installer/game-session.json', {'pid': process.pid, 'executable': str(executable)})
        return wait_owned(process, log)


def update_install(dest, emit=print, cancel=None):
    from installer.update import download_snapshot, latest_commit
    dest = Path(dest).resolve()
    old = load(dest / '.installer/active.json')
    if not old or old['repo'] != profile()['repo']:
        raise ValueError('Instalação de outro repositório ou incompleta.')
    check_slot()
    commit = latest_commit(old['repo'])
    if commit == old['commit']:
        emit({'stage': 'update', 'status': 'complete', 'message': 'Já está atualizado.'})
        return 0
    staging = dest / '.installer/downloads' / (commit + '-' + uuid.uuid4().hex[:8])
    download_snapshot(old['repo'], commit, staging)
    # New release code executes only after a verified pinned snapshot download.
    atomic_json(staging / 'installer/build.json', {'commit': commit})
    if profile(staging)['repo'] != old['repo']:
        raise ValueError('Perfil da atualização não corresponde à instalação.')
    py = dest / '.installer/python' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    command = [py, staging / 'installer/install.py', 'install', '--source', old['source']['game_path'], '--dest', dest]
    for key, value in old['options'].items():
        if key in ('elf','firmware','ffmpeg','compiler','vcvars','rpcs3') and value:
            command.extend(['--' + key, str(value)])
    emit({'stage': 'update', 'status': 'running', 'message': 'Preparando atualização; acompanhe .installer/install.log'})
    Runner(dest / '.installer/install.log', cancel, emit).run(command, cwd=staging)
    if load(dest / '.installer/active.json', {}).get('commit') != commit:
        raise ValueError('A atualização terminou sem ativar a revisão esperada.')
    emit({'stage': 'complete', 'status': 'complete', 'message': 'Atualização concluída.'})
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['doctor', 'install', 'launch', 'update'])
    parser.add_argument('--game')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--dest', type=Path)
    for key in ('elf', 'firmware', 'ffmpeg', 'compiler', 'vcvars', 'rpcs3'):
        parser.add_argument('--' + key)
    args = parser.parse_args()
    if args.game and args.game != profile()['game']:
        parser.error('Este instalador atende apenas ' + profile()['game'])
    options = detect_options()
    options.update({key: getattr(args, key) for key in options if getattr(args, key) is not None})
    if args.command == 'doctor':
        problems = doctor(options)
        print('\n'.join(problems) if problems else 'Requisitos encontrados.')
        return bool(problems)
    if not args.dest:
        parser.error('--dest obrigatório')
    if args.command == 'launch':
        return launch(args.dest)
    if args.command == 'update':
        return update_install(args.dest)
    if not args.source:
        parser.error('--source obrigatório')
    return run_install(args.source, args.dest, options=options)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
