#!/usr/bin/env python3
"""Initial Raspberry Pi provisioning through the established component installers."""
import argparse
from contextlib import contextmanager, nullcontext
import fcntl
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
from uuid import uuid4

import rpi_accounts as accounts
import installation_profiles as profiles
import preboot
import lifecycle
import locale_setup
import wlan
import wolfram
import os_upgrade
from diagnostics import Log, redact
from installation_state import Store

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
locale_environment = locale_setup.keyboard['locale_environment']
SHARE_NAMES = {'GENERAL': 'rpi-share.json', 'HOME': 'rpi-share.home.json', 'AALTO': 'rpi-share.aalto.json'}
SHARE_EXAMPLE = 'rpi-share.example.json'
spec=importlib.util.spec_from_file_location('rpi_catalog',BASE/'bin/rpi_share_catalog.py')
catalog=importlib.util.module_from_spec(spec);spec.loader.exec_module(catalog)


def hostname(value):
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',value):
        raise ValueError('hostname must be a single 1..63 character DNS label')
    return value.lower()


def canonical(value):
    p=Path(value)
    if not p.is_absolute() or p!=p.resolve() or p==Path('/'):
        raise ValueError('canonical absolute path required: '+str(value))
    return p


def hosts_alias(text,old,new):
    """Update the local hostname without changing aliases for other addresses."""
    output=[]
    found=False
    for line in text.splitlines(keepends=True):
        content,separator,comment=line.partition('#')
        tokens=content.split()
        if tokens and tokens[0]=='127.0.1.1':
            prefix, address, aliases = content.partition('127.0.1.1')
            content=prefix+address+re.sub(r'(?<!\S)'+re.escape(old)+r'(?=\.|\s|$)',new,aliases,flags=re.I)
            found |= new in content.split()[1:]
            line=content+separator+comment
        output.append(line)
    updated=''.join(output)
    if not found:
        updated=updated.rstrip('\n')+f'\n127.0.1.1\t{new}\n' if updated else f'127.0.1.1\t{new}\n'
    return updated


class Host:
    """Narrow host boundary; tests replace it, never run provisioning commands."""
    def __init__(self):
        self.locale_requests=locale_setup.requests(os.environ)
        self.env=locale_environment(os.environ,warn=False)
        self.env['PYTHONDONTWRITEBYTECODE']='1'
        self.records=None
        self.log=None
        self.approve_firmware=None

    def refresh_locale_environment(self, *, warn=True):
        self.env=locale_environment({**self.env, **self.locale_requests},warn=warn)

    def run(self, argv, capture=False, **kwargs):
        if self.log:
            return self.log.run(argv,self.env,capture,**kwargs)
        return subprocess.run([str(x) for x in argv],env=self.env,check=True,
                              capture_output=capture,text=True,**kwargs)

    def probe(self,argv):
        return subprocess.run([str(x) for x in argv],env=self.env,check=False,capture_output=True,
                              stdin=subprocess.DEVNULL,text=True)

    @contextmanager
    def installation(self, state):
        store=Store()
        with store.locked():
            if store.data is None:
                store.start(state,lifecycle.apt_inventory(self))
            self.records=store
            self.log=Log(store.directory)
            print('Diagnostic log:',self.log.path)
            umask=os.umask(0o022)
            failure=None
            try:
                yield
            except BaseException as error:
                failure=error
                try:
                    self.log.note(f'[{self.log.stage}] {error}')
                    for note in getattr(error,'__notes__',[]):
                        self.log.note(note)
                except OSError as log_error:
                    print(f'Could not append to diagnostic log: {log_error}',file=sys.stderr)
                print(f'Diagnostic log: {self.log.path}',file=sys.stderr)
                raise
            finally:
                os.umask(umask)
                try:
                    self.log.close()
                except OSError as log_error:
                    if failure is None:
                        raise
                    print(f'Could not close diagnostic log: {log_error}',file=sys.stderr)
                finally:
                    self.log=None
                    self.records=None

    def run_preboot(self, *, preview, layout=None, interactive=False, firmware=True):
        targets=[(name,False) for name in lifecycle.FIRMWARE_PATHS] if firmware else []
        journal=self.records.stage('preboot' if firmware else 'keyboard',targets) if self.records and not preview else nullcontext()
        if self.log:self.log.stage='preboot' if firmware else 'keyboard'
        with journal:
            status,layout=preboot.run(plan=preview,show_plan=preview,layout=layout,interactive=interactive,firmware=firmware,
                                       approve_firmware=self.approve_firmware)
            if self.records and not preview:
                self.records.data['keyboard']=layout
                self.records.data['pending_boot']=lifecycle.boot_id() if status is preboot.BootStatus.REBOOT_REQUIRED else None
        return status,layout

    def run_kernel_compatibility(self, approve):
        store=self.records
        current_boot=lifecycle.boot_id()
        path=str(preboot.FIRMWARE)
        with preboot.LOCK.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with store.stage('kernel-4k',[(path,False)]):
                result=preboot.configure_kernel(approve=approve, pending=store.data.get('pending_kernel_boot'),
                                                boot_id=current_boot)
                store.data['pending_kernel_boot']=current_boot if result in ('changed','reboot') else None
        return result

    def standalone_preboot(self, args):
        if args.plan or os.geteuid()!=0:
            return preboot.run(plan=args.plan,announce_host=True,layout=args.keyboard_layout)
        preboot.check_host(announce=True)
        with self.installation(self.snapshot()):
            return self.run_preboot(preview=False,layout=args.keyboard_layout,interactive=sys.stdin.isatty())

    def native_lab314(self, prefix):
        return any(path for name in ('opencv','py-opencv','spyder')
                   for path in (prefix/'conda-meta').glob(f'{name}-[0-9]*.json'))

    def change_hostname(self,old,new,previous=None):
        path=Path('/etc/hosts')
        if path.is_symlink() or Path('/etc/hostname').is_symlink():
            raise ValueError('symlinked /etc/hosts or /etc/hostname requires separate review')
        if socket.gethostname()!=old:
            raise ValueError('Hostname changed since the plan. Review the new setting.')
        original=path.read_text();updated=hosts_alias(original,previous or old,new)
        if self.records:
            for name in ('/etc/hosts','/etc/hostname'):
                backup=self.records.snapshot(name,backup=True)
                if backup['kind']=='file':
                    print(f'Hostname configuration backup: {self.records.directory/"original"/backup["sha256"]}')
        if updated==original:
            if new!=old:
                self.run(['hostnamectl','set-hostname',new])
            return
        metadata=path.stat();fd,tmp=tempfile.mkstemp(prefix='.rpi-hosts-',dir=path.parent)
        try:
            with os.fdopen(fd,'w') as stream:
                stream.write(updated);stream.flush();os.fsync(stream.fileno())
            os.chmod(tmp,stat.S_IMODE(metadata.st_mode));os.chown(tmp,metadata.st_uid,metadata.st_gid)
            if new!=old:
                self.run(['hostnamectl','set-hostname',new])
            try:os.replace(tmp,path)
            except BaseException:
                if new!=old:
                    self.run(['hostnamectl','set-hostname',old])
                raise
        finally:Path(tmp).unlink(missing_ok=True)

    def verify_hostname(self, name, changed):
        static=self.run(['hostnamectl','--static'],capture=True).stdout.strip()
        if (changed and static!=name) or socket.gethostname()!=name:
            raise ValueError(f'Hostname readback: selected={name}, static={static}, running={socket.gethostname()}')
        if changed and not any(line.split()[:1]==['127.0.1.1'] and name in line.split()[1:]
                               for line in (entry.partition('#')[0] for entry in Path('/etc/hosts').read_text().splitlines())):
            raise ValueError('Selected hostname is missing from the local /etc/hosts mapping')
        print(f'VERIFY PASS hostname: {name} (static: {static or "unset"})')

    def exists(self,path):return Path(path).exists() or Path(path).is_symlink()
    def environment(self,prefix):
        p=Path(prefix)
        if p.is_symlink():raise ValueError('symlinked environment refused: '+str(p))
        if not self.exists(p):return False
        message=f'Existing environment is incomplete at {p}. Preserve it and run setup-rpi.sh --manage --action diagnose.'
        metadata=p/'conda-meta'
        executables=[p/'bin/python']
        if p==Path('/opt/conda'):
            executables.append(p/'bin/conda')
        if (metadata.is_symlink() or not (metadata/'history').is_file() or (metadata/'history').is_symlink()
                or any(not os.access(path,os.X_OK) or not path.resolve().is_relative_to(p)
                       for path in executables)):
            raise ValueError(message)
        if os.geteuid()==0 and (p.stat().st_uid!=0 or p.stat().st_mode&0o022 or p.parent.resolve()!=p.parent):
            raise ValueError(f'Unsafe owner, mode or parent for environment {p}; preserve it for manual review.')
        records=list(metadata.glob('python-[0-9]*.json'))
        if len(records)!=1 or records[0].is_symlink():
            raise ValueError(message)
        try:
            record=json.loads(records[0].read_text())
            if not isinstance(record,dict) or record.get('name')!='python' or not record.get('version'):
                raise ValueError(message)
        except (OSError,ValueError) as error:
            raise ValueError(message) from error
        return True

    def wlan_state(self):
        return wlan.read_state(self)

    def snapshot(self):
        os_release={}
        for line in Path('/etc/os-release').read_text().splitlines():
            if '=' in line:
                k,v=line.split('=',1);os_release[k]=v.strip('"')
        model_path=Path('/proc/device-tree/model')
        model=model_path.read_text().rstrip('\0') if model_path.exists() else 'not a Raspberry Pi device-tree host'
        mem=re.search(r'^MemTotal:\s+(\d+)',Path('/proc/meminfo').read_text(),re.M)
        local=accounts.local_accounts()
        invoking=accounts.invoking_user(local)
        try:
            package=self.probe(['dpkg-query','-W','-f=${Status}','wolfram-engine'])
            wolfram=dict(engine_installed=package.returncode==0 and 'install ok installed' in package.stdout,cli=shutil.which('wolframscript'))
        except OSError:wolfram=dict(engine_installed=False,cli=shutil.which('wolframscript'))
        sudo={'policy':'Preserve NOPASSWD: ALL for the invoking/approved primary administrator','per_user_rule':'not present or unreadable'}
        if invoking:
            try:sudo['per_user_rule']=Path('/etc/sudoers.d',f'010_{invoking}-nopasswd').read_text().strip()
            except OSError:pass
        return dict(model=model,ram_mib=int(mem[1])//1024 if mem else None,
                    os=os_release.get('PRETTY_NAME','unknown'),codename=os_release.get('VERSION_CODENAME'),
                    os_id=os_release.get('ID'),architecture=platform.machine(),hostname=socket.gethostname(),
                    invoking_user=invoking,accounts={n:a for n,a in local.items() if a['uid']>=accounts.uid_min() and n!='nobody'},
                    ssh=lifecycle.ssh_status(self),sudo=sudo,wolfram=wolfram,
                    existing={p:self.exists(p) for p in ('/opt/conda','/opt/lab314','/opt/rpi','/usr/local/bin/rpi-share',
                        '/usr/local/bin/envrun','/etc/profile.d/sci-path.sh',lifecycle.NTP_FILE,
                        '/usr/local/share/applications/rpi-lab314-spyder.desktop')})


