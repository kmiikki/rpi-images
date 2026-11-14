#!/usr/bin/env python3
"""Inspect Python entry points and update approved installation copies on Linux."""
import argparse
import ast
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys

VERSION = '0.1.0'
ENVS = ('portable', 'system', 'rpi', 'lab314')
PORTABLE = '#!/usr/bin/env python3'
HARDWARE = {'picamera2', 'libcamera', 'smbus', 'smbus2', 'RPi', 'gpiozero', 'gpiod',
            'lgpio', 'pigpio', 'spidev', 'board', 'busio', 'adafruit_blinka'}

# Walk dotted names without importing parent packages. The selected interpreter
# supplies its own extension suffixes, site directories and APT .pth settings.
PROBE = """
import importlib.machinery as m, json, sys
def present(name):
    parts = name.split('.')
    path = None
    for i in range(len(parts)):
        mod = '.'.join(parts[:i+1])
        spec = m.BuiltinImporter.find_spec(mod) or m.FrozenImporter.find_spec(mod) or m.PathFinder.find_spec(mod, path)
        if spec is None:
            return False
        path = spec.submodule_search_locations
        if path is None and i+1 < len(parts):
            return False
    return True
print(json.dumps(dict(version=sys.version.split()[0], prefix=sys.prefix,
                      modules={n:present(n) for n in json.load(sys.stdin)})))
"""


class Problem(ValueError):
    pass


def probe(exe, names):
    if not exe:
        return {'path': None, 'error': 'interpreter missing'}
    try:
        # Do not execute a PATH shim or a selected Python script named python3.
        with open(exe, 'rb') as binary:
            if binary.read(4) != b'\x7fELF':
                raise Problem('not a native Linux interpreter (wrapper not executed)')
        result = subprocess.run([exe, '-I', '-B', '-c', PROBE], cwd='/',
                                input=json.dumps(sorted(names)), capture_output=True,
                                text=True, timeout=8, check=True)
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or not str(data.get('version')).startswith('3.') or not isinstance(data.get('modules'), dict) or not data.get('prefix'):
            raise Problem('expected Python 3')
        return dict(data, path=str(exe))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        return {'path': str(exe), 'error': str(exc)}


def discover(names, opt=Path('/opt'), system_bin=Path('/usr/bin'), registry=None):
    prefixes = {k: opt/k for k in ('lab314', 'rpi')}
    conda = {opt/'conda'}
    registry = registry or Path.home()/'.conda/environments.txt'
    if registry.is_file():
        conda.update(Path(s) for s in registry.read_text().splitlines() if s.startswith('/'))
    active = os.environ.get('CONDA_PREFIX')
    if active:
        conda.add(Path(active))
    conda.update(prefixes.values())
    for base in list(conda):
        if (base/'envs').is_dir():
            conda.update((base/'envs').iterdir())
    cache = {}

    def inspect(exe):
        if exe not in cache:
            cache[exe] = probe(exe, names)
        return cache[exe].copy()

    def interpreter(directory, prefix=None):
        error = inspect(None)
        for name in ('python3', 'python'):
            exe = directory/name
            if not exe.is_file() or not os.access(exe, os.X_OK):
                continue
            info = inspect(exe)
            if prefix and not info.get('error') and Path(info['prefix']).resolve() != prefix.resolve():
                info['error'] = 'interpreter runs in a different prefix'
            if not info.get('error'):
                return info
            error = info
        return error

    registered = {str(p): interpreter(p/'bin', p) for p in sorted(conda)
                  if (p/'conda-meta').is_dir()}
    envs = {'system': interpreter(system_bin)}
    for key, prefix in prefixes.items():
        alternatives = [v for p, v in registered.items() if Path(p).name == key and not v.get('error')]
        if prefix.exists() or not alternatives:
            envs[key] = interpreter(prefix/'bin', prefix)
        elif len(alternatives) == 1:
            envs[key] = alternatives[0]
        else:
            envs[key] = {'path': None, 'error': 'multiple registered prefixes with this name'}
    path_pythons = {k: inspect(Path(p) if (p := shutil.which(k)) else None)
                    for k in ('python3', 'python')}
    envs['portable'] = path_pythons['python3'].copy()
    if not os.access('/usr/bin/env', os.X_OK):
        envs['portable']['error'] = '/usr/bin/env unavailable'
    conflicts = []
    for name, info in path_pythons.items():
        if active and (info['path'] or name == 'python3'):
            if info.get('error') or Path(info['prefix']).resolve() != Path(active).resolve():
                conflicts.append(f'{name}: expected {active}/bin, found {info["path"]}')
    return envs, path_pythons, registered, conflicts


