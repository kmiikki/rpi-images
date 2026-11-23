"""Private, versioned records for installer-owned changes."""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid

STATE_DIR = Path('/var/lib/rpi-images')
UNKNOWN = 'Original state unknown – automatic restoration unavailable.'
ABSENT = {'kind': 'absent'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def secure_directory(path, create=False, uid=None):
    if path.parent.resolve() != path.parent:
        raise ValueError(f'Unsafe state directory parent: {path.parent}')
    if create:
        path.mkdir(mode=0o700, exist_ok=True)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != (os.geteuid() if uid is None else uid) or info.st_mode & 0o077:
        raise ValueError(f'State directory must be private and owned by the operator: {path}')
    return True


def private_read(path, uid=None):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != (os.geteuid() if uid is None else uid) or info.st_mode & 0o077:
            raise ValueError(f'Unsafe private state file: {path}')
        return stream.read()


def atomic_write(path, content, mode=0o600, owner=None):
    fd, temp = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            if owner is not None:
                info = os.fstat(stream.fileno())
                if owner != (info.st_uid, info.st_gid):
                    os.fchown(stream.fileno(), *owner)
            if stat.S_IMODE(os.fstat(stream.fileno()).st_mode) != mode:
                os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(temp, path)
        sync_directory(path.parent)
    finally:
        Path(temp).unlink(missing_ok=True)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def tree_fingerprint(root, *, root_only_group=False, ignore_package_cache=False):
    """Inventory file identity and change metadata without following links or mounts."""
    root_stat = root.lstat()
    if root_stat.st_mode & 0o022 or root_stat.st_uid != os.geteuid():
        raise ValueError(f'Environment root is writable by other accounts or is not operator-owned: {root}')
    if root.is_mount():
        raise ValueError(f'Mounted environment requires manual review: {root}')
    # Same-device bind mounts cannot be detected by st_dev alone.
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        point = line.split()[4].replace(r'\040', ' ').replace(r'\011', '\t').replace(r'\134', '\\')
        if Path(point).is_relative_to(root):
            raise ValueError(f'Mounted path in environment: {point}')
    digest = hashlib.sha256()
    count = 0

    def walk_error(error):
        raise error

    for parent, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        dirs.sort()
        for name in sorted(dirs + files):
            path = Path(parent) / name
            info = path.lstat()
            kind = stat.S_IFMT(info.st_mode)
            if kind not in (stat.S_IFDIR, stat.S_IFREG, stat.S_IFLNK) or info.st_dev != root_stat.st_dev:
                raise ValueError(f'Mount or special path in environment: {path}')
            write_mask = 0o002 if root_only_group and info.st_uid==info.st_gid==0 else 0o022
            if info.st_uid != root_stat.st_uid or info.st_mode & write_mask and kind != stat.S_IFLNK:
                raise ValueError(f'Environment contains a path writable by other accounts: {path}')
            if ignore_package_cache and path==root/'pkgs' and kind==stat.S_IFDIR:
                # This operation uses a private package cache, never the base cache.
                dirs.remove(name)
                continue
            target = os.readlink(path) if kind == stat.S_IFLNK else ''
            # ctime also detects content changed with its modification time restored.
            entry = [str(path.relative_to(root)), info.st_mode, info.st_ino,
                     info.st_size, info.st_mtime_ns, info.st_ctime_ns, target]
            digest.update(json.dumps(entry).encode() + b'\n')
            count += 1
    return {'kind': 'tree', 'sha256': digest.hexdigest(), 'entries': count,
            'inode': root_stat.st_ino, 'device': root_stat.st_dev}


class Store:
    def __init__(self, directory=STATE_DIR, root=Path('/')):
        self.directory = directory
        self.root = root
        self.file = directory / 'installation.json'
        self.data = None
        self.reconciled = {}

    def path(self, name):
        logical = Path(name)
        if not logical.is_absolute() or '..' in logical.parts or logical == Path('/'):
            raise ValueError(f'Invalid recorded path: {name}')
        path = self.root.joinpath(*logical.parts[1:])
        if path.parent.resolve() != path.parent:
            raise ValueError(f'Symlinked parent refused: {path}')
        return path

    def trusted_parents(self, name):
        path=self.path(name)
        for parent in path.parents:
            info=parent.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o022:
                raise ValueError(f'Unsafe writable parent directory: {parent}')
            if parent==self.root:
                break
        return path

    def ensure_parents(self, name):
        path=self.path(name)
        for parent in reversed(path.parents):
            if not parent.is_relative_to(self.root):
                continue
            if parent!=self.root:
                parent.mkdir(mode=0o755,exist_ok=True)
            info=parent.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o022:
                raise ValueError(f'Unsafe writable parent directory: {parent}')
        return path

    def load(self):
        if secure_directory(self.directory):
            try:
                self.data = json.loads(private_read(self.file))
            except FileNotFoundError:
                self.data = None
            if self.data is not None:
                if not isinstance(self.data,dict) or self.data.get('version')!=1:
                    raise ValueError('Unsupported installation manifest version')
                if any(not isinstance(self.data.get(key),dict) for key in ('paths','components','services','apt_original','apt_current')):
                    raise ValueError('Incomplete installation manifest; preserve it for review.')
        return self.data

    def save(self):
        atomic_write(self.file, (json.dumps(self.data, indent=2, sort_keys=True) + '\n').encode())

    @contextmanager
    def locked(self):
        secure_directory(self.directory, create=True)
        fd = os.open(self.directory/'lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'r+b') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ValueError('Unsafe lifecycle lock')
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.load()
            yield

    def start(self, state, apt):
        if self.data is None:
            self.data = {'version': 1, 'id': str(uuid.uuid4()), 'created': now(),
                         'target': {k: state.get(k) for k in ('model','os','codename','architecture')},
                         'profile': None, 'keyboard': None, 'pending_boot': None,
                         'components': {}, 'paths': {}, 'services': {},
                         'apt_original': apt, 'apt_current': apt}
            self.data['os_upgrade']={'status':'unknown' if any(state.get('existing',{}).values()) else 'not-started'}
            self.save()

    def snapshot(self, name, tree=False, backup=False):
        path = self.path(name)
        try:
            info = path.lstat()
        except FileNotFoundError:
            return dict(ABSENT)
        if tree:
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError(f'Expected a regular environment directory: {path}')
            return tree_fingerprint(path)
        metadata = dict(mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)
        if stat.S_ISLNK(info.st_mode):
            return dict(kind='symlink', target=os.readlink(path), **metadata)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f'Expected a regular file: {path}')
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
            observed = os.fstat(stream.fileno())
            if (observed.st_dev, observed.st_ino) != (info.st_dev, info.st_ino) or info.st_size > 16*1024*1024:
                raise ValueError(f'File changed or exceeds backup limit: {path}')
            content = stream.read(16*1024*1024+1)
            if len(content) > 16*1024*1024 or os.fstat(stream.fileno()).st_ctime_ns != info.st_ctime_ns:
                raise ValueError(f'File changed or exceeds backup limit: {path}')
        sha = hashlib.sha256(content).hexdigest()
        if backup:
            directory = self.directory/'original'
            secure_directory(directory, create=True)
            dest = directory/sha
            if not dest.exists():
                atomic_write(dest, content)
        return dict(kind='file', sha256=sha, **metadata)

    def inspect(self, name, tree=False, backup=False):
        try:
            return self.snapshot(name, tree, backup)
        except (OSError, ValueError) as error:
            return {'kind': 'unavailable', 'reason': str(error)}

    @contextmanager
    def stage(self, component, targets=(), service_probe=None, repair_missing=False):
        entries = self.data['paths']
        previous = {}
        for name, tree in targets:
            current = self.inspect(name, tree, backup=not tree and name not in entries)
            previous[name] = current
            if name not in entries:
                entries[name] = {'component': component, 'tree': tree, 'original': current}
            else:
                old = entries[name]
                expected = old.get('installed', old['original'])
                reviewed_missing = repair_missing and current==ABSENT and old['original']==ABSENT
                if current != expected and not reviewed_missing:
                    old['conflict'] = 'Changed outside the last recorded operation or an operation was interrupted.'
        service = None
        if service_probe:
            values = service_probe()
            service = self.data['services'].setdefault(component, {'original': values})
            if 'installed' in service and values != service['installed']:
                service['conflict'] = True
        record = self.data['components'].setdefault(component, {})
        record.update(status='running', updated=now())
        self.save()
        try:
            yield
        except BaseException as error:
            record.update(status='failed', updated=now())
            try:
                for name, tree in targets:
                    if self.inspect(name, tree) != previous[name]:
                        entries[name]['conflict'] = 'A failed operation left changes requiring review.'
                if service_probe and service_probe() != service['original']:
                    service['conflict'] = True
                self.save()
            except Exception as journal_error:
                error.add_note(f'Could not update the installation journal: {journal_error}')
            raise
        else:
            for name, tree in targets:
                if 'conflict' not in entries[name]:
                    entries[name]['installed'] = self.inspect(name, tree)
            if service_probe and not service.get('conflict'):
                service['installed'] = service_probe()
            if record['status']=='running':
                record['status']='applied'
            record['updated']=now()
            self.save()

    def restore_file(self, name, record):
        protected = ('/etc/default/keyboard', '/usr/local/bin/rpi-keyboard', '/etc/passwd',
                     '/etc/shadow', '/etc/group', '/etc/gshadow', '/etc/sudoers', '/etc/sudoers.d',
                     '/var/lib/rpi-images', '/home', '/root')
        if any(Path(name).is_relative_to(path) for path in protected):
            raise ValueError(f'Lifecycle restoration excludes {name}')
        path = self.trusted_parents(name)
        if self.snapshot(name) != record['installed']:
            raise ValueError(f'Configuration drift: {name}')
        original = record['original']
        if original == ABSENT:
            path.unlink()
            sync_directory(path.parent)
        elif original['kind'] == 'file':
            digest = original['sha256']
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('Invalid original backup identifier')
            secure_directory(self.directory/'original')
            content = private_read(self.directory/'original'/digest)
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError(f'Original backup failed validation: {name}')
            atomic_write(path, content, original['mode'], (original['uid'],original['gid']))
        elif original['kind'] == 'symlink':
            temp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}')
            try:
                temp.symlink_to(original['target'])
                os.lchown(temp, original['uid'], original['gid'])
                os.replace(temp, path)
                sync_directory(path.parent)
            finally:
                temp.unlink(missing_ok=True)
        else:
            raise ValueError(UNKNOWN)
        record['installed'] = self.snapshot(name)
