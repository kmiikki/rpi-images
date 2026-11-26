"""Read APT prerequisites and the Raspberry Pi Wolfram desktop entries."""

import argparse
from dataclasses import dataclass
from fractions import Fraction
from math import ceil
from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess
import sys

PACKAGE = 'wolfram-engine'
LICENSE = 'https://www.wolfram.com/legal/agreements/wolfram-mathematica-raspberry-pi/'
LOCAL = '/usr/local/share/applications'
VENDOR = ('/usr/share/raspi-ui-overrides/applications', '/usr/share/applications')
COMMANDS = {'mathematica': 'gui', 'wolfram': 'cli', 'wolframscript': 'script'}
APT_CACHE = ('apt-cache', '-o', 'Dir::Cache::pkgcache=', '-o', 'Dir::Cache::srcpkgcache=')


@dataclass(frozen=True)
class Candidate:
    version: str
    download: int
    installed: int


def candidate(host, options=()):
    policy = host.probe(['env', 'LC_ALL=C', *APT_CACHE, *options, 'policy', PACKAGE])
    match = re.search(r'^[ \t]*Candidate:[ \t]+(\S+)[ \t]*$', policy.stdout, re.M)
    if policy.returncode or not match or match[1] == '(none)':
        return None
    return package_metadata(host, match[1], options)


def package_metadata(host, version, options=()):
    package = host.probe(['env', 'LC_ALL=C', *APT_CACHE, *options, 'show', f'{PACKAGE}={version}'])
    if package.returncode:
        return None
    for paragraph in package.stdout.split('\n\n'):
        fields = dict(line.split(':', 1) for line in paragraph.splitlines()
                      if line and line[0].isalpha() and ':' in line)
        if fields.get('Version', '').strip() != version:
            continue
        download = fields.get('Size', '').strip()
        installed = fields.get('Installed-Size', '').strip()
        if re.fullmatch(r'[0-9]+', download) and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', installed):
            # Raspberry Pi's Wolfram package advertises fractional KiB.
            unpacked = ceil(Fraction(installed) * 1024)
            if int(download) and unpacked:
                return Candidate(version, int(download), unpacked)
    return None


def disk_requirements(host, package):
    """Check download and full unpack sizes where APT caches and dpkg unpacks them."""
    result = host.probe(['apt-config', 'shell', 'ARCHIVES', 'Dir::Cache::archives/d'])
    args = shlex.split(result.stdout)
    if result.returncode or len(args) != 1 or not args[0].startswith('ARCHIVES=/'):
        raise ValueError('Cannot determine the APT archive directory')
    volumes = {}
    for path, size, kind in ((Path(args[0].split('=', 1)[1]), package.download, 'download'),
                             (Path('/opt'), package.installed, 'installed'),
                             (Path('/usr'), package.installed, 'installed')):
        while not path.exists():
            path = path.parent
        device = path.stat().st_dev
        if device not in volumes:
            volumes[device] = (shutil.disk_usage(path).free, path, {})
        volumes[device][2][kind] = size
    # Conservatively allow the full package on each distinct installation filesystem.
    return [(free, sum(sizes.values()), path) for free, path, sizes in volumes.values()]


def show_preflight(host, package, *, strict=False):
    print('  Wolfram license           The Pi bundle is limited to personal or educational use and excludes commercial use.')
    print('                            Installation signifies acceptance. Shared institutional use requires licensing review.')
    print(f'  Wolfram terms             {LICENSE}')
    if package is None:
        print('  Wolfram disk              APT candidate metadata unavailable. Aalto sample: about 2.17 GB download and 5.44 GB installed.')
        print('                            APT metadata and free space must be checked before installation.')
        if strict:
            raise ValueError('No downloadable Wolfram APT candidate with size metadata')
        return
    print(f'  Wolfram APT candidate     {package.version}')
    print(f'  Wolfram disk              {package.download/1e9:.2f} GB download, {package.installed/1e9:.2f} GB installed (package only)')
    insufficient = []
    try:
        for free, needed, path in disk_requirements(host, package):
            if needed:
                print(f'    {path}: {free/1e9:.2f} GB available, {needed/1e9:.2f} GB required for Wolfram')
            if free < needed:
                insufficient.append(str(path))
    except (OSError, ValueError) as exc:
        if strict:
            raise
        print(f'    Free space could not be determined: {exc}')
    if insufficient:
        message = 'Insufficient disk space for Wolfram on ' + ', '.join(insufficient)
        print('    ' + message)
        if strict:
            raise ValueError(message)


def entry_fields(path):
    section = path.read_text(encoding='utf-8-sig').partition('[Desktop Entry]')[2]
    lines = []
    for line in section.splitlines():
        if line.startswith('['):
            break
        if '=' in line and not line.startswith('#'):
            lines.append(line.split('=', 1))
    return dict(lines)


