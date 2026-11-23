"""Manage only LXTerminal's FI/SE zoom shortcuts, as the desktop account."""

import argparse
import os
from pathlib import Path
import re
import stat
import tempfile

ZOOM = {'zoom_in_accel':'<Primary>plus','zoom_out_accel':'<Primary>minus',
        'zoom_reset_accel':'<Primary>0'}
LEGACY_ZOOM = {**ZOOM, 'zoom_reset_accel':'<Primary>period'}
BEGIN = '# rpi-images: FI/SE LXTerminal zoom begin'
END = '# rpi-images: FI/SE LXTerminal zoom end'
VERSION = '# rpi-images: LXTerminal zoom bindings v2'
ORIGINAL = '# rpi-images: original '
ABSENT = '# rpi-images: originally absent '
NEW_SECTION = '# rpi-images: originally absent shortcut section'
NEW_FILE = '# rpi-images: originally absent configuration file'
SECTION = re.compile(r'^\s*\[([^]]+)\]\s*$')
ASSIGN = re.compile(r'^\s*(' + '|'.join(ZOOM) + r')\s*=(.*)$')


def edit(text, restore=False, missing=False):
    lines = text.splitlines(keepends=True)
    headers = [(index, match[1]) for index,line in enumerate(lines) if (match:=SECTION.fullmatch(line))]
    matches = [(i, headers[n+1][0] if n+1<len(headers) else len(lines))
               for n,(i,name) in enumerate(headers) if name=='shortcut']
    if len(matches)>1:
        raise ValueError('Multiple [shortcut] sections require manual review.')
    starts = [i for i,line in enumerate(lines) if line.rstrip('\r\n')==BEGIN]
    ends = [i for i,line in enumerate(lines) if line.rstrip('\r\n')==END]
    if starts or ends:
        if not (len(starts)==len(ends)==len(matches)==1 and matches[0][0]<starts[0]<ends[0]<matches[0][1]):
            raise ValueError('LXTerminal management markers were changed; settings preserved.')
        start, end = starts[0], ends[0]
        header, limit = matches[0]
        body = [line.rstrip('\r\n') for line in lines[start+1:end]]
        current = VERSION in body
        expected = ZOOM if current else LEGACY_ZOOM
        active = [(i,found[1],found[2]) for i in range(header+1,limit)
                  if (found:=ASSIGN.fullmatch(lines[i].rstrip('\r\n')))]
        if len(active)!=len(ZOOM) or any(not (start<i<end) or expected[key]!=value for i,key,value in active) or set(k for _,k,_ in active)!=ZOOM.keys():
            raise ValueError('Managed LXTerminal zoom shortcuts were customized; settings preserved.')
        backup = {i:line[len(ORIGINAL):] for i,line in enumerate(lines[header+1:limit], header+1)
                  if line.startswith(ORIGINAL) and ASSIGN.fullmatch(line[len(ORIGINAL):].rstrip('\r\n'))}
        absent = {line.rstrip('\r\n')[len(ABSENT):] for line in lines[start+1:end] if line.startswith(ABSENT)} & ZOOM.keys()
        present = {ASSIGN.fullmatch(line.rstrip('\r\n'))[1] for line in backup.values()}
        if present & absent or present | absent != ZOOM.keys():
            raise ValueError('Original LXTerminal shortcut records are incomplete; settings preserved.')
        if not restore:
            if current:
                return text, False
            reset = next(i for i,key,_ in active if key=='zoom_reset_accel')
            line = lines[reset].rstrip('\r\n')
            lines[reset] = line.removesuffix(LEGACY_ZOOM['zoom_reset_accel'])+ZOOM['zoom_reset_accel']+lines[reset][len(line):]
            newline = '\r\n' if lines[start].endswith('\r\n') else '\n'
            lines.insert(start+1,VERSION+newline)
            return ''.join(lines), False
        flags = set(body)
        own_comments = {NEW_SECTION, NEW_FILE, VERSION, *(ABSENT+key for key in ZOOM)}
        removed = {start, end, *(i for i,_,_ in active)}
        removed.update(i for i in range(start+1,end) if lines[i].rstrip('\r\n') in own_comments)
        if NEW_SECTION in flags and all(i in removed for i in range(header+1,limit)):
            removed.add(header)
        result = [backup.get(i,line) for i,line in enumerate(lines) if i not in removed]
        return ''.join(result), NEW_FILE in flags and not result
    if restore:
        if any(line.startswith((ORIGINAL,ABSENT)) for line in lines):
            raise ValueError('LXTerminal management markers are missing; settings preserved.')
        return text, False
    if any(line.startswith((ORIGINAL,ABSENT)) for line in lines):
        raise ValueError('LXTerminal management markers are missing; settings preserved.')
    newline = '\r\n' if '\r\n' in text else '\n'
    block = [BEGIN,VERSION]
    if matches:
        header, limit = matches[0]
        present = set()
        for i in range(header+1,limit):
            if found:=ASSIGN.fullmatch(lines[i].rstrip('\r\n')):
                present.add(found[1])
                lines[i] = ORIGINAL+lines[i]
    else:
        if lines and not lines[-1].endswith(('\r','\n')):
            lines[-1] += newline
        header = len(lines)
        lines.append('[shortcut]'+newline)
        present = set()
        block.append(NEW_SECTION)
        if missing:
            block.append(NEW_FILE)
    if not lines[header].endswith(('\r','\n')):
        lines[header] += newline
    block.extend(ABSENT+k for k in ZOOM if k not in present)
    block.extend(f'{key}={value}' for key,value in ZOOM.items())
    lines[header+1:header+1] = [line+newline for line in [*block,END]]
    return ''.join(lines), False