def parser():
    p=argparse.ArgumentParser(description=__doc__,
        epilog='Run --manage for maintenance, or --preboot [--plan | --dry-run] for Pi 5 preboot only.')
    p.add_argument('--wlan-country',type=str.upper,help='two-letter regulatory country (default: existing country or FI)')
    p.add_argument('--keyboard-layout',help='select an installed XKB layout code')
    p.add_argument('--profile-file',type=Path,help='local versioned installation preferences; CLI options override file settings')
    p.add_argument('--ntp-server',action='append',type=profiles.ntp_server,help='NTP hostname/IP; repeat to replace base defaults')
    p.add_argument('--profile',choices=['GENERAL','HOME','AALTO'])
    p.add_argument('--school',choices=['CHEM','custom'],help='compatibility option: AALTO accepts CHEM only')
    p.add_argument('--primary-user');p.add_argument('--additional-user',action='append',default=None,help='additional sudo-group account, repeat; does not receive a new per-user NOPASSWD rule')
    p.add_argument('--no-additional-users',action='store_true')
    p.add_argument('--recovery',choices=['create','keep','cancel'],help='explicit choice when the intended primary account is missing')
    p.add_argument('--hostname',type=hostname)
    p.add_argument('--ssh',choices=['keep','enable','disable'])
    p.add_argument('--chromium-policy',choices=('personal','shared'),
                   help='choose personal Chromium or regular browsing without a desktop keyring')
    for name in ('system','conda','lab314','spyder','hardware','wolfram','share','imaging'):
        p.add_argument('--'+name,action=argparse.BooleanOptionalAction,default=None)
    p.add_argument('--lab-prefix',type=canonical)
    p.add_argument('--ide-prefix',type=canonical)
    p.add_argument('--update-existing',action='store_true',help='explicitly request rolling lab314 and selected IDE maintenance')
    p.add_argument('--apt-upgrade',action='store_true',help='request a reviewed full OS upgrade on a configured system')
    p.add_argument('--kernel-4k',action=argparse.BooleanOptionalAction,default=None,
                   help='configure stock 4 KiB boot for Spyder on Pi 5; opting out leaves any existing boot setting in place')
    p.add_argument('--accept-boot-changes',action='store_true',
                   help='explicitly authorize the displayed I²C/SPI and selected Pi 5 kernel boot changes')
    config=p.add_mutually_exclusive_group()
    config.add_argument('--share-json',type=Path,help='use this local JSON instead of discovering a profile catalog')
    config.add_argument('--share-csv',type=Path,help='import this local CSV instead of discovering a profile catalog')
    config.add_argument('--share-example',action='store_true',help='explicitly use the bundled generic example')
    config.add_argument('--share-later',action='store_true',help='skip catalog discovery and leave configuration for later')
    p.add_argument('--share-user',action='append',default=[],help='local catalog owner; repeat; default is primary user')
    p.add_argument('--share-prefix',type=canonical,help='software prefix; keep existing /opt/lab client location when detected, otherwise /usr/local')
    p.add_argument('--replace-share-config',action='store_true')
    p.add_argument('--default-group')
    p.add_argument('--imaging-source',type=Path);p.add_argument('--imaging-app',action='append',default=[])
    p.add_argument('--imaging-approved',action='store_true',help='administrator confirms selected local Scientific Imaging source has been reviewed')
    p.add_argument('--accept-wolfram-license',action='store_true',
                   help='confirm that you reviewed and are authorized to accept the Wolfram terms')
    p.add_argument('--plan','--dry-run',action='store_true')
    p.add_argument('--yes',action='store_true',help='approve the displayed installation plan; new passwords still require a terminal')
    return p


def ask(prompt, default):
    answer=input(prompt+' ['+str(default)+']: ').strip()
    return answer or default


def ask_hostname(current, default):
    while True:
        selected=ask('Hostname',default)
        try:
            return current if selected==current else hostname(selected)
        except ValueError as exc:
            print(exc)


def share_source_selected(a):
    return any((a.share_json, a.share_csv, a.share_example, a.share_later))


class ShareCatalogError(ValueError):
    pass


def discover_share_catalogs(profile):
    """Find only the production filename for this profile in the local package layout."""
    filename = SHARE_NAMES[profile]
    package = BASE.parents[1] if BASE.parent.name == 'trixie' else BASE
    example = BASE/'config'/SHARE_EXAMPLE
    found = {}
    for directory in (Path.cwd(), HERE, package, package.parent):
        path = directory/filename
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved.name in SHARE_NAMES.values() and resolved.name != filename:
            continue
        if example.is_file() and resolved.samefile(example):
            continue
        found[resolved] = None
    return tuple(found)


def choose_share_source(a, candidates):
    a.share_json = a.share_csv = None
    a.share_example = a.share_later = False
    if candidates:
        for index, path in enumerate(candidates, 1):
            print(f'  {index}. External {a.profile} catalog: {path}')
    else:
        print(f'No matching {a.profile} catalog was found ({SHARE_NAMES[a.profile]}).')
    while True:
        options = 'number / ' if candidates else ''
        choice = ask(f'Share configuration: {options}manual / csv / template / later', 'later')
        for index, path in enumerate(candidates, 1):
            if choice == str(index):
                a.share_json = path
                return
        if choice in ('manual', 'csv'):
            path = input('Local catalog path: ').strip()
            if path:
                setattr(a, 'share_json' if choice == 'manual' else 'share_csv', Path(path))
                return
        elif choice == 'template':
            example = BASE/'config'/SHARE_EXAMPLE
            print(f'Generic public template: {example}')
            print('Run this in a private directory to create an editable catalog:')
            print('  '+shlex.join(['python3', str(BASE/'bin/rpi-share-builder.py'), '--csv',
                                   str(example.with_suffix('.csv')), '--output', SHARE_NAMES[a.profile]]))
            print('Edit it for your site, then select it manually or rerun setup to discover it.')
        elif choice == 'later':
            a.share_later = True
            a.default_group = None
            return
        else:
            print('Choose a listed catalog or enter manual, csv, template, or later.')