def vendor_command(value):
    args = shlex.split(value)
    if not args:
        return None, ''
    name = Path(args[0]).name.lower()
    if name in COMMANDS:
        return COMMANDS[name], args[0]
    # Some vendor entries wrap wolfram in a terminal, including one quoted command.
    for index, word in enumerate(args):
        command = ''
        if word.startswith('--command='):
            command = word.partition('=')[2]
        elif word in ('-e', '--command', '-x') and index+1 < len(args):
            command = args[index+1]
        inner = shlex.split(command)
        if inner and Path(inner[0]).name in ('wolfram', 'wolframscript'):
            return COMMANDS[Path(inner[0]).name], inner[0]
    return None, ''


def definitions(host, store):
    listing = host.probe(['dpkg-query', '-L', PACKAGE])
    if listing.returncode:
        raise ValueError('Cannot list desktop entries from the installed Wolfram package')
    sources = {}
    for line in listing.stdout.splitlines():
        path = Path(line)
        if str(path.parent) in VENDOR and path.suffix == '.desktop':
            sources[path.name] = store.path(line)
    # Raspberry Pi's desktop can replace an ID or ship an additional launcher.
    for override in sorted(store.path(VENDOR[0]).glob('*.desktop')):
        if override.name in sources:
            sources[override.name] = override
        elif override.name.lower().startswith(('wolfram','mathematica')):
            logical = f'{VENDOR[0]}/{override.name}'
            role, _ = vendor_command(entry_fields(override).get('Exec', ''))
            if role and host.probe(['dpkg-query', '-S', logical]).returncode == 0:
                sources[override.name] = override
    entries = {'gui': [], 'cli': []}
    result = {}
    for name, path in sorted(sources.items()):
        fields = entry_fields(path)
        role, command = vendor_command(fields.get('Exec', ''))
        if role == 'script':
            result[f'{LOCAL}/{name}'] = desktop_content(dict(Type='Application', Name='WolframScript', Hidden='true'))
        elif role:
            entries[role].append((name, fields, command))
        elif fields.get('NoDisplay', 'false').lower() != 'true' and fields.get('Hidden', 'false').lower() != 'true':
            raise ValueError(f'Unrecognized visible Wolfram desktop entry: {name}')
    titles = {'gui': 'Wolfram Mathematica (GUI)', 'cli': 'Wolfram Language (CLI)'}
    comments = {'gui': 'Open the graphical Mathematica notebook interface',
                'cli': 'Start the interactive Wolfram Language kernel in a terminal'}
    commands = {}
    for role, matches in entries.items():
        if not matches:
            raise ValueError(f'No recognizable Wolfram {role.upper()} desktop entry in the installed package')
        # Prefer a visible vendor definition when several entries invoke the same application.
        matches.sort(key=lambda entry: (entry[1].get('NoDisplay') == 'true' or entry[1].get('Hidden') == 'true',
                                         not bool(entry[1].get('Icon')), entry[0]))
        name, fields, command = matches[0]
        if not fields.get('Icon') or not resolve_command(command, store):
            raise ValueError(f'Missing vendor icon or executable in Wolfram desktop entry: {name}')
        commands[role] = command
        if role == 'cli':
            # Use the vendor kernel target and let the desktop's terminal handler run it.
            fields['Exec'] = '"' + command + '"' if ' ' in command else command
        categories = fields.get('Categories','').split(';')
        main_category = 'Science' if 'Science' in categories and 'Education' not in categories else 'Education'
        values = dict(Type='Application', Name=titles[role], Comment=comments[role],
                      Exec=fields['Exec'], Icon=fields['Icon'], Terminal='true' if role == 'cli' else 'false',
                      Categories=f'{main_category};Math;')
        for key in ('MimeType', 'StartupNotify', 'StartupWMClass'):
            if fields.get(key):
                values[key] = fields[key]
        result[f'{LOCAL}/{name}'] = desktop_content(values)
        for duplicate, _, _ in matches[1:]:
            result[f'{LOCAL}/{duplicate}'] = desktop_content(dict(Type='Application', Name=titles[role],
                                                                Hidden='true'))
    return result, commands


def desktop_content(fields):
    return ('[Desktop Entry]\n' + ''.join(f'{key}={value}\n' for key, value in fields.items())).encode()


def resolve_command(command, store):
    path = Path(command)
    if path.is_absolute():
        target = store.path(command)
        return str(target) if target.is_file() and os.access(target, os.X_OK) else None
    if path.name != command:
        return None
    paths = os.pathsep.join(str(store.path(folder)) for folder in ('/usr/bin', '/usr/local/bin'))
    return shutil.which(command, path=paths)