def first_line(data):
    head, sep, tail = data.partition(b'\n')
    if sep and head.endswith(b'\r'):
        return head[:-1], b'\r\n', tail
    return head, sep, tail


def recognized(line, envs):
    if line == PORTABLE:
        return 'portable'
    for name in ('system', 'rpi', 'lab314'):
        path = envs[name]['path']
        directory = Path(path).parent if path else Path(
            '/usr/bin' if name == 'system' else f'/opt/{name}/bin')
        if line in {'#!'+str(directory/k) for k in ('python', 'python3')}:
            return name
    return None


def dependencies(data):
    tree = ast.parse(data)
    names, uncertainties = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                uncertainties.add('relative import needs application context')
            elif node.module:
                names.add(node.module)
                if node.module == 'RPi' and any(a.name == 'GPIO' for a in node.names):
                    names.add('RPi.GPIO')
        elif isinstance(node, ast.Call):
            func = node.func
            if getattr(func, 'id', '') == '__import__' or getattr(func, 'attr', '') == 'import_module':
                uncertainties.add('dynamic import needs review')
    return names, sorted(uncertainties)


def choose(current, names, doubts, envs, requested):
    def missing(env):
        return sorted(n for n in names if not envs[env].get('modules', {}).get(n))

    def fits(env):
        return not envs[env].get('error') and not missing(env)

    if requested:
        if not fits(requested):
            return None, f'{requested}: ' + (envs[requested].get('error') or 'missing '+', '.join(missing(requested)))
        return requested, 'explicit environment'
    if doubts:
        return None, '; '.join(doubts)
    hardware = any(n.split('.')[0] in HARDWARE for n in names)
    if hardware:
        for key in ('rpi', 'system'):
            if fits(key):
                return key, 'hardware imports and static dependencies located'
    elif current == 'portable' and envs['portable'].get('error'):
        return None, 'portable python3 unavailable'
    elif fits(current):
        return current, 'current environment covers static imports'
    else:
        options = [key for key in ('system', 'rpi', 'lab314') if fits(key)]
        if len(options) == 1:
            return options[0], 'only verified environment covering static imports'
    return None, 'no unique compatible choice; check static imports: '+', '.join(sorted(names))


def digest(data):
    return hashlib.sha256(data).hexdigest()


@dataclass
class Entry:
    path: Path
    data: bytes
    info: os.stat_result
    names: set
    doubts: list
    approved: dict
    new: bytes = b''
    result: str = ''


def identity(s):
    return s.st_dev, s.st_ino, s.st_size, s.st_ctime_ns


