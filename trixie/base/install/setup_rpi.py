#!/usr/bin/env python3
"""Initial Raspberry Pi provisioning through the established component installers."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile

import rpi_accounts as accounts
import installation_profiles as profiles

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
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
    """Update only the existing local 127.0.1.1 alias, preserving other hosts."""
    output=[]
    for line in text.splitlines(keepends=True):
        content,separator,comment=line.partition('#')
        tokens=content.split()
        if tokens and tokens[0]=='127.0.1.1' and old in tokens[1:]:
            content=re.sub(r'(?<!\S)'+re.escape(old)+r'(?!\S)',new,content)
            line=content+separator+comment
        output.append(line)
    return ''.join(output)


class Host:
    """Narrow host boundary; tests replace it, never run provisioning commands."""
    def __init__(self):
        self.env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')

    def run(self, argv, capture=False, **kwargs):
        return subprocess.run([str(x) for x in argv],env=self.env,check=True,
                              capture_output=capture,text=True,**kwargs)

    def probe(self,argv):
        return subprocess.run([str(x) for x in argv],env=self.env,check=False,capture_output=True,text=True)

    def change_hostname(self,old,new):
        path=Path('/etc/hosts')
        if path.is_symlink():raise ValueError('symlinked /etc/hosts requires separate review')
        original=path.read_text();updated=hosts_alias(original,old,new)
        if updated==original:
            self.run(['hostnamectl','set-hostname',new]);return
        metadata=path.stat();fd,tmp=tempfile.mkstemp(prefix='.rpi-hosts-',dir=path.parent)
        try:
            with os.fdopen(fd,'w') as stream:
                stream.write(updated);stream.flush();os.fsync(stream.fileno())
            os.chmod(tmp,stat.S_IMODE(metadata.st_mode));os.chown(tmp,metadata.st_uid,metadata.st_gid)
            self.run(['hostnamectl','set-hostname',new])
            try:os.replace(tmp,path)
            except BaseException:
                self.run(['hostnamectl','set-hostname',old]);raise
        finally:Path(tmp).unlink(missing_ok=True)

    def exists(self,path):return Path(path).exists() or Path(path).is_symlink()
    def environment(self,prefix):
        p=Path(prefix)
        if p.is_symlink():raise ValueError('symlinked environment refused: '+str(p))
        if not self.exists(p):return False
        if not (p/'bin/python').is_file() or not (p/'conda-meta').is_dir():
            raise ValueError('existing environment is incomplete; no replacement: '+str(p))
        return True

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
        ssh={}
        for query in ('is-active','is-enabled'):
            try:ssh[query]=self.run(['systemctl',query,'ssh'],capture=True).stdout.strip()
            except (OSError,subprocess.SubprocessError):ssh[query]='inactive, unavailable or unknown'
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
                    ssh=ssh,sudo=sudo,wolfram=wolfram,
                    existing={p:self.exists(p) for p in ('/opt/conda','/opt/lab314','/opt/rpi','/usr/bin/spyder','/usr/local/bin/rpi-share')})


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile-file',type=Path,help='local versioned installation preferences; CLI options override file settings')
    p.add_argument('--ntp-server',action='append',type=profiles.ntp_server,help='NTP hostname/IP; repeat to replace base defaults')
    p.add_argument('--profile',choices=['GENERAL','HOME','AALTO'])
    p.add_argument('--school',choices=['CHEM','custom'],help='compatibility option: AALTO accepts CHEM only')
    p.add_argument('--primary-user');p.add_argument('--additional-user',action='append',default=None,help='additional sudo-group account, repeat; does not receive a new per-user NOPASSWD rule')
    p.add_argument('--no-additional-users',action='store_true')
    p.add_argument('--recovery',choices=['create','keep','cancel'],help='explicit choice when the intended primary account is missing')
    p.add_argument('--hostname',type=hostname)
    p.add_argument('--ssh',choices=['keep','enable','disable'])
    for name in ('system','conda','lab314','spyder','hardware','wolfram','share','imaging'):
        p.add_argument('--'+name,action=argparse.BooleanOptionalAction,default=None)
    p.add_argument('--lab-prefix',type=canonical,default=Path('/opt/lab314'))
    p.add_argument('--ide-prefix',type=canonical)
    p.add_argument('--update-existing',action='store_true',help='explicitly request rolling lab314 and selected IDE maintenance')
    p.add_argument('--apt-upgrade',action='store_true',help='explicitly opt into the established full APT upgrade policy')
    config=p.add_mutually_exclusive_group()
    config.add_argument('--share-json',type=Path);config.add_argument('--share-csv',type=Path)
    config.add_argument('--share-example',action='store_true');config.add_argument('--share-later',action='store_true')
    p.add_argument('--share-user',action='append',default=[],help='local catalog owner; repeat; default is primary user')
    p.add_argument('--share-prefix',type=canonical,help='software prefix; keep existing /opt/lab client location when detected, otherwise /usr/local')
    p.add_argument('--replace-share-config',action='store_true')
    p.add_argument('--default-group')
    p.add_argument('--imaging-source',type=Path);p.add_argument('--imaging-app',action='append',default=[])
    p.add_argument('--imaging-approved',action='store_true',help='administrator confirms selected local Scientific Imaging source has been reviewed')
    p.add_argument('--plan','--dry-run',action='store_true')
    p.add_argument('--yes',action='store_true',help='approve the displayed installation plan; new passwords still require a terminal')
    return p


def ask(prompt, default):
    answer=input(prompt+' ['+str(default)+']: ').strip()
    return answer or default


def interactive(a, state):
    a.profile=ask('Profile GENERAL / HOME / AALTO','GENERAL').upper()
    if a.profile not in ('GENERAL','HOME','AALTO'):raise ValueError('unknown profile')
    if a.profile=='AALTO':
        policy=accounts.aalto_account_plan(a.primary_user,a.additional_user,a.school,a.no_additional_users)
        a.school='CHEM'
        primary_default=policy['primary'];additional_default=' '.join(policy['additional'])
    else:
        primary_default='chem' if a.school=='CHEM' else state['invoking_user'] or ''
        additional_default='chem-it' if a.school=='CHEM' else '-'
    a.primary_user=ask('Primary local account',primary_default)
    selected_hostname=ask('Hostname (normally keep Imager value)',state['hostname'])
    a.hostname=None if selected_hostname==state['hostname'] else hostname(selected_hostname)
    a.ssh=ask('SSH keep / enable / disable','enable' if a.profile=='HOME' else 'keep')
    prompt='Additional sudo-group users (space separated; - means none)'
    if a.profile=='AALTO':prompt='Additional sudo-group users (required maintenance account is retained; - is not allowed)'
    additional=ask(prompt,additional_default)
    a.additional_user=[] if additional=='-' else additional.split()
    for name,default in dict(system=True,conda=True,lab314=True,spyder=True,hardware=False,wolfram=a.profile=='AALTO',share=a.profile!='GENERAL',imaging=False).items():
        if getattr(a,name) is None:setattr(a,name,ask('Include '+name+'? y/n','y' if default else 'n').lower() in ('y','yes'))
    if a.spyder and not a.ide_prefix:
        prefix=ask('Separate Spyder IDE prefix (- keeps APT IDE fallback)','-')
        if prefix!='-':a.ide_prefix=canonical(prefix)
    if a.share and not any((a.share_json,a.share_csv,a.share_example,a.share_later)):
        choice=ask('Share configuration: existing / csv / example / later','later')
        if choice=='existing':a.share_json=Path(input('Existing JSON path: ').strip())
        elif choice=='csv':a.share_csv=Path(input('Local CSV path: ').strip())
        elif choice=='example':a.share_example=True
        elif choice=='later':a.share_later=True
        else:raise ValueError('unknown configuration choice')
    if a.imaging and not a.imaging_source:
        path=ask('Approved local Scientific Imaging source (- defers installation)','-')
        if path!='-':
            a.imaging_source=Path(path);a.imaging_app=input('Application names (space separated): ').split()
            a.imaging_approved=ask('Has this application source/scope been reviewed? y/n','n').lower() in ('y','yes')


def resolve(a,state,host):
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
    defaults=dict(system=True,conda=True,lab314=True,spyder=True,hardware=False,wolfram=a.profile=='AALTO',share=a.profile!='GENERAL',imaging=bool(a.imaging_source))
    components={n:getattr(a,n) if getattr(a,n) is not None else v for n,v in defaults.items()}
    if a.profile in ('HOME','AALTO') and not components['share']:raise ValueError('HOME/AALTO include rpi-share; use --share-later to defer its configuration')
    existing_lab=host.environment(a.lab_prefix)
    existing_conda=host.environment('/opt/conda')
    existing_rpi=host.environment('/opt/rpi')
    existing_ide=host.environment(a.ide_prefix) if a.ide_prefix else False
    if (components['lab314'] or components['hardware'] or a.ide_prefix) and not components['conda'] and not existing_conda:
        raise ValueError('selected environments require the existing Conda bootstrap')
    if components['spyder'] and not components['lab314'] and not existing_lab:
        raise ValueError('Spyder kernel integration requires lab314')
    if a.ide_prefix and not components['spyder']:raise ValueError('--ide-prefix requires Spyder selection')
    if a.ide_prefix and any(a.ide_prefix.is_relative_to(p) or p.is_relative_to(a.ide_prefix) for p in (a.lab_prefix,Path('/opt/rpi'),Path('/opt/conda'),Path('/opt/sci'))):
        raise ValueError('Spyder IDE prefix must be separate from application/scientific prefixes')
    if any(a.lab_prefix.is_relative_to(p) or p.is_relative_to(a.lab_prefix) for p in (Path('/opt/rpi'),Path('/opt/conda'),Path('/opt/sci'))):raise ValueError('lab314 prefix overlaps a protected environment')
    ssh=a.ssh or ('enable' if a.profile=='HOME' else 'keep')
    hostname(a.hostname or state['hostname'])  # Validate without normalizing an existing identity.
    hostname_value=a.hostname or state['hostname']
    if (primary not in state['accounts'] or any(u not in state['accounts'] for u in extras)) and not a.plan and not sys.stdin.isatty():
        raise ValueError('new accounts require interactive password input; no changes made')
    config=None;config_source='DEFERRED: configure later'
    if a.share_json:
        config=catalog.loads(a.share_json.read_text(encoding='utf-8-sig'));config_source='existing JSON: '+str(a.share_json)
    elif a.share_csv:
        config=catalog.import_csv(a.share_csv.read_text(encoding='utf-8-sig'));config_source='local CSV: '+str(a.share_csv)
    elif a.share_example:
        config=catalog.loads((BASE/'config/rpi-share.example.json').read_text());config_source='explicit public example (replace example hosts before real use)'
    if config is not None:
        if not components['share']:raise ValueError('share configuration requires rpi-share selection')
        if a.default_group:config.setdefault('defaults',{})['group']=a.default_group
        catalog.validate(config)
    elif a.default_group:raise ValueError('--default-group requires a selected configuration source')
    owners=a.share_user or [primary]
    if len(set(owners))!=len(owners):raise ValueError('duplicate catalog owners')
    for owner in owners:
        accounts.username(owner)
        if owner not in state['accounts'] and owner not in [primary,*extras]:raise ValueError('catalog owner is not an existing or planned local account')
    return dict(profile=a.profile,school=school,primary=primary,additional=extras,hostname=hostname_value,
                ssh=ssh,ntp=' '.join(a.ntp_server) if a.ntp_server else {'GENERAL':'pool.ntp.org time.cloudflare.com','HOME':'time.mikes.fi','AALTO':'ntp.aalto.fi'}[a.profile],
                components=components,existing_lab=existing_lab,existing_conda=existing_conda,existing_rpi=existing_rpi,
                existing_ide=existing_ide,config=config,config_source=config_source,owners=owners,
                existing_wolfram=bool(state.get('wolfram',{}).get('engine_installed') or state.get('wolfram',{}).get('cli')),
                share_prefix=a.share_prefix or (Path('/opt/lab') if host.exists('/opt/lab/bin/rpi-share') else Path('/usr/local')))


def stages(a,plan):
    c=plan['components'];result=[('accounts','KEEP existing passwords; create only missing approved accounts'),('profile','NTP '+plan['ntp']+'; SSH '+plan['ssh'])]
    if c['system']:result.append(('system','ENSURE existing APT dependency lists; full upgrade '+str(a.apt_upgrade)))
    if c['conda']:result.append(('conda','KEEP' if plan['existing_conda'] else 'INSTALL Miniforge through existing script'))
    if c['spyder'] and a.ide_prefix:result.append(('spyder-ide','KEEP' if plan['existing_ide'] and not a.update_existing else 'CREATE/UPDATE selected separate IDE'))
    if c['lab314']:result.append(('lab314','KEEP' if plan['existing_lab'] and not a.update_existing else 'INSTALL/ROLLING UPDATE Python 3.14.x'))
    if c['spyder'] and a.ide_prefix and plan['existing_lab'] and not a.update_existing:result.append(('spyder-kernel','TARGET spyder-kernels only using selected IDE metadata'))
    if c['lab314']:result.append(('shell','REUSE existing lab314 shell activation and envrun'))
    if c['hardware']:result.append(('hardware','KEEP' if plan['existing_rpi'] else 'INSTALL optional /opt/rpi through existing script'))
    if c['wolfram']:result.append(('wolfram','KEEP existing Engine/CLI; GUI acceptance separate' if plan['existing_wolfram'] else 'CHECK APT availability, then existing optional installer'))
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
    return entry,directory,destination


def install_config(plan,replace=False):
    if plan['config'] is None:return 'DEFERRED: no production catalog selected'
    data=json.dumps(plan['config'],ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    destinations=[config_destination(owner) for owner in plan['owners']]
    # Precheck every destination before writing any user's configuration.
    for _,_,path in destinations:
        if path.exists() and not catalog.same_value(catalog.loads(path.read_text()),plan['config']) and not replace:
            raise ValueError('existing user configuration differs; review --replace-share-config: '+str(path))
    for entry,directory,path in destinations:
        if path.exists() and catalog.same_value(catalog.loads(path.read_text()),plan['config']):
            os.chown(path,entry['uid'],entry['gid']);continue
        directory.mkdir(mode=0o700,exist_ok=True);os.chown(directory,entry['uid'],entry['gid'])
        catalog.atomic_write(path,data,replace);os.chown(path,entry['uid'],entry['gid'])
    return 'CONFIGURED for '+', '.join(plan['owners'])+'; remote access NOT TESTED'


def apply(a,plan,state,host):
    if os.geteuid()!=0:raise ValueError('run setup through sudo to apply; --plan needs no root')
    if not (re.search(r'Raspberry Pi [45]',state['model']) and state['codename']=='trixie' and state['os_id'] in ('debian','raspbian') and state['architecture'] in ('aarch64','arm64')):
        raise ValueError('apply requires Raspberry Pi 4/5, Raspberry Pi OS Trixie 64-bit')
    host.env.update(PRIMARY_USER=plan['primary'],EXTRA_SUDO_USERS=' '.join(plan['additional']),
                    PRE_ACCOUNTS_MANAGED='1',NTP_PRIMARY=plan['ntp'],SSH_POLICY=plan['ssh'],DO_APT_UPGRADE='1' if a.apt_upgrade else '0')
    if a.ide_prefix:host.env['LAB314_SPYDER_PYTHON']=str(a.ide_prefix/'bin/python')
    results=[];core_failed=False
    def shell(name,*args):host.run(['bash',HERE/name,*args])
    def update_ide():
        parent=a.ide_prefix.parent
        if not parent.is_dir():raise ValueError('IDE prefix parent must already exist')
        record=Path(tempfile.mkdtemp(prefix='.rpi-ide-records-',dir=parent))/'operation'
        host.run(['/usr/bin/python3','-IB',HERE/'update_lab314.py','--ide-prefix',a.ide_prefix,'--apply','--record-dir',record])
    for name,description in stages(a,plan):
        if core_failed and name!='verification':
            results.append((name,'BLOCKED','earlier required component failed'));continue
        try:
            detail=''
            if name=='accounts':
                accounts.ensure_user(plan['primary'],admin=True,passwordless=True)
                for user in plan['additional']:accounts.ensure_user(user,admin=True)
                if plan['hostname']!=state['hostname']:
                    host.change_hostname(state['hostname'],plan['hostname']);print('Hostname changed; reconnect using the new name. A reboot may be needed for all services.')
            elif name=='profile':
                script='pre_home.sh' if plan['profile']=='HOME' else 'pre_aalto.sh' if plan['profile']=='AALTO' else 'pre_profile.sh'
                shell(script,*(['GENERAL'] if script=='pre_profile.sh' else []))
            elif name=='system':shell('install_rpi_base.sh')
            elif name=='conda':
                if not plan['existing_conda']:shell('install_conda_base.sh')
            elif name=='spyder-ide':
                if not plan['existing_ide'] or a.update_existing:update_ide()
            elif name=='lab314':
                if not plan['existing_lab'] or a.update_existing:shell('create_lab314_env.sh','--prefix',a.lab_prefix)
            elif name=='spyder-kernel':shell('create_lab314_env.sh','--prefix',a.lab_prefix,'--package','spyder-kernels')
            elif name=='shell':
                if a.lab_prefix!=Path('/opt/lab314'):
                    detail='DEFERRED default autoactivation for custom prefix; use existing explicit activation'
                else:shell('enable_lab314_autoactivate_rpi.sh')
                shell('install_envrun.sh')
            elif name=='hardware':
                if not plan['existing_rpi']:shell('create_rpi_env.sh')
            elif name=='wolfram':
                if plan['existing_wolfram']:detail='KEEP existing Wolfram; CLI/GUI acceptance separate'
                else:
                    candidate=host.run(['apt-cache','policy','wolfram-engine'],capture=True).stdout
                    if not re.search(r'Candidate:\s+(?!\(none\))\S+',candidate):raise ValueError('wolfram-engine unavailable in configured APT sources')
                    shell('install_optional_wolfram.sh','--yes')
                    detail='Engine/CLI installed; graphical Mathematica/Wolfram NOT VERIFIED'
            elif name=='share':
                shell('install_rpi_share.sh','--prefix',plan['share_prefix']);detail=install_config(plan,a.replace_share_config)
            elif name=='imaging':
                source=a.imaging_source
                if not source or not a.imaging_approved or not a.imaging_app or not (source/'scripts/install/01-install.sh').is_file():
                    results.append((name,'DEFERRED','approved local source and explicit --imaging-app selections required'));continue
                argv=[value for app in a.imaging_app for value in ('--app',app)]
                host.run(['bash',source/'scripts/install/01-install.sh',*argv])
                host.run(['bash',source/'scripts/install/02-diagnose.sh',*argv])
            elif name=='verification':
                errors=[];c=plan['components']
                verify=[]
                if c['lab314']:verify.append(['bash',HERE/'verify_rpi_lab314.sh','--prefix',a.lab_prefix])
                if c['hardware']:verify.append(['bash',HERE/'verify_rpi_env.sh'])
                if c['share']:verify.append([plan['share_prefix']/'bin/rpi-share','--check'])
                verify.extend([['hostnamectl','--static'],['systemctl','is-active','systemd-timesyncd'],['timedatectl','show','-p','NTPSynchronized','--value'],['sudo','-n','-u',plan['primary'],'sudo','-n','true']])
                if plan['ssh']=='enable':verify.append(['systemctl','is-active','ssh'])
                for argv in verify:
                    try:
                        check=host.run(argv,capture=True)
                        print('VERIFY',' '.join(str(x) for x in argv),check.stdout.strip())
                        if any('NTPSynchronized' in str(part) for part in argv) and check.stdout.strip()!='yes':errors.append('time synchronization pending')
                    except (OSError,subprocess.SubprocessError) as exc:errors.append(str(exc))
                if errors:raise ValueError('; '.join(errors))
                detail='Static/runtime checks only; GUI, camera performance and network access require acceptance'
            results.append((name,'DEFERRED' if detail.startswith('DEFERRED') else 'PASS',detail or description))
        except (ValueError,OSError,subprocess.SubprocessError) as exc:
            results.append((name,'FAIL',str(exc)));print('FAILED STAGE '+name+': '+str(exc),file=sys.stderr)
            if name in ('accounts','profile','system','conda','spyder-ide','lab314','spyder-kernel','hardware'):core_failed=True
    print('\nINSTALLATION SUMMARY')
    for key in ('profile','school','hostname','primary','additional','ssh','ntp','config_source'):
        print(key+': '+str(plan[key]))
    print('default_navigation_group: '+str((plan['config'].get('defaults',{}).get('group') or 'all') if plan['config'] else 'DEFERRED'))
    if plan['config']:print('additional_navigation_groups: '+str(plan['config']['defaults'].get('additional_groups') or []))
    print('sudo: existing approved NOPASSWD policy preserved; primary admin verified separately')
    for name,status,detail in results:print(status,name,detail)
    for name,selected in plan['components'].items():
        if not selected:print('NOT SELECTED',name)
    if any(status in ('FAIL','BLOCKED') for _,status,_ in results):
        print('Retry: correct the named failure and rerun the reviewed command. Existing accounts/passwords/environments are retained; no destructive rollback is performed.')
        return 1
    return 0


def main(argv=None,host=None):
    a=profiles.parse_arguments(parser(),sys.argv[1:] if argv is None else argv);host=host or Host();state=host.snapshot()
    print('SYSTEM INFORMATION\n'+json.dumps(state,indent=2))
    plan=resolve(a,state,host)
    print('\nINSTALLATION PLAN')
    for key in ('profile','school','primary','additional','hostname','ssh','ntp','config_source','owners'):
        print(key+': '+str(plan[key]))
    for user in [plan['primary'],*plan['additional']]:print('ACCOUNT',user,'EXISTING — KEEP PASSWORD' if user in state['accounts'] else 'MISSING — CREATE, SET PASSWORD INTERACTIVELY')
    print('Default navigation group:',(plan['config'].get('defaults',{}).get('group') or 'all') if plan['config'] else 'DEFERRED')
    for name,description in stages(a,plan):print(name+': '+description)
    print('No storage formatting or automatic account deletion. Package changes are not transactional.')
    if a.plan:
        print('PLAN ONLY: no accounts, passwords, packages, host settings, configuration files or environments changed.');return 0
    if not a.yes:
        if not sys.stdin.isatty() or input('Apply this installation plan? [y/N] ').lower() not in ('y','yes'):
            print('Cancelled; no changes made.');return 0
    return apply(a,plan,state,host)


if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as exc:sys.exit('Error: '+str(exc))
