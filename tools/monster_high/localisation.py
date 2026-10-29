"""Inspect UTF-8 candidates and apply bounded subtitle proofs to owned HNK copies.

This does not yet rebuild HNK tables or relocate strings. Extracted offsets are
candidate strings, not a validated catalogue of subtitle IDs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

TOKENS = re.compile(r'<[^>]+>|&[A-Za-z_][A-Za-z0-9_]*;|\{[^}]+\}|%(?:\d+\$)?[-+0 #]*\d*(?:\.\d+)?[sdifuxX]')

def digest(data):
    return hashlib.sha256(data).hexdigest()

def extract(data):
    rows = []
    for match in re.finditer(rb'[^\x00]+', data):
        if match.end() == len(data):
            continue
        try:
            text = match.group().decode('utf-8')
        except UnicodeDecodeError:
            continue
        if len(text) < 3 or not any(c.isalpha() for c in text):
            continue
        if any(not c.isprintable() and c not in '\n\r\t' for c in text):
            continue
        rows.append(dict(offset=match.start(), byte_length=len(match.group()), text=text))
    return dict(source_sha256=digest(data), method='UTF-8 NUL-delimited candidates; not all are subtitles', strings=rows)

def patch(data, manifest):
    if manifest['source_sha256'] != digest(data):
        raise ValueError('Source hash differs from the approved manifest')
    result = bytearray(data)
    ranges = []
    for item in manifest['replacements']:
        offset = item['offset']
        original = item['source'].encode('utf-8')
        translated = item['translation'].encode('utf-8')
        end = offset + len(original)
        if not original or offset <= 0 or end >= len(data):
            raise ValueError('Invalid string bounds')
        if data[offset:end] != original or data[end] != 0 or data[offset-1] != 0:
            raise ValueError('Source string or NUL boundary mismatch')
        if '\0' in item['translation'] or len(translated) > len(original):
            raise ValueError('Translation exceeds the original UTF-8 byte span or contains NUL')
        if TOKENS.findall(item['source']) != TOKENS.findall(item['translation']):
            raise ValueError('Formatting tokens differ')
        if any(offset < hi and end > lo for lo, hi in ranges):
            raise ValueError('Overlapping replacements')
        ranges.append((offset, end))
        # Keep terminator location, file size and all relocation/offset tables.
        result[offset:end] = translated.ljust(len(original), b' ')
    assert len(result) == len(data)
    return bytes(result)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    scan = sub.add_parser('extract')
    scan.add_argument('source', type=Path); scan.add_argument('output', type=Path)
    edit = sub.add_parser('patch')
    edit.add_argument('source', type=Path); edit.add_argument('manifest', type=Path); edit.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve() or args.output.exists():
        parser.error('Choose a new output file; source and existing outputs are preserved')
    data = args.source.read_bytes()
    if args.command == 'extract':
        result = extract(data)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"{len(result['strings'])} UTF-8 candidates; source SHA256 {result['source_sha256']}")
    else:
        manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
        output = patch(data, manifest)
        args.output.write_bytes(output)
        print(f'{len(manifest["replacements"])} bounded replacements; {len(output)} bytes; SHA256 {digest(output)}')

if __name__ == '__main__':
    main()
