"""Read the selected release manifest, validate files and perform offline checks."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

IDENT = r'[a-zA-Z0-9_][a-zA-Z0-9._-]*'
FIELDS = {'name','version','source','category','entry','environment','interpreter',
          'dependencies','import_root','verify_imports','version_output','files'}


def require(ok, message):
    if not ok:
        raise ValueError(str(message))


def relative(value):
    require(isinstance(value, str) and value and all(re.fullmatch(IDENT, x)
            for x in value.split('/')), f'invalid relative path: {value!r}')
    return Path(value)


def unique(pairs):
    data = {}
    for key, value in pairs:
        require(key not in data, f'duplicate key: {key}')
        data[key] = value
    return data


def read_profile(path):
    p = json.loads(path.read_bytes(), object_pairs_hook=unique)
    require(isinstance(p, dict) and set(p) == FIELDS, 'invalid profile fields')
    for key in ('name','version'):
        require(re.fullmatch(IDENT,p[key]), f'invalid {key}')
    require(p['category'] in ('bin','bin-rpi'), 'invalid category')
    for key in ('source','entry','import_root'):
        relative(p[key])
    require(isinstance(p['files'],dict) and p['entry'] in p['files'], 'missing entry')
    for name, sha in p['files'].items():
        relative(name)
        require(re.fullmatch('[a-f0-9]{64}',sha), f'invalid hash: {name}')
    for key in ('dependencies','verify_imports'):
        require(isinstance(p[key],list) and all(isinstance(m,str) and
                all(n.isidentifier() for n in m.split('.')) for m in p[key]), key)
    env, exe = p['environment'], p['interpreter']
    if env == 'portable':
        require(exe == '/usr/bin/env python3', 'portable interpreter')
    elif env in ('system','rpi','lab314'):
        directory = '/usr/bin' if env=='system' else f'/opt/{env}/bin'
        require(exe in (directory+'/python',directory+'/python3'), 'environment/interpreter mismatch')
    else:
        raise ValueError('unknown environment')
    require(isinstance(p['version_output'], str) and p['version_output'], 'missing version output')
    return p


def clean_path(path):
    require(path.is_absolute() and path.resolve() == path, f'noncanonical or symlinked path: {path}')


def contents(root, name):
    path = root/name
    clean_path(path)
    require(path.is_file(), f'missing regular file: {path}')
    return path.read_bytes()


def validate(p, root, installed=False):
    if installed:
        actual = set()
        for f in root.rglob('*'):
            require(not f.is_symlink(), f'unexpected symlink: {f}')
            if f.is_dir():
                require(any(n.startswith(str(f.relative_to(root))+'/') for n in p['files']), f'unexpected directory: {f}')
            else:
                actual.add(str(f.relative_to(root)))
        require(actual == set(p['files']), 'installed file list differs')
    for name, sha in p['files'].items():
        data = contents(root, name)
        if installed:
            path = root/name
            mode = 0o755 if name == p['entry'] else 0o644
            require(stat.S_IMODE(path.stat().st_mode) == mode, f'incorrect permissions: {path}')
        if name == p['entry']:
            header, separator, body = data.partition(b'\n')
            expected = '#!'+p['interpreter'] if installed else '#!/usr/bin/env python3'
            require(header == expected.encode() and separator, f'unexpected shebang: {root/name}')
            data = b'#!/usr/bin/env python3\n'+body
        require(hashlib.sha256(data).hexdigest()==sha, f'checksum mismatch: {root/name}')


def interpreter(p):
    return shutil.which('python3') if p['environment']=='portable' else p['interpreter']


def probe(p, runtime=None):
    exe = interpreter(p)
    require(exe and os.access(exe,os.X_OK), f'missing interpreter: {exe}')
    # Test with the caller's inherited environment, including its library paths.
    # cwd=/ prevents project-local modules from satisfying external dependencies.
    code = """
import importlib,sys,json
from pathlib import Path
env,exe,modules,root,local=json.loads(sys.argv[1])
if env != 'portable' and Path(sys.prefix).resolve()!=Path(exe).parent.parent.resolve():
    raise SystemExit('wrong runtime prefix: '+sys.prefix)
print('Python',sys.executable,sys.version.split()[0],'prefix',sys.prefix)
for name in modules:
    m=importlib.import_module(name)
    print(name,getattr(m,'__file__',None))
if root:
    sys.path.insert(0,root)
    for name in local:
        m=importlib.import_module(name)
        if not Path(m.__file__).resolve().is_relative_to(Path(root)):
            raise SystemExit('unexpected location: '+str(m.__file__))
"""
    args = [p['environment'],exe,p['dependencies'],str(runtime/p['import_root']) if runtime else '',p['verify_imports']]
    subprocess.run([exe,'-B','-c',code,json.dumps(args)],cwd='/',check=True,timeout=45)


def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('fields','preflight','stage','verify','tree','target'))
    parser.add_argument('profile',type=Path)
    parser.add_argument('source',type=Path)
    parser.add_argument('runtime',type=Path,nargs='?')
    parser.add_argument('extra',type=Path,nargs='?')
    a=parser.parse_args()
    p=read_profile(a.profile)
    src=a.source/relative(p['source'])
    runtime=a.runtime
    if a.action=='target':
        # Apply the same trusted-directory and checkout policy before making
        # directories or removing a release, including an empty target.
        tool = Path(__file__).resolve().parents[1]/'tools/set-python-shebang.py'
        spec = importlib.util.spec_from_file_location('shebang_policy',tool)
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        for path in (runtime.parent,runtime,runtime/'bin',runtime/'bin-rpi',runtime/'lib'):
            if path.exists():
                with policy.directory(path, True):
                    pass
        return
    if a.action=='fields':
        for k in ('name','version','category','entry','environment','interpreter'):
            print(p[k])
        return
    if a.action=='tree':
        validate(p,runtime,installed=True)
        return
    if a.action in ('preflight','stage'):
        validate(p,src)
        if a.action=='preflight':
            probe(p)
            return
        runtime.mkdir(mode=0o755)
        for name in p['files']:
            data=contents(src,name)
            require(hashlib.sha256(data).hexdigest()==p['files'][name],f'source changed: {name}')
            dst=runtime/name
            dst.parent.mkdir(parents=True,exist_ok=True)
            dst.write_bytes(data)
            dst.chmod(0o755 if name==p['entry'] else 0o644)
        rule={'path':p['entry'],'env':p['environment'],'from':'#!/usr/bin/env python3',
              'to':'#!'+p['interpreter'],'sha256':p['files'][p['entry']]}
        a.extra.write_text(json.dumps(dict(version=1,profile=p['name'],target=str(runtime),files=[rule])))
    else:
        validate(p,runtime,installed=True)
        probe(p,runtime)
        entry=a.extra or runtime/p['entry']
        require(entry.resolve()==runtime/p['entry'], f'unexpected command: {entry}')
        result=subprocess.check_output([entry,'--version'],cwd='/',text=True,timeout=30)
        require(result.strip()==p['version_output'],f'unexpected version: {result!r}')
        print(result.strip())


if __name__=='__main__':
    try:
        run()
    except (OSError,ValueError,TypeError,subprocess.SubprocessError) as exc:
        sys.exit(f'ERROR: {exc}')