def in_checkout(fd):
    try:
        marker = os.stat('.git', dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(marker.st_mode):
        return True  # includes linked worktrees
    try:
        os.stat('.git/HEAD', dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        # Some sandbox mounts expose an empty, read-only .git placeholder.
        return not (os.statvfs(fd).f_flag & os.ST_RDONLY) and bool(marker.st_mode & 0o222)
    return True


def safe_dir(s, ancestor=False):
    # User namespaces can map the filesystem root owner to an overflow UID.
    trusted = s.st_uid in (0, os.geteuid())
    if ancestor and not trusted and s.st_uid == os.stat('/').st_uid:
        trusted = any(os.path.samestat(s, os.stat(p)) for p in ('/', '/tmp'))
    sticky = ancestor and s.st_mode & stat.S_ISVTX
    if not trusted or (s.st_mode & 0o022 and not sticky):
        raise Problem('installation path must be controlled by the current user or root')


@contextmanager
def directory(path, editing=False):
    """Pin each component; never traverse symlinks, including the target root."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        fd = os.open('/', flags)
        stack.callback(os.close, fd)
        for component in path.parts[1:]:
            if editing:
                safe_dir(os.fstat(fd), ancestor=True)
                if component == '.git' or in_checkout(fd):
                    raise Problem('source checkout is not an installation target')
            fd = os.open(component, flags, dir_fd=fd)
            stack.callback(os.close, fd)
        if editing:
            safe_dir(os.fstat(fd))
            if in_checkout(fd):
                raise Problem('source checkout is not an installation target')
        yield fd


def eligible(s):
    if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
        raise Problem('requires a regular file with one link')
    if not s.st_mode & 0o111:
        raise Problem('not an executable script')
    if s.st_mode & (stat.S_ISUID | stat.S_ISGID):
        raise Problem('privileged file')


def snapshot(path, editing):
    with directory(path.parent, editing) as fd:
        eligible(os.stat(path.name, dir_fd=fd, follow_symlinks=False))
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(path.name, flags, dir_fd=fd), 'rb') as src:
            info = os.fstat(src.fileno())
            eligible(info)
            if editing and (info.st_uid not in (0, os.geteuid()) or info.st_mode & 0o022):
                raise Problem('file owner or write permissions allow competing edits')
            data = src.read()
            if identity(info) != identity(os.fstat(src.fileno())):
                raise Problem('file changed while reading')
    return data, info


def make_plan(entry, envs, preferred):
    head, ending, tail = first_line(entry.data)
    line = head.decode('ascii', 'backslashreplace')
    current = recognized(line, envs)
    print('  Current:', ascii(line) if head.startswith(b'#!') else '(missing)', current or 'unknown')
    if current is None:
        raise Problem('unknown or missing Python shebang')
    if ending == b'\r\n':
        print('  Warning: CRLF preserved; Linux direct execution may fail on the carriage return.')
    env, reason = choose(current, entry.names, entry.doubts, envs, entry.approved.get('env', preferred))
    if env is None:
        raise Problem('AMBIGUOUS: '+reason)
    new = PORTABLE if env == 'portable' else '#!'+envs[env]['path']
    # Keep equivalent validated interpreter aliases in the same prefix.
    if current == env and current != 'portable' and Path(line[2:]).is_file():
        try:
            if os.path.samefile(line[2:], envs[env]['path']):
                new = line
        except OSError:
            pass
    if len(os.fsencode(new)) > 255 or (env != 'portable' and any(c.isspace() for c in new)):
        raise Problem('interpreter path cannot be expressed in a Linux shebang')
    result = new.encode() + ending + tail
    if entry.approved:
        rule = entry.approved
        if new != rule['to']:
            raise Problem('interpreter differs from approved destination')
        if recognized(rule['from'], envs) is None:
            raise Problem('unrecognized approved source shebang')
        original = rule['from'].encode()+ending+tail
        if line not in (rule['from'], new) or digest(original) != rule['sha256']:
            raise Problem('source does not match approved contents')
    entry.new = result
    entry.result = 'KEEP' if result == entry.data else 'CHANGE'
    if entry.result == 'CHANGE' and not entry.info.st_mode & 0o222:
        raise Problem('read-only file')
    print(f'  {entry.result} {env}: {new} ({reason})')
    for doubt in entry.doubts:
        print('  Uncertainty:', doubt)


def stage(fd, original_fd, data, info, stack):
    name = '.shebang-'+secrets.token_hex(16)
    tmp = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=fd)
    def remove():
        try:
            os.unlink(name, dir_fd=fd)
        except FileNotFoundError:
            pass
    stack.callback(remove)
    with os.fdopen(tmp, 'wb') as out:
        out.write(data)
        out.flush()
        s = os.fstat(tmp)
        if (s.st_uid, s.st_gid) != (info.st_uid, info.st_gid):
            os.fchown(tmp, info.st_uid, info.st_gid)
        os.fchmod(tmp, stat.S_IMODE(info.st_mode))
        original_attrs = set(os.listxattr(original_fd))
        for attr in set(os.listxattr(tmp)) - original_attrs:
            os.removexattr(tmp, attr)
        for attr in original_attrs:
            if attr.startswith('security.') and attr != 'security.selinux':
                raise Problem('unsupported security attribute: '+attr)
            os.setxattr(tmp, attr, os.getxattr(original_fd, attr))
        os.utime(tmp, ns=(info.st_atime_ns, info.st_mtime_ns))
        os.fsync(tmp)
        return name, os.fstat(tmp).st_ino


def apply(entries):
    # Prepare both directions before publishing anything. Cooperating invocations
    # serialize on parent directories, in a fixed order to avoid deadlocks.
    with ExitStack() as stack:
        parents = {}
        for parent in sorted({e.path.parent for e in entries}):
            fd = stack.enter_context(directory(parent, True))
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            parents[parent] = fd
        ready = []
        for e in entries:
            fd = parents[e.path.parent]
            src = os.open(e.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            stack.callback(os.close, src)
            if identity(os.fstat(src)) != identity(e.info):
                raise Problem(f'{e.path}: changed since review')
            if not os.access(e.path.name, os.W_OK, dir_fd=fd, effective_ids=True):
                raise Problem(f'{e.path}: write permission denied')
            backup, _ = stage(fd, src, e.data, e.info, stack)
            temp, inode = stage(fd, src, e.new, e.info, stack)
            ready.append((e, fd, backup, temp, inode))
        attempted = []
        try:
            for e, fd, backup, temp, inode in ready:
                with directory(e.path.parent, True) as check:
                    if not os.path.samestat(os.fstat(fd), os.fstat(check)):
                        raise Problem('parent directory changed')
                if identity(os.stat(e.path.name, dir_fd=fd, follow_symlinks=False)) != identity(e.info):
                    raise Problem(f'{e.path}: changed before replacement')
                attempted.append((e, fd, backup, inode))
                os.replace(temp, e.path.name, src_dir_fd=fd, dst_dir_fd=fd)
                os.fsync(fd)
        except BaseException:
            for e, fd, backup, inode in reversed(attempted):
                if os.stat(e.path.name, dir_fd=fd, follow_symlinks=False).st_ino == inode:
                    os.replace(backup, e.path.name, src_dir_fd=fd, dst_dir_fd=fd)
                    os.fsync(fd)
            raise


def unique(pairs):
    result = {}
    for k,v in pairs:
        if k in result:
            raise Problem('duplicate manifest key: '+k)
        result[k] = v
    return result


def manifest(args):
    data = json.loads(args.manifest.read_bytes(), object_pairs_hook=unique)
    if not isinstance(data, dict) or set(data) != {'version','profile','target','files'}:
        raise Problem('invalid manifest fields')
    if type(data['version']) is not int or data['version'] != 1:
        raise Problem('unsupported manifest version')
    if not isinstance(data['profile'], str) or not data['profile'].strip():
        raise Problem('missing manifest profile')
    if args.approved_profile and data['profile'] != args.approved_profile:
        raise Problem('profile approval mismatch')
    if str(args.target) != data['target'] or not args.target.is_absolute():
        raise Problem('--target must match the absolute manifest target')
    if not isinstance(data['files'], list) or not data['files']:
        raise Problem('manifest files must be a nonempty array')
    rules = []
    for row in data['files']:
        if not isinstance(row, dict) or set(row) != {'path','env','from','to','sha256'}:
            raise Problem('invalid manifest file fields')
        if not all(isinstance(v,str) and v for v in row.values()) or row['env'] not in ENVS:
            raise Problem('invalid file rule')
        if not re.fullmatch('[0-9a-f]{64}', row['sha256']) or not row['from'].startswith('#!'):
            raise Problem('invalid source hash or shebang')
        if Path(row['path']).is_absolute():
            raise Problem('manifest paths must be relative')
        rules.append((Path(row['path']), row))
    return rules


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for mode, helptext in [('analyze','inspect (default)'), ('dry-run','print the plan'),
                           ('check','return 1 if changes are needed'), ('apply','apply the reviewed plan')]:
        modes.add_argument('--'+mode, action='store_true', help=helptext)
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--env', choices=ENVS, help='explicit interpreter choice')
    parser.add_argument('--manifest', type=Path, help='installer JSON profile')
    parser.add_argument('--approved-profile', help='name of the independently approved installer profile')
    parser.add_argument('--non-interactive', action='store_true', help='never prompt')
    parser.add_argument('--target', type=Path, help='installation root (required for apply and manifests)')
    parser.add_argument('paths', nargs='*', type=Path, help='individual executable scripts')
    args = parser.parse_args(argv)
    if args.manifest and (args.paths or args.env or not args.target):
        parser.error('--manifest needs --target and supplies all paths and environments')
    if args.approved_profile and not args.manifest:
        parser.error('--approved-profile requires --manifest')
    if args.apply and (not args.target or not (args.paths or args.manifest)):
        parser.error('--apply needs --target and selected files')
    if args.apply and args.non_interactive and not (args.manifest and args.approved_profile):
        parser.error('unattended apply requires a manifest and --approved-profile')
    try:
        rules = manifest(args) if args.manifest else [(p,{}) for p in args.paths]
        entries, seen = [], set()
        errors = []
        root = args.target.absolute() if args.target else None
        for name, rule in rules:
            path = (root/name if root else name).absolute()
            try:
                if '..' in path.parts or (root and not path.is_relative_to(root)):
                    raise Problem('outside installation target or contains ..')
                if path in seen:
                    raise Problem('duplicate file')
                seen.add(path)
                data, info = snapshot(path, args.apply or bool(args.target and (args.check or args.dry_run)))
                head = first_line(data)[0]
                if head.startswith(b'#!') and not re.search(rb'(?:/| )python(?:3)?$', head):
                    raise Problem(f'unknown or non-Python shebang: {head!r}')
                if not first_line(data)[0].startswith(b'#!'):
                    raise Problem('missing shebang')
                names, doubts = dependencies(data)
                for top in sorted({n.split('.')[0] for n in names}):
                    if (path.parent/(top+'.py')).exists() or (path.parent/top).is_dir():
                        doubts.append('local module needs application-level review: '+top)
                entries.append(Entry(path, data, info, names, doubts, rule))
            except (ValueError, OSError, SyntaxError) as exc:
                errors.append(f'{path}: {exc}')
        names = set().union(*(e.names for e in entries))
        envs, paths, registered, conflicts = discover(names)
        try:
            os_name = platform.freedesktop_os_release().get('PRETTY_NAME', 'Linux')
        except OSError:
            os_name = platform.system()
        print('OS:', os_name,
              '| Architecture:', platform.machine())
        print('CONDA_PREFIX:', os.environ.get('CONDA_PREFIX'), '| CONDA_DEFAULT_ENV:', os.getenv('CONDA_DEFAULT_ENV'))
        for key, val in [*envs.items(), *registered.items(), *[('PATH '+k,v) for k,v in paths.items()]]:
            print(f'  {key}: {val["path"]} | {val.get("version","?")} | {val.get("error","OK")}')
        print('Environment consistency:', 'WARNING: '+ '; '.join(conflicts) +
              '. Check login-shell PATH ordering.' if conflicts else 'PASS')
        for e in entries:
            print(e.path)
            try:
                make_plan(e, envs, args.env)
            except Problem as exc:
                errors.append(f'{e.path}: {exc}')
        if errors:
            print('\n'.join(errors), file=sys.stderr)
            return 2
        changes = [e for e in entries if e.result == 'CHANGE']
        if args.check:
            return int(bool(changes or conflicts))
        if args.apply and changes:
            if not args.non_interactive:
                if not sys.stdin.isatty():
                    raise Problem('interactive approval needs a terminal')
                if input('Apply changes? [y/N] ').strip().lower() != 'y':
                    return 1
            # The prompt may have been open while an environment was replaced.
            fresh = discover(names)[0]
            for e in changes:
                previous = e.new
                make_plan(e, fresh, args.env)
                if e.new != previous:
                    raise Problem('proposed interpreter changed after review')
            apply(changes)
            print(f'Applied {len(changes)} change(s).')
        return 0
    except (EOFError, KeyboardInterrupt):
        print('Cancelled.', file=sys.stderr)
        return 130
    except (OSError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
