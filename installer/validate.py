"""Read-only validation of the user's source and installer-owned paths."""
import hashlib
from pathlib import Path
import struct


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_sfo(path):
    data = Path(path).read_bytes()
    if len(data) < 20 or data[:4] != b'\0PSF':
        raise ValueError('PARAM.SFO inválido.')
    _, _, keys, values, count = struct.unpack_from('<5I', data)
    if count > 4096 or 20 + count * 16 > len(data):
        raise ValueError('Tabela PARAM.SFO truncada.')
    result = {}
    for i in range(count):
        key, fmt, length, capacity, offset = struct.unpack_from('<HHIII', data, 20 + i * 16)
        start = keys + key
        end = data.find(b'\0', start, values)
        if not 20 + count * 16 <= keys <= start < values <= len(data) or end < start:
            raise ValueError('Chave PARAM.SFO inválida.')
        start_value = values + offset
        if length > capacity or start_value + capacity > len(data):
            raise ValueError('Valor PARAM.SFO truncado.')
        if fmt == 0x204:
            result[data[start:end].decode('utf-8')] = data[start_value:start_value + length].rstrip(b'\0').decode('utf-8')
    return result


def source_root(source):
    source = Path(source).resolve(strict=True)
    game = source if source.name.upper() == 'PS3_GAME' else source / 'PS3_GAME'
    if not (game / 'PARAM.SFO').is_file() or not (game / 'USRDIR').is_dir():
        raise ValueError('Selecione a pasta que contém PS3_GAME, ou a própria PS3_GAME.')
    return game.resolve()


def validate_source(source, profile, elf=None):
    game = source_root(source)
    sfo = read_sfo(game / 'PARAM.SFO')
    if sfo.get('TITLE_ID') != profile['title_id'] or sfo.get('APP_VER') != profile['version']:
        raise ValueError('Edição incompatível. Esperado: ' + profile['title_id'] + ' ' + profile['version'])
    candidate = Path(elf).resolve(strict=True) if elf else game / 'USRDIR' / 'EBOOT.elf'
    if not candidate.is_file():
        raise ValueError('ELF decifrado ausente. Selecione EBOOT.elf ou informe RPCS3 para decifrar uma cópia.')
    if candidate.read_bytes()[:4] != b'\x7fELF' or digest(candidate) != profile['elf_sha256']:
        raise ValueError('SHA-256 do ELF não corresponde à revisão suportada.')
    return {'title_id': sfo['TITLE_ID'], 'version': sfo['APP_VER'],
            'elf_sha256': profile['elf_sha256'], 'game_path': str(game), 'elf': str(candidate)}


def inside(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError('Caminho fora do destino permitido: ' + str(path))
    return path


def reject_overlap(source, dest):
    source, dest = Path(source).resolve(), Path(dest).resolve()
    if source == dest or source.is_relative_to(dest) or dest.is_relative_to(source):
        raise ValueError('Origem e destino devem ser pastas separadas, sem sobreposição.')