def load_share_catalog(a, discovered):
    path = a.share_json or a.share_csv or discovered
    example = BASE/'config'/('rpi-share.example.csv' if a.share_csv else SHARE_EXAMPLE)
    if a.share_example:
        path = example
    if path is None:
        return {}
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ShareCatalogError(f'Share catalog is missing or is not a regular file: {path}')
    try:
        public = example.is_file() and path.samefile(example)
        source = path.read_text(encoding='utf-8-sig')
        config = catalog.import_csv(source) if a.share_csv else catalog.loads(source)
        catalog.validate(config)
        if a.default_group:
            config['defaults']['group'] = a.default_group
            catalog.validate(config)
    except (OSError, ValueError, TypeError) as exc:
        raise ShareCatalogError(f'Cannot read or validate Share catalog at {path}. Review it locally with rpi-share-builder.py.') from exc
    label = ('bundled public example (edit before use)' if public else
             'external CSV' if a.share_csv else 'external production JSON')
    return dict(config=config, config_source=f'{label}: {path}', config_path=path,
                config_kind='csv' if a.share_csv else 'json',
                config_digest=sha256(json.dumps(config, sort_keys=True).encode()).hexdigest())


def interactive(a, state):
    print('\nRaspberry Pi Scientific Environment\n\n  1. GENERAL\n  2. HOME\n  3. AALTO')
    choice=ask('Profile GENERAL / HOME / AALTO','1').upper()
    a.profile={'1':'GENERAL','2':'HOME','3':'AALTO'}.get(choice,choice)
    if a.profile not in ('GENERAL','HOME','AALTO'):raise ValueError('unknown profile')


def customize(a, state, country=None):
    if a.profile=='AALTO':
        policy=accounts.aalto_account_plan(a.primary_user,a.additional_user,a.school,a.no_additional_users)
        a.school='CHEM'
        primary_default=policy['primary'];additional_default=' '.join(policy['additional'])
    else:
        primary_default='chem' if a.school=='CHEM' else state['invoking_user'] or ''
        additional_default='chem-it' if a.school=='CHEM' else '-'
    a.primary_user=ask('Primary local account',a.primary_user or primary_default)
    a.hostname=ask_hostname(state['hostname'],a.hostname or state['hostname'])
    a.ssh=ask('SSH keep / enable / disable',a.ssh or 'keep')
    chromium_default=lifecycle.selected_chromium(vars(a))
    while True:
        chromium=ask('Chromium policy personal / shared',chromium_default).lower()
        if chromium in ('personal','shared'):
            a.chromium_policy=chromium
            break
        print('Choose personal or shared for Chromium.')
    if country:
        while True:
            country=ask('WLAN regulatory country (two-letter ISO code)',country).upper()
            if country in wlan.countries():
                break
            print('Choose a valid two-letter WLAN country.')
    prompt='Additional sudo-group users (space separated; - means none)'
    if a.profile=='AALTO':prompt='Additional sudo-group users (required maintenance account is retained; - is not allowed)'
    if a.additional_user is not None:additional_default=' '.join(a.additional_user) or '-'
    additional=ask(prompt,additional_default)
    a.additional_user=[] if additional=='-' else additional.split()
    defaults = component_defaults(a)
    if not share_source_selected(a):
        defaults['share'] = defaults['share'] or bool(discover_share_catalogs(a.profile))
    elif a.share_json or a.share_csv or a.share_example:
        defaults['share'] = True
    for name,default in defaults.items():
        if getattr(a,name) is None:setattr(a,name,ask('Include '+name+'? y/n','y' if default else 'n').lower() in ('y','yes'))
    if a.spyder and not a.ide_prefix:
        prefix=ask('Separate Spyder IDE prefix (- uses the scientific environment)','-')
        if prefix!='-':a.ide_prefix=canonical(prefix)
    prefix=ask('Scientific Python environment path',str(a.lab_prefix or '/opt/lab314'))
    a.lab_prefix=canonical(prefix)
    if a.imaging:
        path=ask('Approved local Scientific Imaging source (- defers installation)',str(a.imaging_source or '-'))
        if path!='-':
            a.imaging_source=Path(path)
            a.imaging_app=ask('Application names (space separated)', ' '.join(a.imaging_app)).split()
            a.imaging_approved=ask('Has this application source/scope been reviewed? y/n','n').lower() in ('y','yes')
        else:
            a.imaging_source=None
            a.imaging_app=[]
            a.imaging_approved=False
    return country


def component_defaults(a):
    return dict(system=True,conda=True,lab314=True,spyder=True,hardware=True,
                wolfram=a.profile=='AALTO',share=a.profile!='GENERAL',imaging=bool(a.imaging_source))


def reuse_selection(a,data):
    """Restore accepted choices without freezing defaults or transient approvals."""
    if not data or not data.get('profile') or a.profile not in (None,data['profile']):
        return
    a.profile=data['profile']
    saved=data.get('preferences')
    if saved is None:
        # Older records contain effective values only. Preserve those choices on migration.
        saved={**data.get('selected',{}), 'ssh':data.get('ssh_policy'),
               'ntp_server':data.get('ntp','').split() or None}
    for name in (*profiles.COMPONENTS,'ssh','ntp_server','kernel_4k'):
        if getattr(a,name) is None and saved.get(name) is not None:
            setattr(a,name,saved[name])
    if a.chromium_policy is None:
        a.chromium_policy=lifecycle.selected_chromium(data)
    if data.get('pending_install') and a.keyboard_layout is None:
        a.keyboard_layout=saved.get('keyboard_layout')
    if a.primary_user is None:
        a.primary_user=data.get('primary')
    if a.additional_user is None and not a.no_additional_users:
        a.additional_user=data.get('additional', [name for name in data.get('accounts',{}) if name!=data.get('primary')])
    if a.lab_prefix is None and data.get('lab_prefix'):
        a.lab_prefix=canonical(data['lab_prefix'])
    if a.ide_prefix is None and data.get('ide_prefix'):
        a.ide_prefix=canonical(data['ide_prefix'])
    if a.share_prefix is None and data.get('share_prefix'):
        a.share_prefix=canonical(data['share_prefix'])
    if not a.share_user:
        a.share_user=data.get('share_owners',[])
    if not share_source_selected(a) and a.share is not False and data.get('pending_share'):
        source = data['pending_share']
        if source['kind'] == 'csv':
            a.share_csv = Path(source['path'])
        else:
            a.share_json = Path(source['path'])
        if a.default_group is None:
            a.default_group = source.get('default_group')
        a.replace_share_config |= bool(source.get('replace'))
    elif not share_source_selected(a) and data.get('share_later'):
        a.share_later=True
    saved_imaging=data.get('pending_imaging') or data.get('imaging')
    if not a.imaging_source and not a.imaging_app and saved_imaging:
        saved_source=Path(saved_imaging['source'])
        if saved_source.is_absolute():
            a.imaging_source=canonical(saved_source)
        a.imaging_app=saved_imaging['apps']
        if a.imaging is None:
            a.imaging=True