def selected(home, terminal=Path('/usr/bin/lxterminal'), default=Path('/usr/bin/x-terminal-emulator')):
    if not terminal.is_file() or not os.access(terminal, os.X_OK):
        return False
    preference = home/'.config/xdg-terminals.list'
    if preference.is_file():
        first = next((line.strip() for line in preference.read_text().splitlines()
                      if line.strip() and not line.lstrip().startswith('#')), '')
        if first:
            return first in ('lxterminal.desktop','org.lxde.LXTerminal.desktop')
    return default.resolve()==terminal.resolve()


def owned(info, mode):
    if not mode(info.st_mode) or info.st_uid!=os.geteuid():
        raise ValueError('LXTerminal config path must be regular and owned by the desktop user.')


def identity(info):
    return (info.st_dev,info.st_ino,info.st_ctime_ns) if info is not None else None


def configure(home, layout, restore=False, preview=False, tracked=False):
    if not restore and (layout not in ('fi','se') or not selected(home)):
        return 'skipped'
    path = home/'.config/lxterminal/lxterminal.conf'
    for parent in reversed([p for p in path.parents if p.is_relative_to(home)]):
        try:
            owned(parent.lstat(), stat.S_ISDIR)
        except FileNotFoundError:
            if tracked:
                raise ValueError('Tracked LXTerminal configuration is missing; settings preserved.')
            if restore:
                return 'unchanged'
            if not preview:
                parent.mkdir(mode=0o700)
    try:
        with os.fdopen(os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK), 'rb') as file:
            info = os.fstat(file.fileno())
            owned(info, stat.S_ISREG)
            contents = file.read(1024*1024+1)
            if len(contents)>1024*1024 or os.fstat(file.fileno()).st_ctime_ns!=info.st_ctime_ns:
                raise ValueError('LXTerminal configuration is too large or changed while reading.')
    except FileNotFoundError:
        info, contents = None, b''
    text = contents.decode('utf-8', errors='surrogateescape')
    if tracked and BEGIN not in text.splitlines():
        raise ValueError('Tracked LXTerminal markers are missing; settings preserved.')
    revised, remove = edit(text, restore=restore, missing=info is None)
    if revised==text:
        return 'managed' if not restore and BEGIN in text else 'unchanged'
    if preview:
        return 'changed'

    def check_unchanged():
        try:
            current = path.lstat()
        except FileNotFoundError:
            current = None
        if identity(current)!=identity(info):
            raise ValueError('LXTerminal configuration changed during maintenance; settings preserved.')

    if remove:
        check_unchanged()
        path.unlink()
    else:
        fd, temp = tempfile.mkstemp(prefix='.lxterminal-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as file:
                file.write(revised.encode('utf-8',errors='surrogateescape'))
                if info:
                    os.fchown(file.fileno(), -1, info.st_gid)
                    os.fchmod(file.fileno(), stat.S_IMODE(info.st_mode))
                file.flush()
                os.fsync(file.fileno())
            check_unchanged()
            os.replace(temp, path)
        finally:
            Path(temp).unlink(missing_ok=True)
    return 'changed'


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--layout')
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--tracked', action='store_true')
    args = parser.parse_args()
    try:
        if os.geteuid()==0 or not args.home.is_absolute():
            raise ValueError('LXTerminal configuration requires the intended normal user.')
        print(configure(args.home,args.layout,args.restore,args.plan,args.tracked))
    except (OSError,ValueError) as error:
        parser.exit(1, f'{error}\n')
