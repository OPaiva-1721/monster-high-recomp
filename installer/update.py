"""Pinned GitHub snapshots, verified against the commit's Git blob hashes."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import urllib.request
import zipfile

REPOSITORIES = {'OPaiva-1721/monster-high-recomp', 'OPaiva-1721/naruto-storm-recomp'}


def request(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'ps3-port-installer/0.1'})
    with urllib.request.urlopen(req, timeout=60) as response:
        data = response.read(128 * 1024 * 1024 + 1)
    if len(data) > 128 * 1024 * 1024:
        raise ValueError('Download excedeu o limite de 128 MiB.')
    return data


def latest_commit(repo):
    if repo not in REPOSITORIES:
        raise ValueError('Repositório de atualização não permitido.')
    sha = json.loads(request(f'https://api.github.com/repos/{repo}/commits/main'))['sha']
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('Commit inválido.')
    return sha


def safe_extract(data, dest, expected):
    dest = Path(dest).resolve()
    if dest.exists():
        raise ValueError('Staging de download já existe.')
    entries = {}
    prefix = None
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        total = 0
        for info in archive.infolist():
            raw = info.filename
            path = PurePosixPath(raw)
            if '\\' in raw or ':' in raw or path.is_absolute() or '..' in path.parts:
                raise ValueError('Caminho inseguro no ZIP.')
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Link não permitido no ZIP.')
            for part in path.parts:
                if part.endswith((' ', '.')) or part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
                    raise ValueError('Nome incompatível com Windows no ZIP.')
            if prefix is None:prefix = path.parts[0]
            if path.parts[0] != prefix:raise ValueError('Múltiplas raízes no ZIP.')
            if len(path.parts) < 2 or info.is_dir():
                continue
            name = PurePosixPath(*path.parts[1:]).as_posix()
            if name.casefold() in entries or name not in expected:
                raise ValueError('Entrada duplicada ou não declarada: ' + name)
            total += info.file_size
            if info.file_size > 32 * 1024 * 1024 or total > 128 * 1024 * 1024:
                raise ValueError('ZIP excedeu limites de tamanho.')
            body = archive.read(info)
            oid = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
            if oid != expected[name]:
                raise ValueError('Hash Git divergente: ' + name)
            entries[name.casefold()] = (name, body)
    if {n for n, _ in entries.values()} != set(expected):
        raise ValueError('Snapshot incompleto.')
    # Nothing is written until the entire archive has passed validation.
    dest.mkdir(parents=True)
    for name, body in entries.values():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)


def download_snapshot(repo, commit, dest):
    if repo not in REPOSITORIES or not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Origem/revisão de atualização inválida.')
    tree = json.loads(request(f'https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1'))
    if tree.get('truncated'):
        raise ValueError('Árvore Git incompleta.')
    expected = {}
    for item in tree['tree']:
        if item['type'] == 'tree':
            continue
        if item['type'] != 'blob' or item['mode'] not in ('100644', '100755'):
            raise ValueError('Tipo de entrada Git não suportado.')
        expected[item['path']] = item['sha']
    safe_extract(request(f'https://codeload.github.com/{repo}/zip/{commit}'), dest, expected)