def verify(host, store, *, smoke=False):
    expected, commands = definitions(host, store)
    print(f"PASS Wolfram Engine CLI executable ({commands['cli']})")
    script = resolve_command('wolframscript', store)
    if script:
        print('PASS WolframScript executable (wolframscript)')
    else:
        print('FAIL WolframScript executable missing')
    print(f"PASS Mathematica GUI executable ({commands['gui']})")
    errors = []
    for path, content in expected.items():
        file = store.path(path)
        if (file.is_symlink() or not file.is_file() or file.stat().st_mode & 0o777 != 0o644
                or file.read_bytes() != content):
            errors.append(path)
        elif shutil.which('desktop-file-validate'):
            host.run(['desktop-file-validate', file], capture=True)
    for path, entry in (store.data or {}).get('paths', {}).items():
        if entry['component']=='wolfram-launchers' and path not in expected and store.inspect(path)!=entry['original']:
            errors.append(path)
    if errors:
        raise ValueError('Wolfram desktop entries missing or different: ' + ', '.join(errors))
    print('PASS Wolfram Mathematica (GUI) and Wolfram Language (CLI) desktop definitions')
    if not script:
        raise ValueError('WolframScript executable missing')
    if smoke:
        kernel = resolve_command(commands['cli'], store)
        for label, command in (('Wolfram Engine CLI', [kernel, '-noinit', '-noprompt', '-run', 'Print[2+2]; Exit[]']),
                               ('WolframScript', [script, '-code', '2+2'])):
            try:
                result = host.probe(['timeout', '60s', *command])
                passed = result.returncode == 0 and result.stdout.strip() == '4'
            except (OSError, subprocess.SubprocessError):
                passed = False
            print(f'PASS {label} calculation (2+2)' if passed else
                  f'LIMITED {label} calculation did not return 4; check licensing and run it manually')
    else:
        print('WolframScript calculation: not run by this read-only verification')
    print('PENDING MANUAL ACCEPTANCE: launch both menu entries, evaluate the GUI notebook plot and CLI expression.')


def standalone():
    from setup_rpi import Host, ask
    import lifecycle

    parser = argparse.ArgumentParser(description='Install optional Wolfram Engine on Raspberry Pi OS Trixie')
    parser.add_argument('-y', '--yes', action='store_true', help='approve the displayed package installation')
    parser.add_argument('-n', '--dry-run', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('--accept-wolfram-license', action='store_true',
                        help='confirm that you reviewed and are authorized to accept the Wolfram terms')
    args = parser.parse_args()
    host = Host()
    state = host.snapshot()
    installed = state['wolfram']['engine_installed']
    if not installed and state['wolfram']['cli']:
        print('DEFERRED existing Wolfram outside the APT package; review its desktop entries locally.')
        return 0
    reviewed = lifecycle.wolfram.candidate(host) if not installed else None
    if installed:
        print('Keep Wolfram Engine and reconcile the vendor GUI and CLI desktop entries.')
    else:
        show_preflight(host, reviewed)
    if args.verbose:
        print(f"Host: {state['model']}, {state['os']}, {state['ram_mib']} MiB RAM")
    if (state['ram_mib'] or 0) < 2000:
        print('Wolfram Engine may be impractical on a low-memory system.')
    if args.dry_run:
        print('PLAN ONLY: package and desktop files unchanged.')
        return 0
    if (state['codename'] != 'trixie' or state['architecture'] not in ('aarch64', 'arm64') or
            not state['model'].startswith(('Raspberry Pi 4 ', 'Raspberry Pi 5 ')) or
            state['os_id'] not in ('debian', 'raspbian')):
        raise ValueError('Wolfram installation requires Raspberry Pi 4/5 and Raspberry Pi OS Trixie 64-bit')
    if os.geteuid() != 0:
        raise ValueError('Run the optional installer through sudo.')
    confirm = lambda: sys.stdin.isatty() and ask('Install Wolfram under the license terms shown above? y/N', 'n').lower() in ('y','yes')
    if reviewed and not args.yes:
        print('Approving this installation authorizes the displayed package under the linked Wolfram terms.')
    if not args.yes and not (sys.stdin.isatty() and ask('Apply the Wolfram plan? y/N', 'n').lower() in ('y','yes')):
        return 0
    if args.yes and not args.accept_wolfram_license:
        reviewed = None
    with host.installation(state):
        store = host.records
        previous = lifecycle.apt_inventory(host)
        with store.stage('wolfram'):
            try:
                print(lifecycle.install_wolfram(host, store, installed=installed, reviewed=reviewed, confirm=confirm))
            finally:
                store.data['apt_current'] = lifecycle.apt_inventory(host)
                lifecycle.remember_wolfram_install(store, previous)


if __name__ == '__main__':
    try:
        sys.exit(standalone())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f'Error: {exc}')
