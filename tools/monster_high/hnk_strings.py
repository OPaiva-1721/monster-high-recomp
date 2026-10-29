"""Read/rebuild observed StringTable chunks in owned Monster High HNK files."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from localisation import TOKENS

def chunks(data):
    pos = 0
    while pos < len(data):
        if len(data)-pos < 8: raise ValueError('Truncated HNK header')
        size, kind = struct.unpack_from('<II', data, pos)
        if size > len(data)-pos-8: raise ValueError('Truncated HNK chunk')
        yield pos, kind, data[pos+8:pos+8+size]
        pos += 8+size

def table(payload):
    if len(payload) < 28: raise ValueError('Truncated StringTable')
    version, mode, count = struct.unpack_from('>III', payload)
    offsets, hashes = struct.unpack_from('<II', payload, 12)
    if (version, mode) != (1, 2) or offsets != 28 or hashes != 28+4*count:
        raise ValueError('Unsupported StringTable layout')
    start = hashes+4*count
    if start > len(payload): raise ValueError('Invalid table bounds')
    entries = []
    for i in range(count):
        offset = struct.unpack_from('>I', payload, offsets+4*i)[0]
        key = struct.unpack_from('>I', payload, hashes+4*i)[0]
        if not start <= offset < len(payload): raise ValueError('Invalid text offset')
        end = payload.find(b'\0', offset)
        if end < 0: raise ValueError('Missing string terminator')
        entries.append(dict(id=f'{key:08X}', source=payload[offset:end].decode('utf-8')))
    if len({x['id'] for x in entries}) != count: raise ValueError('Duplicate table IDs')
    return start, entries

def tables(data):
    name = None
    for pos, kind, payload in chunks(data):
        if kind == 0x40071:
            name = None
            marker = b'StringTable\0'
            at = payload.find(marker)
            if at >= 0:
                tail = payload[at+len(marker):]
                name = tail[:tail.index(0)].decode('ascii')
        elif kind == 0x4100F and name is not None:
            start, entries = table(payload)
            yield pos, name, payload, start, entries
            name = None

def catalogue(data, names=('Dialog',)):
    result = []
    for _, name, _, _, entries in tables(data):
        if name in names:
            result.extend(dict(table=name, **entry, translation=None) for entry in entries)
    if not result: raise ValueError('No selected StringTable found')
    return dict(source_sha256=hashlib.sha256(data).hexdigest(), entries=result)

def heap_budgets(data):
    records=list(chunks(data))
    if not records or records[0][1]!=0x40070 or len(records[0][2])!=592:
        raise ValueError('Unsupported HNK root allocation header')
    root=records[0][2]
    count=struct.unpack_from('<I',root,12)[0]
    if not 1 <= count <= 8:raise ValueError('Invalid HNK heap count')
    totals=[0]*count
    declared=[struct.unpack_from('<I',root,16+72*i+64)[0] for i in range(count)]
    for _,kind,payload in records[1:]:
        if kind & 0xFFF not in (2,15):continue
        heap=(kind>>12)&15
        align=kind>>16
        if heap>=count or not align or align>4096 or align & (align-1):
            raise ValueError('Unsupported allocation heap/alignment')
        totals[heap]=(totals[heap]+align-1)&~(align-1)
        totals[heap]+=len(payload)
        if totals[heap]>0xFFFFFFFF:raise ValueError('Heap exceeds uint32')
    return totals,declared

def rebuild(data, catalog):
    if catalog['source_sha256'] != hashlib.sha256(data).hexdigest(): raise ValueError('Source hash mismatch')
    budgets,declared=heap_budgets(data)
    if budgets!=declared:raise ValueError('Source allocation budgets do not match observed HNK layout')
    changes = {}
    for entry in catalog['entries']:
        identity = entry['table'], entry['id']
        if identity in changes: raise ValueError('Duplicate catalogue ID')
        changes[identity] = entry
    replacements, used = {}, set()
    for pos, name, payload, start, entries in tables(data):
        translated = []
        changed = False
        for entry in entries:
            identity = name, entry['id']
            item = changes.get(identity)
            value = entry['source']
            if item is not None:
                used.add(identity)
                if item['source'] != value: raise ValueError('Catalogue source differs')
                if item['translation'] is not None:
                    value = item['translation']
                    if not isinstance(value, str) or '\0' in value: raise ValueError('Invalid translation')
                    if TOKENS.findall(entry['source']) != TOKENS.findall(value): raise ValueError('Formatting tokens differ')
                    changed |= value != entry['source']
            translated.append(value)
        if not changed: continue
        # Keep header, IDs, ordering and relocation-field positions. Rebuild only
        # the string blob and its BE offsets, retaining four-byte string padding.
        output = bytearray(payload[:start])
        interned = {}
        for i, value in enumerate(translated):
            raw = value.encode('utf-8')
            if raw not in interned:
                interned[raw] = len(output)
                output.extend(raw+b'\0')
                output.extend(b'\0' * (-(len(output)-start) % 4))
            struct.pack_into('>I', output, 28+4*i, interned[raw])
        if len(output) > 0xFFFFFFFF: raise ValueError('Chunk exceeds uint32')
        replacements[pos] = bytes(output)
    if used != set(changes): raise ValueError('Unknown catalogue table/ID')
    result = bytearray()
    for pos, kind, payload in chunks(data):
        payload = replacements.get(pos, payload)
        result.extend(struct.pack('<II', len(payload), kind)); result.extend(payload)
    budgets,_=heap_budgets(result)
    for heap,size in enumerate(budgets):
        struct.pack_into('<I',result,8+16+72*heap+64,size)
    return bytes(result)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['export','rebuild'])
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--catalogue', type=Path)
    parser.add_argument('--all-tables', action='store_true')
    args = parser.parse_args()
    if args.output.exists() or args.source.resolve()==args.output.resolve(): parser.error('Choose a new output')
    data = args.source.read_bytes()
    if args.command=='export':
        names=tuple(name for _,name,_,_,_ in tables(data)) if args.all_tables else ('Dialog',)
        output=catalogue(data,names)
        args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f"{len(output['entries'])} entries exported by table and ID")
    else:
        if args.catalogue is None: parser.error('--catalogue is required')
        output=rebuild(data,json.loads(args.catalogue.read_text(encoding='utf-8')))
        args.output.write_bytes(output)
        print(f'{len(data)} -> {len(output)} bytes; source preserved')

if __name__=='__main__': main()
