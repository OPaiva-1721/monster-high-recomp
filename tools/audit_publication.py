"""Read-only checks of Git objects; reports locations, never secret contents.

This is an aid to manual publication review, not a copyright or security guarantee.
Untracked/ignored local assets are not part of Git and are not opened.
"""
import argparse
import json
from pathlib import Path,PurePosixPath
import re
import subprocess

FORBIDDEN_SUFFIXES={'.iso','.pkg','.rap','.dkey','.elf','.self','.sprx','.exe','.dll','.pdb',
                    '.apk','.so','.gcap','.partial','.hnk','.xfbin','.bmp','.png','.jpg','.jpeg','.wav','.raw'}
SECRET_PATTERNS=(re.compile(rb'gh[pousr]_[A-Za-z0-9]{36,}'),
                 re.compile(rb'github_pat_[A-Za-z0-9_]{50,}'),
                 re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'))

def git(repo,*args):
    result=subprocess.run(['git','-C',str(repo),*args],capture_output=True,check=True)
    return result.stdout

def path_reason(path):
    p=PurePosixPath(path);parts={s.lower() for s in p.parts};lower=path.lower()
    if lower=='rom/leia-me.md':return None
    if p.suffix.lower() in FORBIDDEN_SUFFIXES:return 'game/binary/capture extension; requires removal or explicit manual exception'
    if parts & {'rom','build','generated','recompiled','savedata','saves','firmware','dev_flash'}:return 'private/generated directory'
    if p.name.lower() in {'eboot.bin','param.pfd','sys-data','ppu_recomp.h','keys.txt'}:return 'game-derived or key file'
    return None

def audit_repository(repo,history=False):
    repo=Path(repo).resolve();blockers=[];warnings=[]
    trees = set(git(repo,'log','--all','--format=%T').splitlines()) if history else {b'HEAD'}
    candidates=[]
    for tree in trees:
        rows=git(repo,'ls-tree','-r','-z',tree.decode('ascii')).split(b'\0')
        for row in rows:
            if not row:continue
            meta,path=row.split(b'\t',1);mode,kind,oid=meta.split()
            if kind==b'blob':candidates.append((oid.decode(),path.decode('utf-8','replace')))
    unique={}
    # The same object can be referenced by multiple paths: audit every path.
    for oid,path in candidates:unique.setdefault(oid,set()).add(path)
    proc=subprocess.Popen(['git','-C',str(repo),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    blobs=0
    try:
        for oid,paths in unique.items():
            proc.stdin.write((oid+'\n').encode());proc.stdin.flush()
            header=proc.stdout.readline().split()
            if len(header)!=3:raise ValueError('Unexpected Git object header')
            kind=header[1];size=int(header[2]);data=proc.stdout.read(size)
            if len(data)!=size or proc.stdout.read(1)!=b'\n':raise ValueError('Truncated Git object')
            if kind!=b'blob':continue
            blobs+=1
            for path in sorted(paths):
                reasons=[];reason=path_reason(path)
                if reason:reasons.append(reason)
                if data.startswith((b'\x7fELF',b'MZ',b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff')):reasons.append('binary magic in Git object')
                if any(pattern.search(data) for pattern in SECRET_PATTERNS):reasons.append('credential/private-key pattern; value redacted')
                if reasons:blockers.append(dict(path=path,object=oid,reasons=reasons))
                if size>10*1024*1024:warnings.append(dict(path=path,object=oid,reason='large object; manual provenance review required',bytes=size))
    finally:
        proc.stdin.close();proc.stdout.close();proc.stderr.close();proc.wait()
    return dict(repository=str(repo),scope='all local refs and reachable history' if history else 'HEAD tree',blobs_checked=blobs,
                blockers=blockers,warnings=warnings,note='Heuristic report; also review patches, dependencies and provenance manually. Ignored local files not scanned.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path('.'))
    parser.add_argument('--history',action='store_true')
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();report=audit_repository(args.repo,args.history)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"Checked {report['blobs_checked']} blobs; blockers={len(report['blockers'])}; warnings={len(report['warnings'])}; report={args.report}")
    return 1 if report['blockers'] else 0

if __name__=='__main__':raise SystemExit(main())
