"""Management commands for the unified Raspberry Pi installer."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

from installation_state import ABSENT, UNKNOWN, Store, now
import locale_setup
import os_upgrade
from os_upgrade import boot_id
import wlan
import wolfram
import preboot

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
LABELS = {
    'conda': 'Miniforge', 'lab314': 'Scientific Python', 'spyder': 'Spyder IDE',
    'hardware': 'Raspberry Pi hardware Python', 'activation': 'Environment activation',
    'envrun': 'Environment runner', 'share': 'rpi-share', 'wolfram': 'Wolfram Engine',
    'imaging': 'Scientific Imaging applications', 'profile': 'System settings',
    'spyder-ide': 'Separate Spyder environment',
    'terminal-shortcuts': 'LXTerminal FI/SE zoom shortcuts',
    'chromium': 'Chromium browser policy',
    'locales': 'Regional locales',
}
DEFAULT_PATHS = {
    'conda': '/opt/conda', 'lab314': '/opt/lab314', 'hardware': '/opt/rpi',
    'spyder': '/opt/lab314/bin/spyder', 'activation': '/etc/profile.d/lab314-bash.sh',
    'envrun': '/usr/local/bin/envrun', 'share': '/usr/local/bin/rpi-share',
}
NTP_FILE = '/etc/systemd/timesyncd.conf.d/60-rpi-scientific.conf'
FIRMWARE_PATHS = ('/boot/firmware/config.txt', '/etc/modules-load.d/rpi-preboot-i2c.conf')
SPYDER_LAUNCHER = (
    (BASE/'bin/rpi-lab314-spyder', '/usr/local/bin/rpi-lab314-spyder', '755'),
    (HERE/'spyder_runtime.py', '/usr/local/lib/rpi-images/spyder_runtime.py', '644'),
    (BASE/'config/lab314/spyder.desktop', '/usr/local/share/applications/rpi-lab314-spyder.desktop', '644'),
    # The local XDG entry takes precedence over Conda's unmanaged lab314 menu entry.
    (BASE/'config/lab314/spyder-conda-compat.desktop',
     '/usr/local/share/applications/conda-spyder_spyder-6-lab314.desktop', '644'),
    (BASE/'bin/lab314-spyder-command', '/usr/local/lib/rpi-images/lab314-bin/spyder', '755'),
    (BASE/'config/lab314/spyder-activate.sh', '/opt/lab314/etc/conda/activate.d/rpi-images-spyder.sh', '644'),
    (BASE/'config/lab314/spyder-deactivate.sh', '/opt/lab314/etc/conda/deactivate.d/rpi-images-spyder.sh', '644'),
)
APT_CAMERA = ('python3-opencv', 'python3-picamera2', 'python3-libcamera', 'python3-serial')
CONDA_PATH = '/etc/profile.d/conda-path.sh'
CONDA_PATH_CONTENT = b'# Conda is available through /usr/local/bin.\n'
SCIENTIFIC_BROWSER = '/usr/local/bin/rpi-scientific-browser'
HARDWARE_BRIDGE = f'/opt/rpi/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages/aalto-system-dist-packages.pth'
PACKAGE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*')
CHROMIUM_FILES = (
    (BASE/'config/chromium/99-rpi-images-shared', '/etc/chromium.d/99-rpi-images-shared'),
    (BASE/'config/chromium/99-rpi-images-shared.json', '/etc/chromium/policies/managed/99-rpi-images-shared.json'),
)


def apt_inventory(host):
    result = host.probe(['dpkg-query', '-W', '-f=${db:Status-Abbrev}\t${binary:Package}\t${Version}\n'])
    if result.returncode:
        raise ValueError('Unable to record installed APT packages')
    return {fields[1]: fields[2] for line in result.stdout.splitlines()
            if len(fields := line.split('\t')) == 3 and fields[0].startswith('ii')}


def services(host):
    return {
        'ssh_enabled': host.probe(['systemctl','is-enabled','ssh']).stdout.strip(),
        'ssh_active': host.probe(['systemctl','is-active','ssh']).stdout.strip(),
        'ntp': host.probe(['timedatectl','show','-p','NTP','--value']).stdout.strip(),
        'timesync': host.probe(['systemctl','is-active','systemd-timesyncd']).stdout.strip(),
    }


def ssh_status(host):
    state = {}
    for unit, activity, startup in (('ssh.service', 'SSH service', 'SSH startup'),
                                    ('ssh.socket', 'SSH socket', 'SSH socket startup')):
        for query, field in (('is-active', activity), ('is-enabled', startup)):
            try:
                output = host.probe(['systemctl', query, unit]).stdout.strip()
            except OSError:
                output = ''
            state[field] = output or 'unknown'
    return state


def report_ssh(policy, state, indent=''):
    print(f'{indent}{"SSH policy":<24} {policy}')
    for label, value in state.items():
        print(f'{indent}{label:<24} {value}')


def apply_locales(store, host, proposal):
    current=locale_setup.plan(host,store)
    if current != proposal:
        raise ValueError('Locale state changed after review. Review a new plan.')
    # The locale archive and configuration are shared with the OS and users.
    # Keep the requested names for repair without claiming ownership of the file.
    store.data['locales']=list(proposal.locales)
    with store.stage('locales'):
        try:
            locale_setup.apply(host,store,proposal)
        finally:
            if hasattr(host,'refresh_locale_environment'):
                host.refresh_locale_environment()
        if proposal.unavailable or proposal.fallback:
            store.data['components']['locales']['status']='deferred'
            return 'LIMITED some locale requests remain unavailable; see the plan above.'
    if proposal.generate:
        return 'Generated and verified '+', '.join(proposal.generate)
    if proposal.enable:
        return 'Enabled for future generation: '+', '.join(row.split()[0] for row in proposal.enable)
    return 'Verified '+(', '.join(proposal.locales) or 'the existing locale inventory')


def reconcile_file(store, name, data, mode, *, edit=None):
    """Install a definition and retain a recoverable copy of the immediate previous file."""
    path=store.path(name)
    receipt=store.data['paths'].get(str(name),{})
    before=preboot.optional_file(path) if not path.is_symlink() else None
    if path.is_symlink():
        store.reconciled[str(name)]='preserved'
        print(f'PRESERVED local configuration (symlink): {name}')
        return 'preserved'
    if before and not edit and before[0]==data and before[1].st_mode & 0o7777==mode:
        return 'unchanged'
    if edit:
        data=edit(before[0] if before else b'')
        if data is None:
            store.reconciled[str(name)]='preserved'
            print(f'PRESERVED local configuration (unrecognized managed block): {name}')
            return 'preserved'
        if before and data==before[0]:
            return 'unchanged'
    current=store.snapshot(name,backup=bool(before))
    expected=receipt.get('installed')
    if before and not edit and (current!=expected or receipt.get('conflict')):
        store.reconciled[str(name)]='preserved'
        print(f'PRESERVED local configuration (differs from last managed version): {name}')
        return 'preserved'
    store.ensure_parents(name)
    owner=(before[1].st_uid,before[1].st_gid) if before else (os.geteuid(),os.getegid())
    preboot.replace_file(path,before,data,mode,*owner)
    store.reconciled[str(name)]='updated' if before else 'added'
    if before:
        print(f'UPDATED {name}; backup: {store.directory/"original"/current["sha256"]}')
    else:
        print(f'INSTALLED {name}')
    # A previously managed file may have been deleted; restore its receipt for future updates.
    if not before and receipt.get('original')==ABSENT:
        receipt.pop('conflict',None)
    return 'updated'


def reconcile_definition(store, source, destination, mode):
    return reconcile_file(store,destination,Path(source).read_bytes(),int(mode,8))


def scientific_browser_hook(prefix):
    return str(prefix/'lib/python3.14/site-packages/rpi-scientific-browser.pth')


def reconcile_scientific_browser(store, host, prefix):
    host.run(['test','-x','/usr/bin/firefox'])
    targets=(
        (BASE/'bin/rpi-scientific-browser',SCIENTIFIC_BROWSER,'755'),
        (BASE/'config/lab314/rpi-scientific-browser.pth',scientific_browser_hook(prefix),'644'),
    )
    for source,destination,mode in targets:
        outcome=reconcile_definition(store,source,destination,mode)
        if outcome=='preserved':
            raise ValueError(f'Local scientific browser definition kept for review: {destination}')


def install_missing_apt(host, packages, *, refresh=True):
    installed={name.split(':',1)[0] for name in apt_inventory(host)}
    missing=sorted(name for name in set(packages) if name.split('=',1)[0] not in installed)
    if not missing:
        return
    options=['--no-upgrade','-o','DPkg::Options::=--force-confold']
    with command_environment(host,LC_ALL='C'):
        if refresh:
            host.run(['apt-get','update'])
        plan=host.run(['apt-get','--simulate','install',*options,*missing],capture=True).stdout
        for line in plan.splitlines():
            match=re.match(r'^(?:Inst|Remv|Purg) (\S+)',line)
            if match and (not line.startswith('Inst ') or match[1].split(':',1)[0] in installed):
                raise ValueError(f'Adding the missing APT packages would change installed packages: {line}. Review through --manage.')
        host.run(['apt-get','install','-y','--no-remove',*options,*missing])
    print('INSTALLED missing APT selections: '+', '.join(missing))


def reconcile_wolfram_launchers(store, host):
    expected, _ = wolfram.definitions(host, store)
    stale = {name: entry for name, entry in store.data['paths'].items()
             if entry['component'] == 'wolfram-launchers' and name not in expected}
    with store.stage('wolfram-launchers', [(path, False) for path in expected], repair_missing=True):
        for path, content in expected.items():
            if reconcile_file(store, path, content, 0o644) == 'preserved':
                raise ValueError(f'Local Wolfram desktop entry preserved for review: {path}')
        for path, entry in stale.items():
            if store.inspect(path) == entry['original']:
                continue
            if entry.get('conflict') or entry['original'] != ABSENT:
                raise ValueError(f'Old Wolfram desktop entry requires review: {path}')
            store.restore_file(path, entry)
            store.save()


def install_wolfram(host, store, *, installed, reviewed, confirm):
    if not installed:
        host.run(['apt-get','update'])
        package=wolfram.candidate(host)
        wolfram.show_preflight(host,package,strict=True)
        if package!=reviewed and not confirm():
            return 'DEFERRED Wolfram APT candidate requires approval; rerun setup or choose --no-wolfram.'
        install_missing_apt(host,[f'{wolfram.PACKAGE}={package.version}'],refresh=False)
    reconcile_wolfram_launchers(store,host)
    wolfram.verify(host,store,smoke=not installed)
    store.data.pop('pending_wolfram',None)
    return 'Engine CLI, WolframScript, GUI executable and desktop entries checked; menu launches pending.'


def selected_chromium(selection):
    mode = selection.get('chromium_policy') or ('shared' if selection.get('profile')=='AALTO' else 'personal')
    if mode not in ('personal','shared'):
        raise ValueError('Invalid saved Chromium policy. Review the installation record.')
    return mode


def chromium_description(mode):
    return {'personal': 'personal (regular Chromium profile and keyring)',
            'shared': 'shared (regular profile, keyring-free with password saving disabled)'}[mode]


def chromium_personal_restore(store):
    """Review both overrides before restoring anything."""
    paths = (store.data or {}).get('paths', {})
    restore = []
    for _, path in CHROMIUM_FILES:
        current = store.inspect(path)
        if current == ABSENT:
            continue
        record = paths.get(path, {})
        if (record.get('component') != 'chromium' or record.get('original') != ABSENT
                or record.get('conflict') or record.get('installed') != current):
            raise ValueError(f'Local Chromium override preserved for review: {path}')
        restore.append((path, record))
    return restore


def chromium_policy(store, *, mode=None, apply=False):
    mode = mode or selected_chromium(store.data or {})
    if mode == 'personal':
        restore = chromium_personal_restore(store)
        if restore and not apply:
            raise ValueError('Chromium personal policy pending: use repair to restore the managed overrides.')
        for path, record in restore:
            store.restore_file(path, record)
            store.save()
        return f'Chromium policy verified: {chromium_description(mode)}.'
    launcher = store.path('/usr/bin/chromium')
    if not launcher.is_file():
        return 'DEFERRED: Chromium is not installed.'
    if b'/etc/chromium.d/' not in launcher.read_bytes():
        raise ValueError('Chromium package launcher no longer loads /etc/chromium.d; review the shared policy.')
    for directory in (wolfram.LOCAL, *wolfram.VENDOR):
        desktop = store.path(f'{directory}/chromium.desktop')
        if desktop.is_file():
            command = shlex.split(wolfram.entry_fields(desktop).get('Exec', ''))
            if not command or command[0] not in ('chromium', '/usr/bin/chromium'):
                raise ValueError(f'Chromium menu entry bypasses the package launcher: {desktop}')
            break
    else:
        raise ValueError('Chromium desktop entry is missing.')
    desired = json.loads(CHROMIUM_FILES[1][0].read_text())
    policy = store.path(CHROMIUM_FILES[1][1])
    for other in policy.parent.glob('*.json'):
        if other != policy:
            values = json.loads(other.read_text())
            if any(key in values and values[key] != value for key, value in desired.items()):
                raise ValueError(f'Conflicting Chromium policy requires review: {other}')
    for source, path in reversed(CHROMIUM_FILES):  # Install policy before enabling the browser flags.
        if apply and reconcile_definition(store, source, path, '644') == 'preserved':
            raise ValueError(f'Local Chromium configuration preserved for review: {path}')
        file = store.path(path)
        if (file.is_symlink() or not file.is_file() or file.stat().st_uid != os.geteuid()
                or file.stat().st_mode & 0o777 != 0o644 or file.read_bytes() != source.read_bytes()):
            raise ValueError(f'Chromium configuration missing or different: {path}')
    return ('Chromium package hook and shared policy verified. '
            'PENDING MANUAL ACCEPTANCE: start Chromium from the menu and terminal in a fresh session.')


def reconcile_system(store, host, model):
    packages={line.strip() for filename in ('common-apt.txt','rpi-apt.txt')
              for line in (HERE/'packages'/filename).read_text().splitlines()
              if line.strip() and not line.lstrip().startswith('#')}
    # Retain the old provider on Pi 4 installations that already use it.
    if not preboot.is_pi5_model(model) and 'python3-rpi.gpio' in apt_inventory(host):
        packages.discard('python3-rpi-lgpio')
    install_missing_apt(host,packages-{'spyder','python3-spyder-kernels'})
    for name in ('bin','bin-rpi','lib'):
        store.ensure_parents(f'/opt/sci/{name}/.directory')
    return reconcile_definition(store,HERE/'sci-path.sh','/etc/profile.d/sci-path.sh','644')


def reconcile_conda(store):
    reconcile_file(store,CONDA_PATH,CONDA_PATH_CONTENT,0o644)
    for tool in ('conda','mamba'):
        destination=f'/usr/local/bin/{tool}'
        target=f'/opt/conda/bin/{tool}'
        if not store.path(target).exists():
            raise ValueError(f'Missing installed Miniforge command: {target}')
        path=store.path(destination)
        if path.is_symlink() and os.readlink(path)==target:
            continue
        if path.exists() or path.is_symlink():
            store.reconciled[destination]='preserved'
            print(f'PRESERVED existing command: {destination}')
            continue
        store.ensure_parents(destination)
        path.symlink_to(target)
        store.reconciled[destination]='added'
        print(f'INSTALLED {destination}')
        receipt=store.data['paths'][destination]
        if receipt['original']==ABSENT:
            receipt.pop('conflict',None)


def reconcile_profile(store, host, plan):
    expected=f"[Time]\nNTP={plan['ntp']}\nFallbackNTP=time.cloudflare.com pool.ntp.org\n"
    ntp=reconcile_file(store,NTP_FILE,expected.encode(),0o644)
    current=services(host)
    previous=store.data['services']['profile']
    ssh=plan['ssh']
    desired={'enable':('enabled','active'), 'disable':('disabled','inactive')}
    current_ssh=(current['ssh_enabled'],current['ssh_active'])
    previous_ssh=tuple(previous.get('installed',{}).get(key) for key in ('ssh_enabled','ssh_active'))
    if ssh=='keep' or desired[ssh]==current_ssh:
        ssh='keep'
    elif previous_ssh!=(None,None) and current_ssh!=previous_ssh and not plan.get('explicit_ssh'):
        print('PRESERVED local SSH service settings.')
        ssh='keep'
    if ssh!='keep' and previous_ssh!=(None,None) and not plan['confirm_significant'](f'Change SSH service to {ssh}'):
        print('DEFERRED SSH service change.')
        ssh='keep'
    change_ntp=ntp=='updated' or (ntp=='unchanged' and 'installed' not in previous and not previous.get('conflict')
                                  and (current['ntp']!='yes' or current['timesync']!='active'))
    if change_ntp or ssh!='keep':
        if ssh=='enable':
            install_missing_apt(host,['openssh-server'])
        with command_environment(host, RPI_PROFILE_CONFIG_MANAGED='1',
                                 RPI_PROFILE_RESTART_NTP=str(int(change_ntp)), SSH_POLICY=ssh):
            host.run(['bash',HERE/'pre_profile.sh',plan['profile']])
    elif ntp=='unchanged':
        print('KEEP existing NTP and SSH configuration.')


@contextmanager
def command_environment(host, **variables):
    previous=host.env.copy()
    host.env.update(variables)
    try:
        yield
    finally:
        host.env.clear()
        host.env.update(previous)


def reconcile_accounts(store, host, plan, state, ensure_user):
    for name in [plan['primary'],*plan['additional']]:
        primary=name==plan['primary']
        if name not in state['accounts']:
            ensure_user(name,admin=True,passwordless=primary)
            continue
        groups=host.run(['id','-nG','--',name],capture=True).stdout.split()
        policy=f'/etc/sudoers.d/010_{name}-nopasswd'
        current=store.inspect(policy) if primary else ABSENT
        add_rule=False
        if primary and current==ABSENT:
            try:
                host.run(['sudo','-n','-u',name,'sudo','-kn','true'],capture=True)
            except subprocess.CalledProcessError:
                add_rule=True
        elif primary:
            expected=f'{name} ALL=(ALL) NOPASSWD: ALL\n'.encode()
            if current.get('sha256')!=hashlib.sha256(expected).hexdigest():
                print(f'PRESERVED existing sudo policy: {policy}')
        if 'sudo' not in groups or add_rule:
            if plan['confirm_significant'](f'Apply the selected administrator policy for {name}'):
                ensure_user(name,admin=True,passwordless=add_rule)
            else:
                print(f'DEFERRED administrator policy changes for {name}.')


def reconcile_shell(store, lab_prefix):
    if lab_prefix==Path('/opt/lab314'):
        helper='/etc/profile.d/lab314-bash.sh'
        reconcile_definition(store,HERE/'lab314-bash.sh',helper,'644')
        path='/etc/bash.bashrc'
        block=(HERE/'lab314-bashrc-block.sh').read_bytes()
        start=b'# >>> LAB314 BEGIN >>>'
        end=b'# <<< LAB314 END <<<'
        definition=hashlib.sha256(block).hexdigest()
        installed=store.data.get('lab314_bashrc_block')

        def edit(original):
            lines=original.splitlines(keepends=True)
            starts=[index for index,line in enumerate(lines) if line.rstrip(b'\r\n')==start]
            ends=[index for index,line in enumerate(lines) if line.rstrip(b'\r\n')==end]
            if not starts and not ends:
                updated=original+(b'' if not original or original.endswith(b'\n') else b'\n')+block
            elif len(starts)!=1 or len(ends)!=1 or starts[0]>=ends[0]:
                return None
            else:
                current=b''.join(lines[starts[0]:ends[0]+1])
                if current==block:
                    return original
                receipt=store.data['paths'][path]
                if (hashlib.sha256(current).hexdigest()!=installed
                        and (receipt.get('installed')!=store.snapshot(path) or receipt.get('conflict'))):
                    return None
                updated=b''.join(lines[:starts[0]])+block+b''.join(lines[ends[0]+1:])
            subprocess.run(['bash','-n'],input=updated,check=True)
            return updated

        bashrc=store.path(path)
        if not bashrc.is_file() or bashrc.is_symlink():
            raise ValueError(f'Missing regular system shell configuration: {bashrc}')
        if reconcile_file(store,path,b'',bashrc.stat().st_mode&0o777,edit=edit)!='preserved':
            store.data['lab314_bashrc_block']=definition
        legacy=CONDA_PATH
        if store.path(legacy).is_file() and not store.path(legacy).is_symlink():
            def fix_legacy(data):
                return (CONDA_PATH_CONTENT
                        if data.rstrip(b'\n')==b'export PATH=/opt/conda/bin:$PATH' else data)
            reconcile_file(store,legacy,b'',0o644,edit=fix_legacy)
    reconcile_definition(store,BASE/'bin/envrun','/usr/local/bin/envrun','755')


def target_paths(stage, a, plan, state):
    if stage == 'accounts':
        files = ['/etc/hosts','/etc/hostname'] if plan['hostname'] != state['hostname'] else []
        files += [f"/etc/sudoers.d/010_{plan['primary']}-nopasswd"]
    elif stage == 'profile':
        files = [NTP_FILE]
    elif stage == 'system':
        files = ['/etc/profile.d/sci-path.sh']
        if state['invoking_user']:
            files += [f"/etc/sudoers.d/010_{state['invoking_user']}-nopasswd"]
    elif stage == 'conda':
        files = ['/usr/local/bin/conda','/usr/local/bin/mamba',CONDA_PATH]
        return [('/opt/conda',True), *((name,False) for name in files)]
    elif stage == 'lab314':
        return [(str(a.lab_prefix),True),(scientific_browser_hook(a.lab_prefix),False),(SCIENTIFIC_BROWSER,False)]
    elif stage in ('spyder-kernel','spyder-add'):
        return [(str(a.lab_prefix),True)]
    elif stage == 'hardware':
        return [('/opt/rpi',True),(HARDWARE_BRIDGE,False)]
    elif stage == 'spyder-ide' and a.ide_prefix:
        return [(str(a.ide_prefix),True)]
    elif stage == 'spyder-desktop':
        files = [destination for _, destination, _ in SPYDER_LAUNCHER]
    elif stage == 'chromium':
        files = [destination for _, destination in CHROMIUM_FILES]
    elif stage == 'shell':
        files = ['/usr/local/bin/envrun']
        if a.lab_prefix == Path('/opt/lab314'):
            files += ['/etc/bash.bashrc','/etc/profile.d/lab314-bash.sh','/etc/profile.d/conda-path.sh']
    elif stage == 'share':
        files = share_paths(plan['share_prefix'])
    elif stage == 'imaging':
        files = [app_record(name) for name in a.imaging_app if PACKAGE.fullmatch(name)]
    else:
        files = []
    return [(name,False) for name in files]


@contextmanager
def spyder_prefix_receipt(store):
    prefix='/opt/lab314'
    entry=(store.data or {}).get('paths',{}).get(prefix) if store else None
    refresh=(entry and entry.get('tree') and not entry.get('conflict')
             and store.inspect(prefix,True)==entry.get('installed'))
    yield
    if refresh:
        entry['installed']=store.snapshot(prefix,True)
        store.save()


def install_spyder_launcher(host,store=None):
    results=[]
    with spyder_prefix_receipt(store):
        for source,destination,mode in SPYDER_LAUNCHER:
            if store:
                results.append(reconcile_definition(store,source,destination,mode))
            else:
                host.run(['install',f'-Dm{mode}',source,destination])
    return results


def spyder_pending():
    print('Spyder GUI startup: PENDING')
    print('Spyder IPython console: PENDING')
    print('Spyder graphical acceptance: PENDING (check as a desktop user)')


def terminal_target(state, user=None):
    user = user or state.get('invoking_user')
    account = state.get('accounts',{}).get(user)
    if account and account['uid']>0 and Path(account['home']).is_absolute():
        return {'name':user,'uid':account['uid'],'home':str(account['home'])}
    return None


def terminal_shortcuts(host, target, *, layout=None, restore=False, preview=False, tracked=False):
    command = ['runuser','-u',target['name'],'--','/usr/bin/python3','-IB',HERE/'lxterminal_zoom.py',
               '--home',target['home']]
    command += ['--restore'] if restore else ['--layout',layout]
    if preview:
        command.append('--plan')
    if tracked or restore:
        command.append('--tracked')
    try:
        return host.run(command,capture=True).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise ValueError((error.stderr or str(error)).strip()) from error


def apply_terminal_shortcuts(store,host,target,layout,*,preview=False):
    records = ((store.data or {}).get('terminal_shortcuts',{}) if store else {})
    tracked = records.get(target['name'])
    if tracked and any(tracked.get(key)!=value for key,value in target.items()):
        raise ValueError('Recorded LXTerminal owner or home changed; settings preserved.')
    proposed = terminal_shortcuts(host,target,layout=layout,preview=True,tracked=bool(tracked))
    if proposed not in ('managed','changed'):
        return 'DEFERRED: LXTerminal is not the selected installed terminal.'
    if preview:
        return f"LXTerminal shortcuts for {target['name']}: {proposed}."
    if store:
        store.data.setdefault('terminal_shortcuts',{})[target['name']]={**target,'layout':layout}
        store.save()
    if proposed=='changed':
        outcome=terminal_shortcuts(host,target,layout=layout,tracked=bool(tracked))
        if outcome not in ('changed','managed'):
            if store and not tracked:
                store.data['terminal_shortcuts'].pop(target['name'])
                store.save()
            return 'DEFERRED: LXTerminal selection changed before applying the plan.'
    return (f"Managed FI/SE LXTerminal zoom shortcuts for {target['name']}. "
            "Open a separate window with lxterminal --no-remote to load them now. "
            "Normal windows may reuse the running LXTerminal process until the next desktop login.")


def terminal_restoration(store,host):
    records = store.data.get('terminal_shortcuts',{})
    if not records:
        return None
    target = terminal_target(host.snapshot())
    entry = records.get(target['name']) if target else None
    if entry and all(entry.get(k)==value for k,value in target.items()):
        return target
    raise ValueError('Run LXTerminal restoration as the recorded desktop user through sudo.')


def installed_desktop_target(store,host):
    state=host.snapshot()
    user=store.data.get('primary') if store.data.get('profile')=='AALTO' else None
    return terminal_target(state,user)


def share_definitions(prefix):
    binaries=[(BASE/'bin'/name,str(prefix/'bin'/name),mode)
              for name,mode in (('rpi-share','755'),('rpi-share-builder.py','755'),('rpi_share_catalog.py','644'))]
    examples=[(BASE/'config'/name,str(prefix/'share/rpi-share/examples'/name),'644')
              for name in ('rpi-share.example.csv','rpi-share.example.json','rpi-share.schema.json')]
    return binaries+examples


def share_paths(prefix):
    return [destination for _,destination,_ in share_definitions(prefix)]


def app_record(name):
    return f'/opt/sci/lib/.sci-apps-v1/{name}.json'


def save_selection(store, a, plan, state):
    preferences={key:getattr(a,key) for key in (*plan['components'],'ssh','ntp_server','kernel_4k','keyboard_layout')
                 if getattr(a,key) is not None}
    store.data.update(profile=plan['profile'], selected=plan['components'], preferences=preferences,
                      lab_prefix=str(a.lab_prefix), ide_prefix=str(a.ide_prefix) if a.ide_prefix else None,
                      share_prefix=str(plan['share_prefix']), ntp=plan['ntp'], ssh_policy=plan['ssh'], primary=plan['primary'],
                      additional=plan['additional'], share_owners=plan['owners'], hostname=plan['hostname'],
                      chromium_policy=plan['chromium_policy'],
                      share_later=a.share_later,
                      pending_install=True, pending_update_existing=a.update_existing,
                      accounts={user: user in state['accounts'] for user in [plan['primary'],*plan['additional']]})
    if plan['hostname'] != state['hostname']:
        store.data['pending_hostname'] = dict(name=plan['hostname'], previous=state['hostname'])
    elif not plan.get('continue_hostname'):
        store.data.pop('pending_hostname', None)
    if plan.get('wlan_country'):
        store.data['pending_wlan'] = dict(country=plan['wlan_country'],previous=plan['previous_wlan_country'])
    if plan.get('config_path'):
        store.data['pending_share'] = dict(path=str(plan['config_path']), kind=plan['config_kind'],
                                           default_group=a.default_group, replace=a.replace_share_config,
                                           digest=plan['config_digest'])
    else:
        store.data.pop('pending_share',None)
    if plan.get('imaging_selection'):
        store.data['pending_imaging'] = plan['imaging_selection']
    else:
        store.data.pop('pending_imaging', None)
    if plan.get('wolfram_reviewed'):
        store.data['pending_wolfram'] = vars(plan['wolfram_reviewed'])
    else:
        store.data.pop('pending_wolfram', None)
    store.save()


@contextmanager
def track_stage(store, host, stage, a, plan, state):
    targets=target_paths(stage,a,plan,state)
    service_probe=(lambda: services(host)) if stage=='profile' else None
    apt_stage=stage in ('profile','system','hardware','wolfram')
    packages=apt_inventory(host) if stage=='wolfram' else {}
    with store.stage(stage,targets,service_probe):
        try:
            yield
        except BaseException as error:
            if apt_stage:
                try:
                    store.data['apt_current']=apt_inventory(host)
                    if stage=='wolfram':
                        remember_wolfram_install(store, packages)
                except Exception as inventory_error:
                    error.add_note(f'Could not refresh the APT inventory: {inventory_error}')
            raise
        if apt_stage:
            store.data['apt_current']=apt_inventory(host)
        if stage=='wolfram':
            remember_wolfram_install(store, packages)
        if stage=='imaging' and store.data['components'][stage]['status']!='deferred':
            if approved:=store.data.pop('pending_imaging',None):
                store.data['imaging']=approved
        if stage in ('conda','lab314','hardware','spyder-ide'):
            record=store.data['components'][stage]
            record['versions']=environment_versions(store.path(targets[0][0])) if targets else {}


def remember_wolfram_install(store, previous):
    learned=store.data['apt_current'].get(wolfram.PACKAGE)
    if learned and wolfram.PACKAGE not in previous and wolfram.PACKAGE not in store.data['apt_original']:
        store.data['wolfram_owned']=learned


def environment_versions(prefix):
    found={}
    for line in ('python','conda','spyder','spyder-kernels','opencv','hdf5','h5py','netcdf4','numpy'):
        for path in (prefix/'conda-meta').glob(f'{line}-[0-9]*.json'):
            try:
                record=json.loads(path.read_text())
            except (OSError,ValueError):
                continue
            if record.get('name')==line and isinstance(record.get('version'),str):
                found[line]=record['version']
    return found


def imaging_tool_hashes(source):
    return {path.name:hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((source/'scripts/install').iterdir())
            if path.is_file() and (path.suffix in ('.sh','.py') or path.name == 'app-catalog.json')}


def status(store, host):
    data=store.data or {}
    current=apt_inventory(host)
    keyboard=preboot.active_layout()
    print('Raspberry Pi Scientific Environment')
    print(f"Profile: {data.get('profile') or 'Unknown'}")
    if data.get('profile'):
        print('Chromium policy:', chromium_description(selected_chromium(data)))
    print('Full OS upgrade:',os_upgrade.description(data))
    print(f"Keyboard: {keyboard or data.get('keyboard') or 'Unknown'} (preserved by reset)")
    print('I²C device:', 'present' if (preboot.DEV/'i2c-1').is_char_device() else 'missing')
    print('SPI devices:', 'present' if any(path.is_char_device() for path in preboot.DEV.glob('spidev0.*')) else 'missing')
    if not store.data:
        print(UNKNOWN)
    current_services=services(host)
    report_ssh(data.get('ssh_policy','unknown'), ssh_status(host))
    print(f"NTP: {current_services['ntp'] or 'unknown'}")
    ntp_file=store.path(NTP_FILE)
    if ntp_file.is_file() and not ntp_file.is_symlink():
        for line in ntp_file.read_text(errors='replace').splitlines():
            if re.fullmatch(r'NTP=[A-Za-z0-9. :_-]+',line):
                print('Configured time servers:',line[4:])
    print(f'Kernel: {platform.release()}; memory page size: {os.sysconf("SC_PAGE_SIZE")} bytes')
    running_boot=boot_id()
    if (preboot.REBOOT_MARKER.exists() or data.get('pending_boot')==running_boot
            or data.get('pending_kernel_boot')==running_boot or os_upgrade.reboot_pending(data)):
        print('Reboot pending during this boot.')
    elif data.get('pending_boot') or data.get('pending_kernel_boot'):
        print('Reboot completed; run setup again to verify the running kernel and devices.')
    attention=False
    for name, labels in LABELS.items():
        logical=location(data,name)
        records=[(name_,entry) for name_,entry in data.get('paths',{}).items() if component_for(name_,entry)==name]
        saved=data.get('components',{}).get(stage_for(name),{})
        if saved.get('status') in ('running','failed'):
            text='Partially installed or last operation failed'
        elif saved.get('status')=='blocked' and not (logical and host.exists(logical)):
            text='Blocked by an earlier installation failure'
        elif any(entry.get('conflict') or ('installed' in entry and
                 store.inspect(name_,entry['tree']) not in (entry['original'],entry['installed']))
                 for name_,entry in records):
            text='Configuration drift; review required'
        elif name=='profile':
            text='Tracked' if records else 'Unknown ownership'
        elif name=='terminal-shortcuts':
            users=', '.join(sorted(data.get('terminal_shortcuts',{})))
            text=f'Tracked for {users}' if users else 'Not installed'
        elif name=='locales':
            text=', '.join(data.get('locales', ())) or 'No installer record'
        elif name=='chromium':
            if selected_chromium(data)=='shared':
                text='Configured' if all(store.inspect(name_)!=ABSENT for _,name_ in CHROMIUM_FILES) else 'Missing definitions'
            else:
                text='Personal defaults'
        elif name=='imaging':
            text=('Tracked integration' if records and any(store.inspect(n)!=ABSENT for n,_ in records)
                  else 'Unknown ownership' if host.exists('/opt/sci/lib/.sci-apps-v1') else 'Not selected')
        elif name=='wolfram':
            text=('Installed; tracked' if data.get('wolfram_owned') else 'Installed; ownership unknown') if name+'-engine' in current else 'Missing'
        elif logical and host.exists(logical):
            incomplete=False
            if name in ('conda','lab314','hardware'):
                try:
                    incomplete=not host.environment(Path(logical))
                except (OSError,ValueError):
                    incomplete=True
            if incomplete:
                text='Partially installed'
            elif name=='spyder':
                text='Package installed; graphical acceptance pending'
            elif records and all(not e.get('conflict') for _,e in records):
                text='Installed and verified at last setup' if data.get('components',{}).get('verification',{}).get('status')=='applied' else 'Installed; verification pending'
            else:
                text='Installed; ownership unknown'
        else:
            text='Missing' if data.get('selected',{}).get({'hardware':'hardware','spyder':'spyder'}.get(name,name)) else 'Not selected'
        attention |= text.startswith(('Partially','Blocked','Configuration drift')) or text=='Missing' and data.get('selected',{}).get(name,False)
        print(f'  {labels:<30} {text}')
    print('Installation health:', 'Needs review' if attention else 'Ownership unknown' if not data else 'Run verification for current health')
    print('Run Verify to confirm current software and configuration.')


def location(data, component):
    if component=='lab314':
        return data.get('lab_prefix',DEFAULT_PATHS[component])
    if component=='spyder':
        return str(Path(data.get('lab_prefix','/opt/lab314'))/'bin/spyder')
    if component=='share':
        return str(Path(data.get('share_prefix','/usr/local'))/'bin/rpi-share')
    if component=='spyder-ide':
        return data.get('ide_prefix')
    return DEFAULT_PATHS.get(component)


def stage_for(component):
    return {'activation':'shell','envrun':'shell','spyder':'spyder-desktop'}.get(component,component)


def component_for(path, entry):
    stage=entry['component']
    if path=='/usr/local/bin/envrun':
        return 'envrun'
    return {'shell':'activation','spyder-desktop':'spyder','wolfram-launchers':'wolfram'}.get(stage,stage)


@contextmanager
def inspection(host):
    """Keep runtime check caches and temporary profiles out of the target installation."""
    with tempfile.TemporaryDirectory(prefix='rpi-verify-') as tmp:
        old=host.env.copy()
        host.env.update(TMPDIR=tmp, XDG_CONFIG_HOME=tmp, XDG_CACHE_HOME=tmp,
                        XDG_DATA_HOME=tmp, MPLCONFIGDIR=tmp, CONDA_PKGS_DIRS=tmp,
                        PYTHONDONTWRITEBYTECODE='1')
        try:
            yield
        finally:
            host.env.clear()
            host.env.update(old)


def verify(store, host, component=None):
    data=store.data or {}
    paths={name:location(data,name) for name in DEFAULT_PATHS}
    selected=data.get('selected',{})
    commands={
        'conda':[Path(paths['conda'])/'bin/conda','--version'],
        'lab314':['bash',HERE/'verify_rpi_lab314.sh','--science-only','--prefix',paths['lab314']],
        'spyder':[Path(paths['lab314'])/'bin/python','-IB',HERE/'check_lab314.py',
                  '--prefix',paths['lab314'],'--require-spyder','--functional'],
        'hardware':['bash',HERE/'verify_rpi_env.sh'], 'envrun':[paths['envrun'],'--help'],
        'share':[paths['share'],'--check'], 'activation':['bash','-n',paths['activation']],
        'wolfram':['dpkg-query','-W','wolfram-engine'],
    }
    failed=False
    if component=='locales' or (not component and data.get('locales')):
        try:
            failed=not locale_setup.verify(host,store)
        except (OSError,ValueError,subprocess.SubprocessError) as error:
            print('LIMITED locales:',error)
            failed=True
        if component=='locales':
            return int(failed)
    wlan_country=data.get('pending_wlan',{}).get('country') or data.get('wlan_country')
    if component=='wlan' or (not component and wlan_country):
        try:
            state=wlan.read_state(host)
            detail=wlan.verify(state,wlan_country or wlan.existing_country(state) or 'FI',data)
            print(detail)
            failed |= detail.startswith('DEFERRED')
        except (ValueError,OSError) as exc:
            print('FAIL WLAN:',exc)
            failed=True
        if component=='wlan':
            return int(failed)
    if component=='chromium' or (not component and data.get('profile')):
        try:
            message=chromium_policy(store)
            print(message)
            failed |= message.startswith('DEFERRED')
        except (OSError, ValueError) as error:
            print(f'FAIL Chromium: {error}')
            failed=True
    with inspection(host):
        for name,command in commands.items():
            if component and name!=component:
                continue
            installed=host.exists(paths[name]) if name in paths else 'wolfram-engine' in apt_inventory(host)
            if not installed:
                stage=data.get('components',{}).get(stage_for(name),{})
                if stage.get('status')=='blocked':
                    print(f'BLOCKED {LABELS[name]} (installation did not complete)')
                elif component or selected.get(name) or not data:
                    print(f'NOT INSTALLED {LABELS[name]}')
                else:
                    print(f'NOT SELECTED {LABELS[name]}')
                if component or selected.get(name):
                    failed=True
                continue
            try:
                result=host.run(command,capture=True)
                if result.stdout:
                    print(result.stdout.strip())
                if name=='wolfram':
                    wolfram.verify(host, store)
            except (ValueError,OSError,subprocess.SubprocessError) as error:
                print(f'FAIL {LABELS[name]}: {error}')
                failed=True
            else:
                print(f'PASS {LABELS[name]}')
                if name=='spyder':
                    spyder_pending()
        if component in (None,'profile'):
            report_ssh(data.get('ssh_policy','unknown'), ssh_status(host))
            print('Hostname (running):', platform.node() or 'unknown')
            drift=[name for name,entry in data.get('paths',{}).items()
                   if component_for(name, entry) in ('profile','preboot','system','accounts')
                   and (entry.get('conflict') or store.inspect(name,entry['tree'])!=entry.get('installed'))]
            profile=data.get('services',{}).get('profile',{})
            if profile and services(host)!=profile.get('installed'):
                drift.append('SSH or NTP service state')
            for path in drift:
                print(f'DRIFT {path}')
            failed |= bool(drift)
            print(f'Keyboard stored: {preboot.active_layout() or "unknown"}; check live typing separately.')
            if data.get('components',{}).get('preboot',{}).get('status')=='applied':
                okay=(preboot.DEV/'i2c-1').is_char_device() and any(p.is_char_device() for p in preboot.DEV.glob('spidev0.*'))
                print('PASS I²C/SPI device nodes' if okay else 'MISSING I²C or SPI device nodes')
                failed |= not okay
        if component in (None,'imaging') and data.get('imaging'):
            try:
                run_imaging(store,host,'diagnose')
            except (ValueError,OSError,subprocess.SubprocessError) as error:
                print(f'FAIL Scientific Imaging: {error}')
                failed=True
        elif component=='imaging':
            print(UNKNOWN)
            failed=True
    print('Desktop, camera capture and physical bus access require separate acceptance.')
    return int(failed)


def remote_session():
    if any(os.environ.get(key) for key in ('SSH_CONNECTION','SSH_CLIENT','SSH_TTY')):
        return True
    pid=os.getppid()
    while pid>1:
        try:
            comm=(Path('/proc')/str(pid)/'comm').read_text().strip()
            if comm.startswith('sshd'):
                return True
            info=(Path('/proc')/str(pid)/'status').read_text()
            pid=int(next(line for line in info.splitlines() if line.startswith('PPid:')).split()[1])
        except (OSError,ValueError,StopIteration):
            return True  # Cannot establish a safe local console.
    # sudo or a detached shell can hide SSH variables and ancestry.
    return not sys.stdin.isatty()


def consumers(path):
    matches=[]
    root=os.fsencode(path)
    for process in Path('/proc').glob('[0-9]*'):
        try:
            refs=[os.fsencode(os.readlink(link)).removesuffix(b' (deleted)')
                  for link in (process/'exe',process/'cwd') if link.is_symlink()]
            files=process/'fd'
            if files.exists():
                for link in files.iterdir():
                    try:
                        refs.append(os.fsencode(os.readlink(link)).removesuffix(b' (deleted)'))
                    except FileNotFoundError:
                        continue
            if any(ref==root or ref.startswith(root+b'/') for ref in refs):
                matches.append(process.name)
                continue
            for filename in ('maps','cmdline'):
                data=(process/filename).read_bytes()
                if root+b'/' in data or root+b'\0' in data:
                    matches.append(process.name)
                    break
        except (FileNotFoundError,ProcessLookupError,PermissionError):
            continue
    return matches


def conda_dependents(store, host):
    roots={'/opt/lab314','/opt/rpi'}
    roots.update(name for name,entry in store.data['paths'].items() if entry['tree'] and name!='/opt/conda')
    for base in ('/opt','/opt/conda/envs'):
        path=store.path(base)
        if path.is_dir():
            roots.update('/'+str(p.relative_to(store.root)) for p in path.iterdir()
                         if (p/'conda-meta').is_dir() or (base=='/opt/conda/envs' and p.is_symlink()))
    homes={Path('/root'),*(Path(account['home']) for account in host.snapshot().get('accounts',{}).values())}
    for home in homes:
        for parent in (home/'.conda/envs', home/'miniforge3/envs',home/'.local/share/mamba/envs'):
            if parent.is_absolute():
                actual=store.root.joinpath(*parent.parts[1:])
                if actual.is_dir():
                    roots.update('/'+str(p.relative_to(store.root)) for p in actual.iterdir() if (p/'conda-meta').is_dir())
        registry=home/'.conda/environments.txt'
        if registry.is_absolute():
            file=store.root.joinpath(*registry.parts[1:])
            if file.is_file() and not file.is_symlink() and file.stat().st_size<1024*1024:
                roots.update(line.strip() for line in file.read_text(errors='replace').splitlines()
                             if line.startswith('/') and not line.startswith('/opt/conda/'))
    present=[]
    for name in sorted(roots-{'/opt/conda'}):
        try:
            path=store.path(name)
            if path.exists() or path.is_symlink():
                present.append(name)
        except ValueError:
            present.append(name)
    return present


def apt_removal(host, package):
    command=['apt-get','--simulate','remove','--',package]
    result=host.run(command,capture=True)
    actions=re.findall(r'^(Remv|Purg|Inst|Conf)\s+(\S+)',result.stdout,re.M)
    if actions!=[('Remv',package)]:
        raise ValueError(f'APT removal is not limited to {package}; preserve it for review.')
    return result.stdout


def managed_tree(store, name, entry):
    path=store.trusted_parents(name)
    if not path.is_relative_to(store.root/'opt') or path==store.root/'opt':
        raise ValueError('Only recorded descendants of /opt can be removed automatically.')
    if entry['original']!=ABSENT or entry.get('conflict') or entry.get('installed',{}).get('kind')!='tree':
        raise ValueError(UNKNOWN)
    if store.snapshot(name,tree=True)!=entry['installed']:
        raise ValueError('Changed, missing, or untracked files in the environment; preserve for review.')
    if active:=consumers(path):
        raise ValueError('Environment in use by PID(s): '+', '.join(active))


def run_imaging(store,host,verb,preview=False,apps=None):
    saved=store.data.get('imaging') if store.data else None
    if not saved:
        raise ValueError(UNKNOWN)
    source=Path(saved['source'])
    if not source.is_absolute() or source.resolve()!=source:
        raise ValueError('Scientific Imaging source moved or is symlinked.')
    # A previous approval is insufficient to execute a now user-editable tree as root.
    for path in (source,*source.parents):
        info=path.lstat()
        if info.st_uid!=0 or info.st_mode&0o022:
            raise ValueError('Scientific Imaging source requires a reviewed, root-owned checkout for lifecycle commands.')
    for directory, dirs, files in os.walk(source,followlinks=False):
        for name in dirs+files:
            path=Path(directory)/name
            info=path.lstat()
            if path.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:
                raise ValueError(f'Untrusted Scientific Imaging source path: {path}')
    if imaging_tool_hashes(source)!=saved['tool_hashes']:
        raise ValueError('Scientific Imaging lifecycle tools changed after approval; review the source.')
    scripts={'diagnose':'02-diagnose.sh','update':'03-update.sh','remove':'04-remove.sh','repair':'01-install.sh'}
    selected=apps if apps is not None else saved['apps']
    if any(app not in saved['apps'] or not PACKAGE.fullmatch(app) for app in selected):
        raise ValueError('Invalid recorded Scientific Imaging application')
    return host.run(['bash',source/'scripts/install'/scripts[verb],
                     *(['--plan'] if preview else []),*(part for app in selected for part in ('--app',app))],
                    capture=preview)


def removed_applications(store,host,blocked):
    apps=[]
    for app in store.data.get('imaging',{}).get('apps',[]):
        name=app_record(app)
        entry=store.data['paths'].get(name)
        if store.inspect(name)==ABSENT:
            continue
        if not entry or entry['original']!=ABSENT or entry.get('conflict') or store.inspect(name)!=entry.get('installed'):
            blocked.append(f'{app}: {UNKNOWN}')
            continue
        if consumers(store.path('/opt/sci')):
            blocked.append(f'{app}: Scientific Imaging applications are in use.')
            continue
        try:
            run_imaging(store,host,'remove',preview=True,apps=[app])
            apps.append(app)
        except (OSError,ValueError,subprocess.SubprocessError) as error:
            blocked.append(f'{app}: {error}')
    return apps


def removal_plan(store,host,component=None):
    if not store.data:
        return [],[UNKNOWN]
    reset=component is None
    entries=store.data['paths']
    actions=[]
    blocked=[]
    if reset or component=='terminal-shortcuts':
        try:
            target=terminal_restoration(store,host)
            if target and terminal_shortcuts(host,target,restore=True,preview=True)=='changed':
                actions.append(('terminal-shortcuts',str(Path(target['home'])/'.config/lxterminal/lxterminal.conf')))
        except (ValueError,OSError,subprocess.SubprocessError) as error:
            blocked.append(f'LXTerminal: {error}')
    if reset or component=='imaging':
        if apps:=removed_applications(store,host,blocked):
            actions.extend(('application',app) for app in apps)
    # Dependent prefixes are considered before the Conda base and its links.
    for name,entry in sorted(entries.items(),key=lambda p:(p[0]=='/opt/conda',p[0])):
        owner=component_for(name,entry)
        if not entry['tree'] or (not reset and component!=owner):
            continue
        current=store.inspect(name,True)
        if current==ABSENT:
            continue
        if owner in ('lab314','hardware') and store.path('/opt/sci/lib/.sci-apps-v1').is_dir():
            records=list(store.path('/opt/sci/lib/.sci-apps-v1').glob('*.json'))
            scheduled={store.path(app_record(app)) for kind,app in actions if kind=='application'}
            if any(path not in scheduled for path in records):
                blocked.append(f'{name}: Scientific Imaging has remaining applications or unknown dependencies.')
                continue
        if name=='/opt/conda':
            removed={x for kind,x in actions if kind=='tree'}
            depends=[path for path in conda_dependents(store,host) if path not in removed]
            if depends:
                blocked.append(f'{name}: dependent environments remain ({", ".join(depends)}).')
                continue
        try:
            managed_tree(store,name,entry)
        except (OSError,ValueError) as error:
            blocked.append(f'{name}: {error}')
        else:
            actions.append(('tree',name))

    for name,entry in entries.items():
        owner=component_for(name,entry)
        remove_activation=component=='lab314' and any(c=='tree' and p==location(store.data,'lab314') for c,p in actions)
        if entry['tree'] or owner=='imaging' or (not reset and owner!=component and
                not (remove_activation and owner in ('activation','spyder'))):
            continue
        if any(kind=='tree' and Path(name).is_relative_to(parent) for kind,parent in actions):
            continue
        current=store.inspect(name)
        if current==entry['original'] and not entry.get('conflict'):
            continue
        if name.startswith('/etc/sudoers.d/'):
            blocked.append(f'{name}: administrator access is preserved; review separately.')
            continue
        if name in ('/etc/hosts','/etc/hostname') and remote_session():
            blocked.append(f'{name}: restore from the local console.')
            continue
        if owner=='conda' and ('tree','/opt/conda') not in actions and store.inspect('/opt/conda',True)!=ABSENT:
            continue
        if name=='/etc/profile.d/sci-path.sh' and store.path('/opt/sci/lib/.sci-apps-v1').is_dir():
            scheduled={store.path(app_record(app)) for kind,app in actions if kind=='application'}
            if any(p not in scheduled for p in store.path('/opt/sci/lib/.sci-apps-v1').glob('*.json')):
                blocked.append(f'{name}: retained for remaining Scientific Imaging applications.')
                continue
        if entry.get('conflict') or 'installed' not in entry or current!=entry['installed'] or entry['original']['kind']=='unavailable':
            blocked.append(f'{name}: configuration drift or incomplete operation; preserve for review.')
            continue
        actions.append(('file',name))
    if reset or component=='profile':
        tracked=store.data['services'].get('profile')
        if tracked and tracked.get('original')!=tracked.get('installed'):
            current=services(host)
            if tracked.get('conflict') or current!=tracked.get('installed'):
                blocked.append('SSH/NTP service state has drifted or was not verified; preserve for review.')
            else:
                original=tracked['original']
                ssh=('ssh_enabled','ssh_active')
                ntp=('ntp','timesync')
                if any(original[k]!=current[k] for k in ntp):
                    if any(item.startswith(NTP_FILE+':') for item in blocked):
                        blocked.append('NTP service state retained because the configuration needs review.')
                    elif original['ntp'] in ('yes','no') and original['timesync'] in ('active','inactive'):
                        actions.append(('service','ntp'))
                    else:
                        blocked.append('Original NTP service state cannot be restored automatically.')
                if any(original[k]!=current[k] for k in ssh):
                    if remote_session():
                        blocked.append('SSH restoration requires an interactive local console; current access preserved.')
                    elif original['ssh_enabled'] in ('enabled','disabled','not-found') and original['ssh_active'] in ('active','inactive'):
                        actions.append(('service','ssh'))
                    else:
                        blocked.append('Original SSH service state cannot be restored automatically.')
    if reset or component=='wolfram':
        existing=apt_inventory(host).get('wolfram-engine')
        owned=store.data.get('wolfram_owned')
        if existing:
            if not owned or owned!=existing:
                blocked.append(f'Wolfram Engine: {UNKNOWN}')
            else:
                try:
                    apt_removal(host,'wolfram-engine')
                    actions.append(('apt','wolfram-engine'))
                except (ValueError,OSError,subprocess.SubprocessError) as error:
                    blocked.append(str(error))
    if not reset and not actions and not blocked:
        if logical:=location(store.data,component):
            if host.exists(logical):
                blocked.append(f'{logical}: no reversible installer-owned change was proven.')
    return actions,blocked


def restore_service(store,host,name):
    record=store.data['services']['profile']
    original=record['original']
    expected=record['installed']
    current=services(host)
    fields=('ssh_enabled','ssh_active') if name=='ssh' else ('ntp','timesync')
    if any(current[k]!=expected[k] for k in fields):
        raise ValueError(f'Service state changed after confirmation: {name}')
    if name=='ssh':
        if remote_session():
            raise ValueError('Restore SSH only from an interactive local console.')
        host.run(['systemctl','enable' if original['ssh_enabled']=='enabled' else 'disable','ssh'])
        host.run(['systemctl','start' if original['ssh_active']=='active' else 'stop','ssh'])
    else:
        host.run(['timedatectl','set-ntp','true' if original['ntp']=='yes' else 'false'])
        host.run(['systemctl','restart' if original['timesync']=='active' else 'stop','systemd-timesyncd'])
    after=services(host)
    original_fields={key:original[key] for key in fields}
    if name=='ssh' and original_fields['ssh_enabled']=='not-found':
        original_fields['ssh_enabled']='disabled'
    if any(after[key]!=value for key,value in original_fields.items()):
        raise ValueError(f'Could not verify the restored service state: {name}')
    for key in fields:
        expected[key]=after[key]


def apply_removal(store,host,actions,blocked):
    errors=list(blocked)
    reboot=False
    failed_apps=False
    failed_files=set()
    for kind,name in actions:
        store.data['operation']={'action':kind,'target':name,'status':'running','time':now()}
        store.save()
        try:
            if kind=='application':
                if consumers(store.path('/opt/sci')):
                    raise ValueError('Scientific Imaging is now in use.')
                run_imaging(store,host,'remove',apps=[name])
                store.data['paths'][app_record(name)]['installed']=dict(ABSENT)
            elif kind=='tree':
                entry=store.data['paths'][name]
                if failed_apps and entry['component'] in ('lab314','hardware'):
                    raise ValueError('Dependent applications could not be removed.')
                if name=='/opt/conda' and conda_dependents(store,host):
                    raise ValueError('Dependent Conda environments remain.')
                managed_tree(store,name,entry)
                path=store.path(name)
                if not shutil.rmtree.avoids_symlink_attacks:
                    raise ValueError('Safe directory removal is unavailable.')
                shutil.rmtree(path)
                entry['installed']=dict(ABSENT)
                store.data['components'][entry['component']]['status']='removed'
            elif kind=='file':
                if failed_apps and name=='/etc/profile.d/sci-path.sh':
                    raise ValueError('Dependent applications could not be removed.')
                if name in ('/etc/hosts','/etc/hostname') and remote_session():
                    raise ValueError('Restore hostname only from a local console.')
                entry=store.data['paths'][name]
                if entry['component']=='conda' and store.inspect('/opt/conda',True)!=ABSENT:
                    raise ValueError('Conda remains installed; preserve its links and configuration.')
                store.restore_file(name,entry)
                reboot |= name in (*FIRMWARE_PATHS,'/etc/hostname')
            elif kind=='service':
                if name=='ntp' and NTP_FILE in failed_files:
                    raise ValueError('Preserve NTP service state until its configuration is reviewed.')
                restore_service(store,host,name)
            elif kind=='terminal-shortcuts':
                target=terminal_restoration(store,host)
                if not target or str(Path(target['home'])/'.config/lxterminal/lxterminal.conf')!=name:
                    raise ValueError('LXTerminal owner changed after confirmation.')
                terminal_shortcuts(host,target,restore=True)
                store.data['terminal_shortcuts'].pop(target['name'])
            elif kind=='apt':
                if apt_inventory(host).get(name)!=store.data.get('wolfram_owned'):
                    raise ValueError('APT package version changed after confirmation.')
                apt_removal(host,name)
                host.run(['apt-get','-y','remove','--',name])
                store.data['apt_current']=apt_inventory(host)
                store.data.pop('wolfram_owned',None)
            print(f'DONE {name}')
        except (ValueError,OSError,subprocess.SubprocessError) as error:
            failed_apps |= kind=='application'
            if kind=='file':
                failed_files.add(name)
            errors.append(f'{name}: {error}')
            store.data['operation']['status']='failed'
            store.save()
        else:
            store.data['operation']['status']='complete'
            store.save()
    if reboot:
        store.data['pending_boot']=boot_id()
        store.save()
        print('Reboot manually to apply restored boot settings. I²C/SPI may be disabled after reboot.')
    if errors:
        print('Remaining items requiring review:')
        for problem in errors:
            print('  '+problem)
    print('Keyboard layout, rpi-keyboard, user accounts, home directories and measurement data were preserved.')
    return int(bool(errors))


def diagnostic_report(store,host):
    status(store,host)
    try:
        df=host.probe(['df','-h','--','/opt','/tmp'])
        if df.returncode==0 and df.stdout:
            print('Available storage:')
            print(df.stdout.rstrip())
    except OSError as error:
        print(f'Storage information unavailable: {error}')
    data=store.data or {}
    for name,record in data.get('components',{}).items():
        if record['status'] in ('running','failed','blocked'):
            print(f"{record['status'].upper()} {name} ({record.get('updated','unknown time')})")
    if data.get('operation',{}).get('status') in ('running','failed'):
        print('Interrupted or failed lifecycle operation:',data['operation'])
    prefix=Path(location(data,'lab314'))
    if host.exists(prefix):
        try:
            if not host.environment(prefix):
                raise ValueError(f'Environment is absent: {prefix}')
        except (ValueError,OSError,subprocess.SubprocessError) as error:
            print(f'INCOMPLETE {prefix}: {error}')
            print('Preserve the prefix. Use Verify or an explicit quarantine before installing at the original path.')
        else:
            if host.native_lab314(prefix) and host.exists(prefix/'bin/spyder'):
                for option, label in (('--kernel-only','Spyder kernel'), ('--reporting-only','scientific reporting')):
                    try:
                        with inspection(host):
                            host.run([prefix/'bin/python','-IB',HERE/'check_lab314.py','--prefix',prefix,option])
                    except (OSError,ValueError,subprocess.SubprocessError) as error:
                        print(f'FAIL {label} diagnostic: {error}')
            else:
                verify(store,host,'lab314')
    logs=store.directory/'logs'
    if logs.is_dir():
        paths=sorted(logs.glob('install-*.log'),key=lambda p:p.stat().st_mtime,reverse=True)
        if paths:
            print('Most recent diagnostic log:',paths[0])
    print('Resume normal setup after correcting the reported failure. Existing valid Miniforge and environments are retained.')
    return 0


def quarantine_plan(store,host):
    logical=location(store.data or {},'lab314')
    path=store.path(logical)
    if logical!='/opt/lab314' or not path.is_dir() or path.is_symlink():
        raise ValueError('Quarantine applies to an incomplete /opt/lab314 directory.')
    store.trusted_parents(logical)
    snapshot=store.snapshot(logical,tree=True)
    try:
        valid=host.environment(Path(logical))
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        print(f'Environment diagnostic: {error}')
        valid=False
    if valid:
        with inspection(host):
            try:
                host.run([path/'bin/python','-IB',HERE/'check_lab314.py','--prefix',path],capture=True)
            except (ValueError,OSError,subprocess.SubprocessError) as error:
                print(f'Environment verification failed: {error}')
            else:
                raise ValueError('The environment verification succeeded; quarantine refused.')
    if active:=consumers(path):
        raise ValueError('Environment in use by PID(s): '+', '.join(active))
    print(f'Move {logical} to a new sibling backup. All files remain available for diagnosis.')
    print('Afterward, run sudo bash setup-rpi.sh to create the missing environment and resume.')
    return logical,snapshot


def quarantine(store,host,approved):
    logical,fingerprint=quarantine_plan(store,host)
    if (logical,fingerprint)!=approved:
        raise ValueError('The environment changed after the reviewed quarantine plan.')
    path=store.path(logical)
    import uuid
    save=path.with_name(path.name+'.incomplete-'+uuid.uuid4().hex[:12])
    if save.exists() or save.is_symlink():
        raise ValueError('Quarantine destination already exists.')
    store.data['operation']={'action':'quarantine','target':logical,'backup':str(save),'status':'running','time':now()}
    store.save()
    path.rename(save)
    from installation_state import sync_directory
    sync_directory(path.parent)
    entry=store.data['paths'].get(logical)
    store.data.setdefault('quarantines',[]).append(dict(store.data['operation'],status='complete'))
    if entry:
        # The old prefix still exists under its backup name. Track a genuinely
        # new installation at the now-vacant original path independently.
        store.data['paths'].pop(logical)
    # An unknown old installation remains unknown; a new prefix can be tracked from now on.
    store.data['operation']['status']='complete'
    store.data['components'].setdefault('lab314',{})['status']='missing'
    store.save()
    print(f'Incomplete files preserved at {save}. Run sudo bash setup-rpi.sh again.')
    return 0


def approved_targets(store, paths, component):
    targets=[]
    for name in paths:
        current=store.inspect(name)
        entry=(store.data or {}).get('paths',{}).get(name)
        if current!=ABSENT and (not entry or entry.get('conflict') or current!=entry.get('installed')):
            raise ValueError(f'{name}: {UNKNOWN}')
        targets.append((name,False))
    return targets


def software_action(store,host,verb,component,packages,preview,approved_plan=None,*,wlan_country=None):
    data=store.data or {}
    if not preview and not data:
        raise ValueError(UNKNOWN)
    if packages and component not in ('lab314','spyder','hardware'):
        raise ValueError('Package names apply to Scientific Python, Spyder or hardware Python.')
    if any(not PACKAGE.fullmatch(package) for package in packages):
        raise ValueError('Use an installed package name without shell or version expressions.')
    if component=='locales':
        if preview:
            proposal=locale_setup.plan(host,store)
            locale_setup.describe(proposal)
            if not (proposal.enable or proposal.generate):
                print('No locale generation changes planned.')
            return proposal
        print(apply_locales(store,host,approved_plan))
        return
    if component=='wlan':
        if verb!='repair':
            raise ValueError('Use repair or verify for WLAN')
        if preview:
            previous=wlan.existing_country(wlan.read_state(host))
            pending=data.get('pending_wlan',{})
            resumed=pending.get('country') if pending.get('previous')==previous else None
            country=wlan_country or resumed or previous or 'FI'
        else:
            previous,country=approved_plan
        detail=wlan.configure(host,country,expected=previous,data=store.data,preview=preview)
        print(detail)
        if not preview:
            if detail.startswith('DEFERRED'):
                store.data['pending_wlan']=dict(country=country,previous=previous)
                store.data['operation']['status']='deferred'
            else:
                store.data.pop('pending_wlan',None)
        return previous,country
    if component=='terminal-shortcuts' and verb=='repair':
        target=installed_desktop_target(store,host)
        layout=preboot.active_layout()
        if not target or layout not in ('fi','se'):
            print('LXTerminal zoom setup requires the intended desktop user and a Finnish or Swedish layout.')
            return
        print(apply_terminal_shortcuts(store,host,target,layout,preview=preview))
        return
    if component=='chromium':
        mode=selected_chromium(data)
        if preview:
            print('Chromium policy:', chromium_description(mode))
            paths=(chromium_personal_restore(store) if mode=='personal' else
                   [(path, None) for _,path in CHROMIUM_FILES])
            for path, _ in paths:
                print(('  Restore ' if mode=='personal' else '  Reconcile ') + path)
            return mode
        else:
            if approved_plan is not None and mode!=approved_plan:
                raise ValueError('The saved Chromium policy changed. Review a new maintenance plan.')
            with store.stage('chromium',[(path,False) for _,path in CHROMIUM_FILES],repair_missing=True):
                result=chromium_policy(store,mode=mode,apply=True)
                print(result)
                if result.startswith('DEFERRED'):
                    store.data['components']['chromium']['status']='deferred'
        return
    if component in ('lab314','spyder'):
        name=location(data,'lab314')
        prefix=store.path(name)
        selected=packages or (['spyder','spyder-kernels'] if component=='spyder' else [])
        if not host.environment(Path(name)):
            if verb!='repair' or preview is False and not data:
                raise ValueError('Scientific Python is missing; run normal setup to install it.')
            if preview:
                print(f'Install missing Scientific Python with integrated Spyder at {name}.')
            else:
                with store.stage('lab314',[(name,True)]):
                    host.run(['bash',HERE/'create_lab314_env.sh','--prefix',prefix])
                    store.data['components']['lab314']['versions']=environment_versions(prefix)
            return
        if verb=='repair' and component=='spyder' and not packages and host.exists(Path(name)/'bin/spyder'):
            launcher_targets=[]
            if Path(name)==Path('/opt/lab314'):
                launcher_targets=approved_targets(store,[dest for _,dest,_ in SPYDER_LAUNCHER],component)
                print('Install the desktop and terminal launcher without replacing packages:')
                for target,_ in launcher_targets:
                    print('  '+target)
            print('Check the existing integrated Spyder and its kernel without replacing packages.')
            with inspection(host):
                host.run([prefix/'bin/python','-IB',HERE/'check_lab314.py','--prefix',prefix,'--kernel-only'])
            if not preview and launcher_targets:
                with store.stage('spyder-desktop',launcher_targets,repair_missing=True):
                    install_spyder_launcher(host,store)
            spyder_pending()
            return
        if verb=='repair' and not selected:
            raise ValueError('Select a damaged package with --package NAME, or choose Spyder to repair its IDE and kernel.')
        command=[prefix/'bin/python','-IB',HERE/'update_lab314.py','--prefix',prefix]
        command+= [arg for p in selected for arg in ('--package',p)] if selected else ['--all']
        if verb=='repair':
            command.append('--repair')
        opencv_upgrade = component=='lab314' and 'opencv' in packages
        if opencv_upgrade and not host.native_lab314(Path(name)):
            raise ValueError('The OpenCV upgrade requires the current Conda Scientific Python environment.')
        print('Current Conda versions:',environment_versions(prefix))
        if preview:
            if not opencv_upgrade:
                host.run(command)
                return None
            result=host.run(command,capture=True)
            print(result.stdout,end='',flush=True)
            match=re.search(r'^CONDA PLAN TOKEN ([0-9a-f]{64})$',result.stdout,re.MULTILINE)
            if not match:
                raise ValueError('The OpenCV plan could not be verified.')
            return match[1]
        else:
            record=Path(tempfile.mkdtemp(prefix='maintenance-',dir=store.directory))/'operation'
            if opencv_upgrade:
                if not approved_plan:
                    raise ValueError('A reviewed Conda transaction is required.')
                command+=['--approved-conda-plan',approved_plan]
            with store.stage('lab314',[(name,True)]):
                host.run([*command,'--apply','--record-dir',record])
                store.data['components']['lab314']['versions']=environment_versions(prefix)
    elif component=='hardware':
        hardware_action(store,host,verb,packages,preview)
    elif component in ('share','envrun','activation','profile'):
        repair_files(store,host,component,preview)
    elif component=='imaging':
        if preview:
            result=run_imaging(store,host,verb,preview=True)
            print(result.stdout.strip())
        else:
            paths=[(app_record(app),False) for app in data['imaging']['apps']]
            with store.stage('imaging',paths):
                run_imaging(store,host,verb)
    elif component=='wolfram':
        installed=apt_inventory(host).get('wolfram-engine')
        if not installed:
            raise ValueError('Wolfram Engine is not installed; use the profile installer to add it.')
        print('Current Wolfram Engine:',installed)
        proposed=(wolfram.package_metadata(host, installed) if verb=='repair' else wolfram.candidate(host))
        if verb=='update' and proposed and proposed.version==installed:
            proposed=None
        if preview:
            args=['--reinstall',f'{wolfram.PACKAGE}={installed}'] if verb=='repair' else ['--only-upgrade',wolfram.PACKAGE]
            if proposed:
                wolfram.show_preflight(host, proposed)
                host.run(['apt-get','--simulate','install',*args])
                print('Approving the package operation authorizes installation under the displayed Wolfram terms.')
            print('Review and reconcile the package-provided Wolfram GUI and CLI desktop entries.')
            return proposed
        if proposed!=approved_plan:
            raise ValueError('Wolfram APT metadata changed. Review the new update plan.')
        if proposed:
            wolfram.show_preflight(host, proposed, strict=True)
            action='--reinstall' if verb=='repair' else '--only-upgrade'
            host.run(['apt-get','install',action,'--no-remove','-y',f'{wolfram.PACKAGE}={proposed.version}'])
        inventory=apt_inventory(host)
        if data.get('wolfram_owned')==installed:
            data['wolfram_owned']=inventory.get('wolfram-engine')
        data['apt_current']=inventory
        store.save()
        reconcile_wolfram_launchers(store, host)
        wolfram.verify(host, store)
    else:
        raise ValueError('This component is maintained through normal setup or its documented upstream procedure.')


def repair_files(store,host,component,preview):
    data=store.data or {}
    if component=='share':
        prefix=Path(data.get('share_prefix','/usr/local'))
        targets=approved_targets(store,share_paths(prefix),component)
        command=['bash',HERE/'install_rpi_share.sh','--prefix',prefix]
    elif component=='envrun':
        targets=approved_targets(store,['/usr/local/bin/envrun'],component)
        command=['bash',HERE/'install_envrun.sh']
    elif component=='activation':
        names=['/etc/bash.bashrc','/etc/profile.d/lab314-bash.sh','/etc/profile.d/conda-path.sh']
        targets=approved_targets(store,names,component)
        if store.inspect(names[0])==ABSENT:
            raise ValueError('System Bash configuration is missing; restore it separately.')
        command=['bash',HERE/'enable_lab314_autoactivate_rpi.sh']
    else:
        saved=data.get('services',{}).get('profile')
        entry=data.get('paths',{}).get(NTP_FILE)
        if not entry or entry.get('conflict') or not saved or saved.get('conflict'):
            raise ValueError(UNKNOWN)
        current=store.inspect(NTP_FILE)
        if current not in (ABSENT,entry.get('installed')):
            raise ValueError('NTP configuration drift requires manual review.')
        if current!=ABSENT and services(host)==saved['installed']:
            print('Recorded profile configuration and services already match.')
            return
        if remote_session():
            raise ValueError('System service repair requires the local console.')
        print('Reapply the recorded NTP configuration and SSH policy from the local console.')
        if not preview:
            old=host.env.copy()
            host.env.update(PRIMARY_USER=data['primary'], NTP_PRIMARY=data['ntp'],
                            SSH_POLICY=data['ssh_policy'], PRE_ACCOUNTS_MANAGED='1')
            try:
                with store.stage('profile',[(NTP_FILE,False)],lambda:services(host),repair_missing=True):
                    host.run(['bash',HERE/'pre_profile.sh',data['profile']])
                    store.data['apt_current']=apt_inventory(host)
            finally:
                host.env.clear()
                host.env.update(old)
        return
    print('Managed paths for '+LABELS[component]+':')
    for name,_ in targets:
        print('  '+name)
    if not preview:
        stage=stage_for(component)
        with store.stage(stage,targets,repair_missing=True):
            host.run(command)


def hardware_action(store,host,verb,packages,preview):
    prefix=store.path('/opt/rpi')
    if not host.environment(Path('/opt/rpi')):
        print('Install missing Raspberry Pi hardware Python with the existing Raspberry Pi OS 3.13 bridge.')
        if not preview:
            with store.stage('hardware',[('/opt/rpi',True)]):
                host.run(['bash',HERE/'create_rpi_env.sh'])
                store.data['apt_current']=apt_inventory(host)
        return
    current=environment_versions(prefix)
    if not current.get('python','').startswith('3.13.'):
        raise ValueError('Expected the Trixie Python 3.13 hardware environment.')
    bridge=prefix/'lib/python3.13/site-packages/aalto-system-dist-packages.pth'
    if bridge.is_symlink() or bridge.exists() and bridge.read_text()!='/usr/lib/python3/dist-packages\n':
        raise ValueError('Custom or unsafe Raspberry Pi Python bridge; preserve it for review.')
    selected=packages or ['python','numpy','scipy','pandas','matplotlib','pillow','imageio','tifffile','openpyxl','pyserial','spyder-kernels']
    cmd=[store.path('/opt/conda')/'bin/conda','install','-p',prefix,'--freeze-installed',
         '--override-channels','-c','conda-forge',*(p for p in selected if p!='python'),'python=3.13']
    apt=['apt-get','install',*(['--reinstall'] if verb=='repair' else []),*APT_CAMERA]
    if verb=='repair' and packages:
        cmd.append('--force-reinstall')
    print('Current hardware Python:',current)
    print('The plan preserves the Python 3.13 series and the Raspberry Pi OS camera bridge.')
    if preview:
        host.run([*cmd,'--dry-run'])
        host.run([*apt,'--simulate'])
        return
    with store.stage('hardware',[('/opt/rpi',True)]):
        host.run([*apt,'-y'])
        host.run([*cmd,'-y'])
        if not bridge.exists():
            bridge.write_text('/usr/lib/python3/dist-packages\n')
        host.run(['bash',HERE/'verify_rpi_env.sh'])
        store.data['apt_current']=apt_inventory(host)


def package_removal(store,host,component,packages,preview):
    data=store.data or {}
    name=location(data,'lab314')
    prefix=store.path(name)
    entry=data.get('paths',{}).get(name)
    if not entry:
        raise ValueError(UNKNOWN)
    managed_tree(store,name,entry)
    selected=['spyder'] if component=='spyder' else packages
    if not selected or component not in ('spyder','lab314') or any(not PACKAGE.fullmatch(p) for p in selected):
        raise ValueError('Select an installed Conda-owned scientific package.')
    if set(selected)&{'python','python-gil','pip','conda','packaging'}:
        raise ValueError('The scientific Python runtime and package manager cannot be removed selectively.')
    command=[store.path('/opt/conda')/'bin/conda','remove','-p',prefix,*selected,'--json']
    result=json.loads(host.run([*command,'--dry-run'],capture=True).stdout)
    actions=result.get('actions',{})
    unlinked={item['name'] for item in actions.get('UNLINK',[])}
    if result.get('success') is False or unlinked!=set(selected) or actions.get('LINK'):
        raise ValueError('Removal has additional dependency effects, or the package is missing. No packages removed.')
    for item in actions['UNLINK']:
        print(f"Remove {item['name']} {item['version']} from {name}.")
    if preview:
        return
    with store.stage('lab314',[(name,True)]):
        host.run([*command,'-y'])
        store.data['components']['lab314']['versions']=environment_versions(prefix)
    if component=='spyder':
        for _,launcher,_ in SPYDER_LAUNCHER:
            item=data['paths'].get(launcher)
            if item and not item.get('conflict') and store.inspect(launcher)==item.get('installed')!=item['original']:
                store.restore_file(launcher,item)
                store.save()


def show_removal(store, actions, blocked, reset):
    print('RESET INSTALLATION' if reset else 'COMPONENT REMOVAL')
    for kind,name in actions:
        if kind=='file':
            action='Remove installer-created file' if store.data['paths'][name]['original']==ABSENT else 'Restore original file'
        else:
            action={'apt':'Remove APT package','service':'Restore service settings',
                    'tree':'Remove unchanged installer-owned environment',
                    'terminal-shortcuts':'Restore original LXTerminal zoom definitions',
                    'application':'Remove through Scientific Imaging manager'}[kind]
        print(f'  {action}: {name}')
    for text in blocked:
        print('  Preserve for review: '+text)
    if not actions:
        print('No reversible changes were identified.')
    if any(name in (*FIRMWARE_PATHS,'/etc/hostname') for kind,name in actions if kind=='file'):
        print('Manual reboot required. Restoring firmware settings may disable I²C or SPI.')
    print('Preserve keyboard and rpi-keyboard, accounts and privileges, user files and unowned software.')
    if reset and store.data:
        count=len(set(store.data.get('apt_current',{}))-set(store.data.get('apt_original',{})))
        print(f'APT baseline recorded ({count} packages added since setup). Shared packages are retained.')


def confirm(args, destructive=None):
    if destructive:
        if args.confirm:
            return args.confirm==destructive
        if not sys.stdin.isatty():
            return False
        return input(f'Type {destructive} to approve, or press Enter to cancel: ').strip()==destructive
    return args.yes or (sys.stdin.isatty() and input('Apply this reviewed maintenance plan? [y/N] ').strip().lower() in ('yes','y'))


def menu():
    steps=('status','verify','diagnose','repair','update-all','update','remove','reset','quarantine','os-upgrade','exit')
    print('\nRaspberry Pi Scientific Environment · Maintenance')
    for i,label in enumerate(('Show installation status','Verify installed components','Diagnose a partial installation',
        'Repair a component','Update All installed components','Update a component','Remove a component','Reset installer-managed changes',
        'Preserve an incomplete Scientific Python directory for recovery','Review a full Raspberry Pi OS upgrade','Exit'),1):
        print(f'  {i}. {label}')
    while True:
        answer=input(f'Selection [{len(steps)}]: ').strip() or str(len(steps))
        if answer.isascii() and answer.isdigit() and len(answer)<=2 and 1<=int(answer)<=len(steps):
            return steps[int(answer)-1]
        print('Choose one of the menu numbers.')


def require_root():
    if os.geteuid()!=0:
        raise ValueError('Run setup through sudo to apply maintenance.')


def select_component(action):
    choices=list(LABELS) + (['wlan'] if action=='repair' else [])
    for i,key in enumerate(choices,1):
        print(f'  {i}. {LABELS.get(key,"Wireless LAN")}')
    while True:
        value=input(f'Component to {action} (0 returns): ').strip()
        if value in ('','0'):
            return None
        if value.isascii() and value.isdigit() and len(value)<=3 and 1<=int(value)<=len(choices):
            return choices[int(value)-1]
        print('Choose one of the listed component numbers.')


def main(argv,host,store=None):
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--manage', action='store_true', required=True)
    parser.add_argument('--action', choices=('status','verify','diagnose','repair','update','remove','reset','quarantine','os-upgrade'))
    parser.add_argument('--component', choices=(*LABELS,'wlan'))
    parser.add_argument('--wlan-country',type=str.upper,help='two-letter country for WLAN repair')
    parser.add_argument('--all', action='store_true', help='update the complete saved installation')
    parser.add_argument('--package', action='append', default=[])
    parser.add_argument('--plan','--dry-run', action='store_true')
    parser.add_argument('--yes', action='store_true', help='approve a planned repair/update')
    parser.add_argument('--accept-wolfram-license',action='store_true',
                        help='confirm that you reviewed and are authorized to accept the Wolfram terms')
    parser.add_argument('--expect-plan', metavar='ID', help='require the previously reviewed Update All plan ID')
    parser.add_argument('--confirm', choices=('REMOVE','RESET','QUARANTINE'), help='explicit noninteractive approval for a destructive action')
    args=parser.parse_args(argv)
    action=args.action or (menu() if sys.stdin.isatty() else 'status')
    if args.all:
        if args.action!='update':
            parser.error('--all requires --action update')
        action='update-all'
    if action=='update-all' and (args.component or args.package or args.confirm):
        parser.error('Update All cannot be combined with a component, package or removal confirmation')
    if args.expect_plan and (action!='update-all' or not re.fullmatch(r'[0-9a-f]{64}',args.expect_plan)):
        parser.error('--expect-plan requires an Update All plan ID')
    if action=='update-all' and args.yes and not args.plan and not args.expect_plan:
        parser.error('Noninteractive Update All approval requires --expect-plan ID')
    if action=='exit':
        return 0
    if args.package and action not in ('repair','update','remove'):
        parser.error('--package requires repair, update or remove')
    component=args.component
    if not component and action in ('repair','update','remove'):
        if not sys.stdin.isatty():
            parser.error('--component is required')
        component=select_component(action)
        if not component:
            return 0
    if args.wlan_country and (component!='wlan' or action!='repair' or args.wlan_country not in wlan.countries()):
        parser.error('--wlan-country requires WLAN repair and a valid two-letter country')
    if component=='wlan' and action not in ('repair','verify'):
        parser.error('WLAN supports repair and verify')
    if component=='locales' and action=='remove' and not args.package:
        print('Preserve /etc/locale.gen and generated system locales for local and SSH sessions.')
        return 0
    if action=='repair' and component in ('lab314','hardware') and sys.stdin.isatty() and not args.package:
        prompt='Damaged package name (Enter to check the environment): '
        if package:=input(prompt).strip():
            args.package=[package]
        elif component=='lab314' and host.exists('/opt/lab314'):
            action='diagnose'
    store=store or Store()
    store.load()
    if action=='status':
        return status(store,host) or 0
    if action=='verify':
        return verify(store,host,component)
    if action=='diagnose':
        return diagnostic_report(store,host)
    if action=='update-all':
        require_root()
    if not args.plan:
        require_root()
        target=host.snapshot()
        if (target['codename']!='trixie' or target['os_id'] not in ('debian','raspbian')
                or target['architecture'] not in ('aarch64','arm64') or not re.search(r'Raspberry Pi [45]',target['model'])):
            raise ValueError('Maintenance changes require Raspberry Pi OS Trixie on Raspberry Pi 4 or 5.')
    if action=='update-all':
        from update_all import run
        return run(host,store,args)
    if action=='os-upgrade':
        if args.plan:
            os_upgrade.preview(host)
            return 0
        with host.installation(target):
            complete=os_upgrade.run(host,host.records,apt_inventory,lambda:confirm(args),os_upgrade.confirm_removals)
            if os_upgrade.reboot_pending(host.records.data):
                print('Reboot manually when ready.')
        return 0 if complete else 1
    if action=='quarantine':
        proposal=quarantine_plan(store,host)
        if args.plan or not confirm(args,'QUARANTINE'):
            return 0
        with store.locked():
            store.start(host.snapshot(),apt_inventory(host))
            return quarantine(store,host,proposal)
    if action=='reset' or (action=='remove' and component!='spyder' and not args.package):
        scope=None if action=='reset' else component
        proposal=removal_plan(store,host,scope)
        show_removal(store,*proposal,reset=action=='reset')
        if args.plan or not proposal[0] or not confirm(args,'RESET' if action=='reset' else 'REMOVE'):
            return int(bool(proposal[1]) and not args.plan)
        with store.locked():
            if removal_plan(store,host,scope)!=proposal:
                raise ValueError('The removal plan changed. Review a new plan before applying.')
            result=apply_removal(store,host,*proposal)
            if scope=='chromium' and not result:
                store.data['chromium_policy']='personal'
                store.save()
            return result
    if action=='remove':
        with inspection(host):
            package_removal(store,host,component,args.package,True)
        if args.plan or not confirm(args,'REMOVE'):
            return 0
        with store.locked():
            package_removal(store,host,component,args.package,False)
        return 0
    with inspection(host):
        options={'wlan_country':args.wlan_country} if args.wlan_country else {}
        approved_plan=software_action(store,host,action,component,args.package,True,**options)
    if args.plan or not confirm(args):
        return 0
    if component=='wolfram' and approved_plan and args.yes and not args.accept_wolfram_license:
        raise ValueError('Wolfram package maintenance with --yes requires --accept-wolfram-license after reviewing the terms.')
    with store.locked():
        if store.data is None:
            raise ValueError(UNKNOWN)
        from diagnostics import Log
        old=host.log
        host.log=Log(store.directory)
        host.log.stage=f'{action} {component}'
        print('Diagnostic log:',host.log.path)
        store.data['operation']={'action':action,'target':component,'status':'running','time':now()}
        store.save()
        try:
            software_action(store,host,action,component,args.package,False,approved_plan)
        except BaseException:
            store.data['operation']['status']='failed'
            raise
        else:
            if store.data['operation']['status']=='running':
                store.data['operation']['status']='complete'
        finally:
            store.save()
            host.log.close()
            host.log=old
    return 0
