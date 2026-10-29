"""Atomic journals; output fingerprints determine whether a step can resume."""
import json
import os
from pathlib import Path
from installer.validate import digest, inside


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def load(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


class Journal:
    def __init__(self, path, root, identity):
        self.path, self.root, self.identity = Path(path), Path(root), identity
        self.data = load(path, {'schema': 1, 'identity': identity, 'steps': {}})
        if self.data.get('schema') != 1 or self.data.get('identity') != identity:
            self.data = {'schema': 1, 'identity': identity, 'steps': {}}

    def complete(self, step):
        record = self.data['steps'].get(step)
        if not record:
            return False
        try:
            return all((p := inside(self.root, self.root / name)).is_file() and digest(p) == sha
                       for name, sha in record['outputs'].items()) and bool(record['outputs'])
        except (OSError, ValueError):
            return False

    def invalidate_from(self, step, order):
        for name in order[order.index(step):]:
            self.data['steps'].pop(name, None)
        atomic_json(self.path, self.data)

    def finish(self, step, paths, allow_empty=False):
        outputs = {}
        for value in paths:
            path = inside(self.root, value)
            if not path.is_file() or (not allow_empty and not path.stat().st_size):
                raise ValueError('Saída ausente/vazia: ' + str(path))
            outputs[path.relative_to(self.root.resolve()).as_posix()] = digest(path)
        if not outputs:
            raise ValueError('Etapa não produziu arquivos verificáveis.')
        self.data['steps'][step] = {'outputs': outputs}
        atomic_json(self.path, self.data)