def resolve(a,state,host):
    if a.lab_prefix is None:
        a.lab_prefix=Path('/opt/lab314')
    if not a.profile:
        if not sys.stdin.isatty():raise ValueError('select --profile when interactive input is unavailable')
        interactive(a,state)
    if a.no_additional_users and a.additional_user:raise ValueError('conflicting additional-user options')
    if a.profile=='AALTO':
        policy=accounts.aalto_account_plan(a.primary_user,a.additional_user,a.school,a.no_additional_users)
        school,primary,extras=policy['school'],policy['primary'],policy['additional']
    else:
        school=a.school or 'custom'
        primary=a.primary_user or state['invoking_user']
        extras=[] if a.no_additional_users else a.additional_user if a.additional_user is not None else []
    if not primary:raise ValueError('primary account is ambiguous; use --primary-user explicitly')
    accounts.username(primary)
    if primary not in state['accounts']:
        choice=a.recovery
        if not choice and sys.stdin.isatty():
            print('Intended account '+primary+' is missing. Existing invoking account: '+str(state['invoking_user']))
            choice=ask('Recovery create / keep / cancel','cancel')
        if choice=='keep' and state['invoking_user']:primary=state['invoking_user']
        elif choice!='create':raise ValueError('missing primary account: choose --recovery create, keep or cancel')
    for name in extras:accounts.username(name)
    if len(set(extras))!=len(extras) or primary in extras:raise ValueError('duplicate primary/additional accounts')
    defaults=component_defaults(a)
    components={n:getattr(a,n) if getattr(a,n) is not None else v for n,v in defaults.items()}
    candidates = discover_share_catalogs(a.profile) if a.share is not False and not share_source_selected(a) else ()
    if a.share is None and (candidates or a.share_json or a.share_csv or a.share_example):
        components['share'] = True
    if a.profile in ('HOME','AALTO') and not components['share']:raise ValueError('HOME/AALTO include rpi-share; use --share-later to defer its configuration')
    existing_lab=host.environment(a.lab_prefix) if components['lab314'] or components['spyder'] else host.exists(a.lab_prefix)
    existing_conda=host.environment('/opt/conda')
    existing_rpi=host.environment('/opt/rpi') if components['hardware'] else host.exists('/opt/rpi')
    existing_ide=host.environment(a.ide_prefix) if a.ide_prefix else False
    if (components['lab314'] or components['hardware'] or a.ide_prefix) and not components['conda'] and not existing_conda:
        raise ValueError('selected environments require the existing Conda bootstrap')
    if components['spyder'] and not components['lab314'] and not existing_lab:
        raise ValueError('Spyder kernel integration requires lab314')
    if a.ide_prefix and not components['spyder']:raise ValueError('--ide-prefix requires Spyder selection')
    if a.ide_prefix and any(a.ide_prefix.is_relative_to(p) or p.is_relative_to(a.ide_prefix) for p in (a.lab_prefix,Path('/opt/rpi'),Path('/opt/conda'),Path('/opt/sci'))):
        raise ValueError('Spyder IDE prefix must be separate from application/scientific prefixes')
    if any(a.lab_prefix.is_relative_to(p) or p.is_relative_to(a.lab_prefix) for p in (Path('/opt/rpi'),Path('/opt/conda'),Path('/opt/sci'))):raise ValueError('lab314 prefix overlaps a protected environment')
    ssh=a.ssh or 'keep'
    if a.hostname and a.hostname!=state['hostname']:
        hostname(a.hostname)
    hostname_value=a.hostname or state['hostname']
    if (primary not in state['accounts'] or any(u not in state['accounts'] for u in extras)) and not a.plan and not sys.stdin.isatty():
        raise ValueError('new accounts require interactive password input; no changes made')
    selection = dict(config=None, config_source='DEFERRED: configure later')
    if len(candidates) > 1:
        selection.update(config_source='Selection required: multiple matching external catalogs',
                         share_candidates=candidates)
    else:
        selection.update(load_share_catalog(a, candidates[0] if candidates else None))
    if selection['config'] is not None:
        if not components['share']:raise ValueError('share configuration requires rpi-share selection')
    elif a.default_group and not candidates:raise ValueError('--default-group requires a selected configuration source')
    owners=a.share_user or [primary]
    if len(set(owners))!=len(owners):raise ValueError('duplicate catalog owners')
    for owner in owners:
        accounts.username(owner)
        if owner not in state['accounts'] and owner not in [primary,*extras]:raise ValueError('catalog owner is not an existing or planned local account')
    return dict(profile=a.profile,school=school,primary=primary,additional=extras,hostname=hostname_value,
                chromium_policy=lifecycle.selected_chromium(vars(a)),
                ssh=ssh,ntp=' '.join(a.ntp_server) if a.ntp_server else {'GENERAL':'pool.ntp.org time.cloudflare.com','HOME':'time.mikes.fi','AALTO':'ntp.aalto.fi'}[a.profile],
                components=components,existing_lab=existing_lab,existing_conda=existing_conda,existing_rpi=existing_rpi,
                existing_ide=existing_ide,native_lab=existing_lab and host.native_lab314(a.lab_prefix),
                existing_spyder=existing_lab and host.exists(a.lab_prefix/'bin/spyder'),
                **selection,owners=owners,
                existing_wolfram=bool(state.get('wolfram',{}).get('engine_installed') or state.get('wolfram',{}).get('cli')),
                share_prefix=a.share_prefix or (Path('/opt/lab') if host.exists('/opt/lab/bin/rpi-share') else Path('/usr/local')))


def stages(a,plan):
    c=plan['components'];result=[('accounts','KEEP existing passwords; create only missing approved accounts'),('profile','NTP '+plan['ntp']+'; SSH '+plan['ssh'])]
    if plan.get('wlan_country'):
        result.append(('wlan',f'Enable WLAN in {plan["wlan_country"]}'))
    if plan.get('desktop_account') and plan.get('keyboard_layout') in ('fi','se'):
        result.append(('terminal-shortcuts','Configure FI/SE zoom shortcuts if LXTerminal is the selected terminal'))
    if plan['chromium_policy']=='shared' or plan.get('chromium_cleanup'):
        result.append(('chromium',f"Apply Chromium policy: {plan['chromium_policy']}"))
    if c['system']:result.append(('system','ENSURE existing APT dependency lists'))
    if c['conda']:result.append(('conda','KEEP' if plan['existing_conda'] else 'INSTALL Miniforge through existing script'))
    if c['spyder'] and a.ide_prefix:result.append(('spyder-ide','KEEP' if plan['existing_ide'] and not a.update_existing else 'CREATE/UPDATE selected separate IDE'))
    if c['lab314']:
        action = ('UPDATE selected environment' if plan['existing_lab'] and a.update_existing
                  else 'RECONCILE missing manifest defaults' if plan['existing_lab'] else 'INSTALL Python 3.14')
        result.append(('lab314',action))
    if c['spyder'] and a.ide_prefix and plan['existing_lab'] and not plan['native_lab'] and not a.update_existing:result.append(('spyder-kernel','TARGET spyder-kernels only using selected IDE metadata'))
    if c['spyder'] and not a.ide_prefix:
        if plan['existing_spyder']:
            action='UPDATE with Scientific Python' if c['lab314'] and a.update_existing else 'KEEP integrated IDE'
            result.append(('spyder-desktop',action))
        elif c['lab314'] and not plan['existing_lab']:
            result.append(('spyder-desktop','INSTALL in Scientific Python'))
        elif plan['native_lab'] and plan.get('reconcile'):
            result.append(('spyder-add','ADD integrated Spyder only if installed packages can be held fixed'))
            result.append(('spyder-desktop','INSTALL integrated desktop launchers'))
        else:
            result.append(('spyder-desktop','DEFERRED: existing Scientific Python environment has no Spyder; migration is separate'))
    if c['lab314']:result.append(('shell','REUSE existing lab314 shell activation and envrun'))
    if c['hardware']:result.append(('hardware','KEEP' if plan['existing_rpi'] else 'INSTALL optional /opt/rpi through existing script'))
    if c['wolfram']:result.append(('wolfram','KEEP Wolfram Engine; reconcile GUI and CLI launchers' if plan['existing_wolfram'] else 'Install optional APT package and reconcile GUI and CLI launchers'))
    if c['share']:result.append(('share','INSTALL '+str(plan['share_prefix']/'bin/rpi-share')+'; '+plan['config_source']))
    if c['imaging']:result.append(('imaging','DEFER unless approved local source and explicit applications are available'))
    result.append(('verification','VERIFY selected components and report deferred GUI/hardware/network acceptance'))
    return result


def config_destination(owner):
    entry=accounts.local_accounts()[owner];home=Path(entry['home'])
    if not home.is_absolute() or home.is_symlink() or not home.is_dir():raise ValueError('unsafe/missing account home')
    directory=home/'.config';destination=directory/'rpi-share.json'
    if directory.is_symlink() or destination.is_symlink():raise ValueError('symlinked user configuration refused')
    if directory.exists() and directory.stat().st_uid not in (0,entry['uid']):raise ValueError('configuration directory belongs to another user')
    if destination.exists() and not destination.is_file():raise ValueError('Share configuration must be a regular file: '+str(destination))
    return entry,directory,destination


def install_config(plan,replace=False):
    if plan['config'] is None:return 'DEFERRED: no catalog selected'
    data=json.dumps(plan['config'],ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    destinations=[config_destination(owner) for owner in plan['owners']]
    outcomes = []
    for entry,directory,path in destinations:
        existing = path.exists()
        if existing:
            if path.resolve() == plan.get('config_path'):
                outcomes.append(f'KEPT selected source {path}')
                continue
            if not replace:
                outcomes.append(f'KEPT existing {path}')
                continue
            try:
                same = catalog.same_value(catalog.loads(path.read_text(encoding='utf-8-sig')), plan['config'])
            except ValueError:
                same = False  # Explicit replacement can repair an invalid existing JSON.
            if same:
                outcomes.append(f'KEPT matching {path}')
                continue
        directory.mkdir(mode=0o700,exist_ok=True);os.chown(directory,entry['uid'],entry['gid'])
        catalog.atomic_write(path,data,replace and existing);os.chown(path,entry['uid'],entry['gid'])
        outcomes.append(f'{"REPLACED" if existing else "CONFIGURED"} {path}')
    return '; '.join(outcomes)


def apply_wlan(host,plan,store):
    detail=wlan.configure(host,plan['wlan_country'],expected=plan['previous_wlan_country'],
                          data=store.data if store else None)
    if store and not detail.startswith('DEFERRED'):
        store.data.pop('pending_wlan',None)
    return detail


def apply(a,plan,state,host):
    if os.geteuid()!=0:raise ValueError('run setup through sudo to apply; --plan needs no root')
    if not (re.search(r'Raspberry Pi [45]',state['model']) and state['codename']=='trixie' and state['os_id'] in ('debian','raspbian') and state['architecture'] in ('aarch64','arm64')):
        raise ValueError('apply requires Raspberry Pi 4/5, Raspberry Pi OS Trixie 64-bit')
    results=[]
    if plan.get('preboot'):
        results.append(('preboot','PASS','I²C/SPI device nodes and stored keyboard configuration verified'))
    store=getattr(host,'records',None)
    previous_lab=(store.data['components'].get('lab314',{}).get('status') if store else None)
    host.env.update(PRIMARY_USER=plan['primary'],EXTRA_SUDO_USERS=' '.join(plan['additional']),
                    PRE_ACCOUNTS_MANAGED='1',NTP_PRIMARY=plan['ntp'],SSH_POLICY=plan['ssh'],
                    DO_APT_UPGRADE='0',INSTALL_APT_SPYDER='0')
    if a.ide_prefix and not plan['native_lab']:host.env['LAB314_SPYDER_PYTHON']=str(a.ide_prefix/'bin/python')
    core_failed=False
    def shell(name,*args):host.run(['bash',HERE/name,*args])
    def update_ide():
        parent=a.ide_prefix.parent
        if not parent.is_dir():raise ValueError('IDE prefix parent must already exist')
        record=Path(tempfile.mkdtemp(prefix='.rpi-ide-records-',dir=parent))/'operation'
        host.run(['/usr/bin/python3','-IB',HERE/'update_lab314.py','--ide-prefix',a.ide_prefix,'--apply','--record-dir',record])
    for name,description in stages(a,plan):
        if core_failed and name!='verification':
            results.append((name,'BLOCKED','earlier required component failed'))
            if store:
                store.data['components'].setdefault(name,{}).update(status='blocked',updated=lifecycle.now())
                store.save()
            continue
        if getattr(host,'log',None):
            host.log.stage=name
        try:
            with lifecycle.track_stage(store,host,name,a,plan,state) if store else nullcontext():
                detail=''
                if name=='accounts':
                    if store and plan.get('reconcile'):
                        lifecycle.reconcile_accounts(store,host,plan,state,accounts.ensure_user)
                    else:
                        accounts.ensure_user(plan['primary'],admin=True,passwordless=True)
                        for user in plan['additional']:accounts.ensure_user(user,admin=True)
                    if plan.get('continue_hostname') and plan['hostname']==state['hostname']:
                        host.change_hostname(state['hostname'],plan['hostname'],plan['continue_hostname']['previous'])
                    elif plan['hostname']!=state['hostname']:
                        host.change_hostname(state['hostname'],plan['hostname'])
                        print('Hostname changed; reconnect using the new name. A reboot may be needed for all services.')
                    if store and hasattr(host,'verify_hostname'):
                        host.verify_hostname(plan['hostname'],bool(store.data.get('pending_hostname')))
                        store.data.pop('pending_hostname',None)
                elif name=='profile':
                    script='pre_home.sh' if plan['profile']=='HOME' else 'pre_aalto.sh' if plan['profile']=='AALTO' else 'pre_profile.sh'
                    if store:
                        lifecycle.reconcile_profile(store,host,plan)
                    else:
                        shell(script,*(['GENERAL'] if script=='pre_profile.sh' else []))
                elif name=='wlan':
                    detail=apply_wlan(host,plan,store)
                elif name=='terminal-shortcuts':
                    user=plan['desktop_account']
                    target=plan.get('desktop_user') or lifecycle.terminal_target(host.snapshot(),user)
                    detail=(lifecycle.apply_terminal_shortcuts(store,host,target,plan['keyboard_layout']) if target
                            else f'DEFERRED: desktop account {user} unavailable for LXTerminal configuration.')
                elif name=='chromium':
                    detail=lifecycle.chromium_policy(store or Store(),mode=plan['chromium_policy'],apply=True)
                elif name=='system':
                    if store:
                        lifecycle.reconcile_system(store,host,state['model'])
                    else:
                        shell('install_rpi_base.sh')
                elif name=='conda':
                    if not plan['existing_conda']:
                        if store:
                            with lifecycle.command_environment(host,RPI_CONDA_COMMANDS_MANAGED='1'):
                                shell('install_conda_base.sh')
                        else:shell('install_conda_base.sh')
                    if store:lifecycle.reconcile_conda(store)
                elif name=='spyder-ide':
                    if not plan['existing_ide'] or a.update_existing:update_ide()
                elif name=='lab314':
                    if not plan['existing_lab'] or a.update_existing:
                        flags = ['--external-spyder'] if a.ide_prefix else [] if plan['components']['spyder'] else ['--without-spyder']
                        shell('create_lab314_env.sh','--prefix',a.lab_prefix,*flags)
                    elif store:
                        record=store.directory/f'lab314-defaults-{uuid4().hex}'
                        host.run([a.lab_prefix/'bin/python','-IB',HERE/'update_lab314.py','--prefix',a.lab_prefix,
                                  '--add-defaults','--apply','--record-dir',record])
                        flags=['--require-spyder'] if plan['existing_spyder'] and not a.ide_prefix else []
                        if previous_lab in ('running','failed'):
                            flags.append('--functional')
                        with lifecycle.inspection(host):
                            host.run([a.lab_prefix/'bin/python','-IB',HERE/'check_lab314.py','--prefix',a.lab_prefix,*flags])
                        detail='Scientific Python verified; installed packages retained and missing defaults reconciled'
                    if store:
                        lifecycle.reconcile_scientific_browser(store,host,a.lab_prefix)
                elif name=='spyder-kernel':shell('create_lab314_env.sh','--prefix',a.lab_prefix,'--package','spyder-kernels')
                elif name=='spyder-add':
                    record=Path(tempfile.mkdtemp(prefix='spyder-add-',dir=store.directory))/'operation'
                    host.run([a.lab_prefix/'bin/python','-IB',HERE/'update_lab314.py','--prefix',a.lab_prefix,
                              '--add-spyder','--apply','--record-dir',record])
                elif name=='spyder-desktop':
                    if description.startswith('DEFERRED'):
                        detail=description
                    elif a.lab_prefix==Path('/opt/lab314'):
                        changes=lifecycle.install_spyder_launcher(host,store)
                        detail=('Desktop and terminal launcher definitions reconciled' if 'updated' in changes
                                else 'Existing launchers checked')+'; graphical acceptance pending'
                elif name=='shell':
                    if a.lab_prefix!=Path('/opt/lab314'):
                        detail='DEFERRED default autoactivation for custom prefix; use existing explicit activation'
                    if store:
                        lifecycle.reconcile_shell(store,a.lab_prefix)
                    else:
                        if a.lab_prefix==Path('/opt/lab314'):shell('enable_lab314_autoactivate_rpi.sh')
                        shell('install_envrun.sh')
                elif name=='hardware':
                    if store:
                        lifecycle.install_missing_apt(host,lifecycle.APT_CAMERA)
                    if not plan['existing_rpi']:
                        if store:
                            with lifecycle.command_environment(host,RPI_HARDWARE_APT_READY='1'):
                                shell('create_rpi_env.sh')
                        else:shell('create_rpi_env.sh')
                    elif store:
                        lifecycle.reconcile_file(store,lifecycle.HARDWARE_BRIDGE,b'/usr/lib/python3/dist-packages\n',0o644)
                elif name=='wolfram':
                    if plan['existing_wolfram'] and not state.get('wolfram',{}).get('engine_installed'):
                        detail='DEFERRED existing Wolfram outside the APT package; review its desktop entries locally.'
                    else:
                        detail=lifecycle.install_wolfram(
                            host, store, installed=plan['existing_wolfram'], reviewed=plan.get('wolfram_reviewed'),
                            confirm=lambda: sys.stdin.isatty() and
                            ask('Install Wolfram under the license terms shown above? y/N','n').lower() in ('y','yes'))
                elif name=='share':
                    if store:
                        for source,destination,mode in lifecycle.share_definitions(plan['share_prefix']):
                            lifecycle.reconcile_definition(store,source,destination,mode)
                    else:
                        shell('install_rpi_share.sh','--prefix',plan['share_prefix'])
                    detail=install_config(plan,a.replace_share_config)
                    if store:
                        store.data.pop('pending_share',None)
                elif name=='imaging':
                    source=a.imaging_source
                    missing=[app for app in a.imaging_app if not host.exists(lifecycle.app_record(app))] if store else a.imaging_app
                    approved=a.imaging_approved and not store
                    previous=(store.data.get('pending_imaging') or store.data.get('imaging',{})) if store else {}
                    if source and previous.get('source')==str(source.resolve()) and (source/'scripts/install').is_dir():
                        approved=(a.imaging_app==previous.get('apps') and
                                  lifecycle.imaging_tool_hashes(source)==previous.get('tool_hashes'))
                    if a.imaging_app and not missing:
                        results.append((name,'PASS','KEEP selected imaging applications'));continue
                    if not source or not approved or not missing or not (source/'scripts/install/01-install.sh').is_file():
                        if store:store.data['components'][name]['status']='deferred'
                        results.append((name,'DEFERRED','approved local source and explicit --imaging-app selections required'));continue
                    argv=[value for app in missing for value in ('--app',app)]
                    host.run(['bash',source/'scripts/install/01-install.sh',*argv])
                    host.run(['bash',source/'scripts/install/02-diagnose.sh',*argv])
                elif name=='verification':
                    errors=[];c=plan['components']
                    verify=[]
                    outcomes={component:status for component,status,_ in results}
                    if c['lab314'] or (c['spyder'] and plan['existing_lab']):
                        if outcomes.get('lab314') in ('FAIL','BLOCKED'):
                            print('VERIFY BLOCKED Scientific Python (installation did not complete)')
                        else:
                            flags = ['--require-spyder'] if c['spyder'] and not a.ide_prefix and (
                                plan['existing_spyder'] or not plan['existing_lab'] or outcomes.get('spyder-add')=='PASS') else []
                            verify.append(['bash',HERE/'verify_rpi_lab314.sh','--science-only','--prefix',a.lab_prefix,*flags])
                    for component,command in (('hardware',['bash',HERE/'verify_rpi_env.sh']),
                                              ('share',[plan['share_prefix']/'bin/rpi-share','--check'])):
                        if not c[component]:
                            continue
                        if outcomes.get(component) in ('FAIL','BLOCKED'):
                            print(f'VERIFY BLOCKED {component} (installation did not complete)')
                        elif outcomes.get(component) is None:
                            print(f'VERIFY NOT INSTALLED {component}')
                        elif store and not host.exists('/opt/rpi' if component=='hardware' else plan['share_prefix']/'bin/rpi-share'):
                            print(f'VERIFY NOT INSTALLED {component}')
                            errors.append(f'{component} files missing after installation')
                        else:
                            verify.append(command)
                    if outcomes.get('accounts')=='PASS':
                        verify.extend([['hostnamectl','--static'],['sudo','-n','-u',plan['primary'],'sudo','-n','true']])
                    else:
                        print('VERIFY BLOCKED accounts (configuration did not complete)')
                    if outcomes.get('profile')=='PASS':
                        verify.extend([['systemctl','is-active','systemd-timesyncd'],['timedatectl','show','-p','NTPSynchronized','--value']])
                        if plan['ssh']=='enable':verify.append(['systemctl','is-active','ssh'])
                    else:
                        print('VERIFY BLOCKED profile (configuration did not complete)')
                    for argv in verify:
                        try:
                            check=host.run(argv,capture=True)
                            if 'NTPSynchronized' in argv and check.stdout.strip()!='yes':
                                raise ValueError('time synchronization pending')
                            print('VERIFY PASS',' '.join(str(x) for x in argv),check.stdout.strip())
                        except (ValueError,OSError,subprocess.SubprocessError) as exc:
                            print('VERIFY FAIL',' '.join(str(x) for x in argv))
                            errors.append(str(exc))
                    if errors:raise ValueError('; '.join(errors))
                    detail='Completed components checked; GUI, camera performance and network access require acceptance'
                if store and detail.startswith('DEFERRED'):
                    store.data['components'][name]['status']='deferred'
            results.append((name,'DEFERRED' if detail.startswith('DEFERRED') else 'PASS',detail or description))
        except (ValueError,OSError,subprocess.SubprocessError) as exc:
            message=redact(exc)
            results.append((name,'FAIL',message))
            print('FAILED STAGE '+name+': '+message,file=sys.stderr)
            if getattr(host,'log',None):
                try:
                    host.log.note(f'FAILED STAGE {name}: {message}')
                    for note in getattr(exc,'__notes__',[]):
                        host.log.note(note)
                except OSError as error:
                    print(f'Could not append to diagnostic log: {error}',file=sys.stderr)
            if name in ('accounts','profile','system','conda','spyder-ide','lab314','spyder-kernel','spyder-add','hardware'):core_failed=True
    print('\nINSTALLATION SUMMARY')
    for key in ('profile','school','primary','additional','ntp','config_source'):
        print(key+': '+str(plan[key]))
    current=socket.gethostname() if isinstance(host,Host) else host.snapshot()['hostname']
    print(f"Hostname selected: {plan['hostname']} (running: {current})")
    if plan.get('locale_summary'):
        print('Locales:',plan['locale_summary'])
    print(f"Chromium policy: {lifecycle.chromium_description(plan['chromium_policy'])}")
    if plan.get('wlan_country'):
        print(f"WLAN country selected: {plan['wlan_country']}")
    lifecycle.report_ssh(plan['ssh'],lifecycle.ssh_status(host))
    print('sudo: existing approved NOPASSWD policy preserved; primary admin verified separately')
    for name,status,detail in results:print(status,name,detail)
    if store:
        if store.reconciled:
            for path,outcome in sorted(store.reconciled.items()):
                print(f'CONFIGURATION {outcome}: {path}')
        else:
            print('Managed file reconciliation: no changes needed.')
    if plan.get('kernel_compatibility'):
        print(plan['kernel_compatibility'])
    if plan['components']['spyder']:
        lifecycle.spyder_pending()
        if host.exists(a.lab_prefix/'conda-meta/qt-webengine-5.15.15-h6406779_4.json'):
            print('LIMITED standalone QtWebEngine: this build failed the standalone renderer test on Trixie.')
            print('Verify formatted Spyder Help with Ctrl+I. If it is blank, use Plain Text or an external browser.')
    for name,selected in plan['components'].items():
        if not selected:print('NOT SELECTED',name)
    if any(status in ('FAIL','BLOCKED') for _,status,_ in results):
        print('Retry: review the first failed stage, use setup-rpi.sh --manage --action diagnose, then rerun setup after correction. Preserve incomplete prefixes.')
        return 1
    print('A reboot is recommended after successful installation. Run sudo reboot when ready.')
    return 0


def show_plan(a, plan, state, boot_status, host):
    print('\nINSTALLATION PLAN')
    print(f"profile: {plan['profile']}" + (' (CHEM)' if plan['profile']=='AALTO' else ''))
    print('\nSystem configuration')
    if proposal:=plan.get('locale_plan'):
        locale_setup.describe(proposal)
    if error:=plan.get('locale_error'):
        print('LIMITED locales:',error)
    if plan.get('keyboard_layout'):
        print(f"  Keyboard layout          {plan['keyboard_layout']}")
    if plan.get('desktop_account') and plan.get('keyboard_layout') in ('fi','se'):
        print(f"  LXTerminal zoom          {plan['desktop_account']} (if LXTerminal is selected)")
    if boot_status is preboot.BootStatus.READY:
        print('  I²C and SPI              Ready')
    elif boot_status is preboot.BootStatus.REBOOT_REQUIRED:
        print('  I²C and SPI              Reboot required before software installation')
    elif boot_status is preboot.BootStatus.DEVICES_MISSING:
        print('  I²C and SPI              Missing device nodes must be resolved first')
    else:
        print('  Pi 5 preboot             Applies to Raspberry Pi 5 Model B on Trixie')
    if preboot.is_pi5_model(state['model']):
        kernel_selected=a.kernel_4k if a.kernel_4k is not None else plan['components']['spyder']
        print('  Pi 5 kernel              '+(plan.get('kernel_status','Verification pending')
              if kernel_selected else 'Keep current boot selection'))
    if plan.get('wlan_country'):
        previous=plan.get('previous_wlan_country')
        change=f' (currently {previous})' if previous and previous!=plan['wlan_country'] else ''
        print('  Ethernet and Wi-Fi       Keep Ethernet; enable WLAN in '+plan['wlan_country']+change)
        if plan.get('wlan_readback'):
            print('  WLAN readback            '+plan['wlan_readback'])
    elif a.plan:
        print('  Ethernet and Wi-Fi       Inspect target WLAN country; default to FI if unset')
    for label, value in (('Hostname',plan['hostname']),('NTP',plan['ntp']),
                         ('Full OS upgrade',plan.get('os_upgrade_status','First-install stage'))):
        print(f'  {label:<24} {value}')
    lifecycle.report_ssh(plan['ssh'], state['ssh'], '  ')
    if plan['ssh']!='keep':
        print('    The approved policy applies to ssh.service. The current ssh.socket setting is retained.')
    print(f"  Chromium policy          {lifecycle.chromium_description(plan['chromium_policy'])}")
    if plan['chromium_policy']=='personal' and plan.get('chromium_cleanup'):
        print('    Restore any remaining installer-owned Chromium shared overrides.')
    for label, users in (('Primary administrator',[plan['primary']]),('Additional administrator',plan['additional'])):
        for user in users:
            action='keep password' if user in state['accounts'] else 'create, set password interactively'
            print(f'  {label:<24} {user} ({action})')
    actions=dict(stages(a,plan))
    def label_action(key):
        action=actions.get(key,'No')
        status=action.split()[0]
        return {'ENSURE':'Install missing dependencies','KEEP':'Keep existing',
                'INSTALL':'Install','CHECK':'Install if available'}.get(status,action)
    print('\nScientific software')
    for label, key in (('System dependencies','system'),('Conda / Miniforge','conda'),
                       ('Scientific Python 3.14','lab314'),('Spyder IDE','spyder-ide' if a.ide_prefix else 'spyder-desktop'),
                       ('Raspberry Pi Python 3.13','hardware')):
        print(f'  {label:<24} {label_action(key)}')
    if plan['components']['lab314']:
        print('  Scientific reporting     ReportLab, pypdf, Jinja2 (offline PDF and HTML)')
    print('\nOptional components')
    for label, key in (('Wolfram Engine','wolfram'),('Scientific Imaging','imaging'),('rpi-share','share')):
        print(f'  {label:<24} {label_action(key)}')
    if plan['components']['wolfram'] and not plan['existing_wolfram']:
        wolfram.show_preflight(host,plan.get('wolfram_candidate'))
    if plan['components']['share']:
        print(f"  Share configuration      {plan['config_source']}; owners: {', '.join(plan['owners'])}")
        for path in plan.get('share_candidates', ()):
            print(f'    Matching external catalog: {path}')
        if plan.get('share_candidates'):
            print('    Select a catalog interactively or use --share-json PATH / --share-later.')
        if plan['config'] is not None:
            print('    Existing catalogs: '+('replacement authorized' if a.replace_share_config else 'keep'))
        elif not plan.get('share_candidates') and not a.share_later:
            print(f'    No matching {plan["profile"]} production catalog. Use --share-json PATH to select a local file.')


def main(argv=None,host=None):
    argv=sys.argv[1:] if argv is None else list(argv)
    if '--manage' in argv:
        return lifecycle.main(argv,host or Host())
    if '--preboot' in argv:
        if '--plan' in argv or '--dry-run' in argv:
            return preboot.main(argv)
        return preboot.main(argv,runner=(host or Host()).standalone_preboot)
    a=profiles.parse_arguments(parser(),argv);host=host or Host();state=host.snapshot()
    a.reconcile_without_prompt=not argv
    firmware=preboot.is_pi5_model(state['model'])
    target=((firmware or state['model'].startswith('Raspberry Pi 4 ')) and state['codename']=='trixie'
            and state['os_id'] in ('debian','raspbian') and state['architecture'] in ('aarch64','arm64'))
    if not a.plan and target and os.geteuid()!=0 and hasattr(host,'installation'):
        raise ValueError('Run setup through sudo to configure the system.')
    if a.keyboard_layout is not None and not target:
        # The XKB registry and an explicit code can still be validated in an offline plan.
        if not a.plan:
            raise ValueError('Keyboard selection requires a Raspberry Pi OS Trixie target.')
        keyboard=preboot.runpy.run_path(str(preboot.SOURCE))
        if a.keyboard_layout not in keyboard['layouts']():
            raise ValueError(f'Unknown XKB keyboard layout: {a.keyboard_layout!r}')
    journal=host.installation(state) if target and not a.plan and hasattr(host,'installation') else nullcontext()
    with journal:
        return normal_setup(a,state,host,target,firmware)


def normal_setup(a,state,host,target,firmware):
    boot_status=None
    store=getattr(host,'records',None)
    data=store.data if store else None
    if a.plan and target and isinstance(host,Host) and os.geteuid()==0:
        data=Store().load()
    saved=(data or {}) if a.profile in (None,(data or {}).get('profile')) else {}
    established=bool(saved.get('profile'))
    explicit_ssh=a.ssh is not None
    source_can_change=not share_source_selected(a)
    explicit_hostname=a.hostname is not None
    reuse_selection(a,saved)
    if not a.profile and not sys.stdin.isatty() and a.plan:
        a.profile='GENERAL'
    if saved.get('pending_install') and not a.update_existing:
        a.update_existing=bool(saved.get('pending_update_existing'))
    layout=a.keyboard_layout
    if isinstance(host,Host):
        host.approve_firmware=lambda: a.accept_boot_changes or (
            sys.stdin.isatty() and ask('Approve displayed I²C/SPI boot changes? y/N','n').lower() in ('y','yes'))
    if target and (a.plan or firmware):
        print('EARLY HARDWARE PREVIEW',flush=True)
        status,layout=host.run_preboot(preview=True,layout=layout,firmware=firmware)
        if firmware:
            boot_status=status
        if not a.plan and firmware and status is preboot.BootStatus.DEVICES_MISSING:
            preboot.report_reboot(status)
            return 1
    if not a.profile and sys.stdin.isatty():
        interactive(a,state)
    interactive_review=not a.plan and not a.yes and sys.stdin.isatty()
    current_name=state['hostname']
    pending_host=saved.get('pending_hostname',{})
    continuing_host=(not explicit_hostname and pending_host.get('name') and
                     current_name in (pending_host.get('previous'),pending_host['name']))
    hostname_drift=bool(pending_host and not continuing_host and not explicit_hostname)
    if continuing_host:
        a.hostname=hostname(pending_host['name'])
    elif not explicit_hostname and interactive_review and (not established or hostname_drift):
        a.hostname=ask_hostname(current_name,current_name)

    country=a.wlan_country
    previous = None
    wlan_state=None
    approved_country=None
    wlan_matches=True
    if target and hasattr(host,'wlan_state'):
        wlan_state=host.wlan_state()
        previous=wlan.existing_country(wlan_state)
        pending=saved.get('pending_wlan',{})
        approved_country=pending.get('country') or saved.get('wlan_country')
        if approved_country not in wlan.countries():
            approved_country=None
        wlan_matches=bool(approved_country and (
            wlan.ready(wlan_state,approved_country) or
            (wlan.deferred(wlan_state) and previous in (None,approved_country))))
        default=approved_country if wlan_matches or pending.get('previous')==previous else None
        default=default or previous or 'FI'
        if not country and interactive_review and not wlan_matches:
            while True:
                country=ask('WLAN regulatory country (two-letter ISO code)',default).upper()
                if country in wlan.countries():
                    break
                print('Choose a valid two-letter WLAN country.')
        country = country or default
    if country and country not in wlan.countries():
        raise ValueError('Invalid WLAN regulatory country')
    locale_fields={}
    if hasattr(host,'locale_requests'):
        try:
            locale_store=store or Store()
            if not store:
                locale_store.data=data
            locale_fields['locale_plan']=locale_setup.plan(host,locale_store)
        except (ValueError,OSError,subprocess.SubprocessError) as exc:
            locale_fields['locale_error']=str(exc)
    while True:
        try:
            plan=resolve(a,state,host)
        except ShareCatalogError as exc:
            if a.plan or a.yes or not sys.stdin.isatty() or not source_can_change:
                raise
            print(exc)
            choose_share_source(a, discover_share_catalogs(a.profile))
            continue
        candidates = plan.get('share_candidates', ())
        if candidates and not a.plan and sys.stdin.isatty():
            choose_share_source(a, candidates)
            continue
        desktop_account=(plan['primary'] if a.profile=='AALTO' else state['invoking_user']) if target else None
        plan.update(preboot=target and firmware, keyboard_layout=layout,
                    desktop_account=desktop_account,
                    desktop_user=lifecycle.terminal_target(state,desktop_account) if desktop_account else None,
                    reconcile=bool(established or any(state.get('existing',{}).values())) and bool(store),
                    explicit_ssh=explicit_ssh,
                    continue_hostname=pending_host if continuing_host and plan['hostname']==pending_host['name'] else None)
        plan['chromium_cleanup']=any(
            destination in (data or {}).get('paths',{}) for _,destination in lifecycle.CHROMIUM_FILES)
        plan.update(wlan_country=country,previous_wlan_country=previous)
        plan.update(locale_fields)
        if wlan_state and country:
            if wlan.ready(wlan_state,country) or wlan.deferred(wlan_state):
                plan['wlan_readback']=wlan.verify(wlan_state,country,saved)
            else:
                plan['wlan_readback']=(f"boot={wlan_state['stored'] or 'unset'}, global={wlan_state['country'] or 'unknown'}, "
                                       f"radio={wlan_state['radio'] or 'unknown'}; verification pending")
        if plan['components']['wolfram'] and not plan['existing_wolfram']:
            plan['wolfram_candidate']=wolfram.candidate(host)
        if (plan['components']['imaging'] and a.imaging_source and a.imaging_app
                and (a.imaging_source/'scripts/install').is_dir()):
            source=str(a.imaging_source.resolve())
            hashes=lifecycle.imaging_tool_hashes(a.imaging_source)
            if hashes:
                selection=dict(source=source,apps=a.imaging_app,tool_hashes=hashes)
                if a.imaging_approved or selection==(saved.get('pending_imaging') or saved.get('imaging')):
                    plan['imaging_selection']=selection
        if target and firmware and isinstance(host,Host):
            plan['kernel_status']=preboot.kernel_status((data or {}).get('pending_kernel_boot'),lifecycle.boot_id())
        if a.plan:
            plan['os_upgrade_status']='Requested' if a.apt_upgrade else 'Automatic for reliably identified first installations'
        elif store:
            plan['os_upgrade_status']=os_upgrade.description(data)
        show_plan(a,plan,state,boot_status,host)
        if a.plan:
            print('PLAN ONLY: no accounts, passwords, packages, host settings, configuration files or environments changed.')
            return 0
        if candidates:
            raise ValueError('Multiple matching Share catalogs require --share-json PATH or --share-later.')
        share_unchanged=(plan['config'] is None and not saved.get('pending_share') or
                         saved.get('pending_install') and plan.get('config_digest') and
                         plan['config_digest']==saved.get('pending_share',{}).get('digest'))
        wolfram_unchanged=(not plan.get('wolfram_candidate') or
                           vars(plan['wolfram_candidate'])==saved.get('pending_wolfram'))
        if wolfram_unchanged or a.accept_wolfram_license:
            plan['wolfram_reviewed']=plan.get('wolfram_candidate')
        if a.yes or (established and getattr(a,'reconcile_without_prompt',False) and share_unchanged
                     and wolfram_unchanged and not hostname_drift and wlan_matches
                     and country in (None,approved_country)):
            if established:
                print('Reconciling saved installation choices with current definitions. Package updates are available in --manage.')
            break
        can_choose_share = plan['components']['share'] and source_can_change
        if can_choose_share and plan['config'] is None and not a.share_later:
            print('Choose share to select a local catalog or view the generic template. Approve the plan to configure later.')
        if plan.get('wolfram_candidate'):
            print('Approving this plan authorizes installing the displayed Wolfram package under the linked terms.')
        prompt = 'Apply this installation plan? y/N/customize' + ('/share' if can_choose_share else '')
        choice=ask(prompt,'n').lower() if sys.stdin.isatty() else 'n'
        if choice in ('y','yes'):
            plan['wolfram_reviewed']=plan.get('wolfram_candidate')
            break
        if choice in ('c','customize'):
            country=customize(a,state,country)
            explicit_ssh=True
            continue
        if choice == 'share' and can_choose_share:
            choose_share_source(a, discover_share_catalogs(a.profile))
            continue
        print('Cancelled software installation.')
        return 0
    if store:
        lifecycle.save_selection(store,a,plan,state)
        plan['confirm_significant']=lambda description: a.yes or (
            sys.stdin.isatty() and ask(description+'? y/N','n').lower() in ('y','yes'))
        if hasattr(host,'locale_requests'):
            if getattr(host,'log',None):
                host.log.stage='locales'
            try:
                if plan.get('locale_error'):
                    raise ValueError(plan['locale_error'])
                plan['locale_summary']=lifecycle.apply_locales(store,host,plan['locale_plan'])
            except (ValueError,OSError,subprocess.SubprocessError) as exc:
                plan['locale_summary']='LIMITED '+redact(exc)
            print('Locales:',plan['locale_summary'])
    if target:
        print('EARLY HARDWARE SETUP',flush=True)
        status,layout=host.run_preboot(preview=False,layout=a.keyboard_layout,
                                      interactive=sys.stdin.isatty(),firmware=firmware)
        plan['keyboard_layout']=layout
        if firmware:
            boot_status=status
        if firmware and status is preboot.BootStatus.DEVICES_MISSING:
            preboot.report_reboot(status)
            return 1
    if store:
        upgrade=data.get('os_upgrade',{})
        first=upgrade.get('status')=='not-started' or (
            upgrade.get('status') in ('running','interrupted') and upgrade.get('first_install'))
        if (first or a.apt_upgrade) and not os_upgrade.reboot_pending(data):
            def approve_upgrade():
                return first or a.yes or (sys.stdin.isatty() and ask('Apply this reviewed OS upgrade? y/N','n').lower() in ('y','yes'))
            if not os_upgrade.run(host,store,lifecycle.apt_inventory,approve_upgrade,os_upgrade.confirm_removals,
                                  first_install=first):
                return 1
        else:
            print('Raspberry Pi OS Update:',os_upgrade.description(data))
    kernel_reboot=False
    if target and firmware and hasattr(host,'run_kernel_compatibility'):
        wanted=a.kernel_4k if a.kernel_4k is not None else plan['components']['spyder']
        if a.kernel_4k is False and data.get('pending_kernel_boot'):
            data['pending_kernel_boot']=None
            store.save()
        if wanted or data.get('pending_kernel_boot'):
            def approve_kernel():
                return a.accept_boot_changes or (sys.stdin.isatty() and
                    ask('Approve switching the Pi 5 to the stock 4 KiB kernel? y/N','n').lower() in ('y','yes'))
            result=host.run_kernel_compatibility(approve_kernel)
            kernel_reboot=result in ('changed','reboot')
            if kernel_reboot:
                print('Reboot required to verify the selected 4 KiB kernel.')
            elif result=='ready':
                plan['kernel_compatibility']='PASS Pi 5 boot compatibility: verified 4096-byte pages and stock v8 kernel'
            else:
                plan['kernel_compatibility']='LIMITED Spyder formatted Help: use Plain Text Help or an external browser until 4 KiB boot is verified'
        elif plan['components']['spyder'] and os.sysconf('SC_PAGE_SIZE') != 4096:
            plan['kernel_compatibility']='LIMITED Spyder formatted Help on the current kernel: use Plain Text Help or an external browser'
    if target:
        if firmware:
            preboot.report_reboot(boot_status)
        if kernel_reboot or boot_status is preboot.BootStatus.REBOOT_REQUIRED or os_upgrade.reboot_pending(data):
            if country and store:
                if getattr(host,'log',None):
                    host.log.stage='wlan'
                with store.stage('wlan'):
                    detail=apply_wlan(host,plan,store)
                    print(detail)
                    if detail.startswith('DEFERRED'):
                        store.data['components']['wlan']['status']='deferred'
            if os_upgrade.reboot_pending(data):
                print('Reboot required for the completed OS upgrade.')
            print('Software installation is paused. After reboot run sudo bash setup-rpi.sh again.')
            if sys.stdin.isatty() and ask('Reboot now? y/N','n').lower() in ('y','yes'):
                host.run(['systemctl','reboot'])
            else:
                print('Run sudo reboot when ready.')
            return 0
    result=apply(a,plan,state,host)
    if store and not result:
        store.data.pop('pending_install',None)
        store.data.pop('pending_update_existing',None)
        store.save()
    return result


if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as exc:sys.exit('Error: '+str(exc))
