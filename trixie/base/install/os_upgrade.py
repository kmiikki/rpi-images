"""Reviewed, resumable Raspberry Pi OS package upgrades."""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile

REBOOT_REQUIRED = Path('/run/reboot-required')
KERNEL_PACKAGE = re.compile(r'^(linux-(image|modules)-|raspi-firmware(?:$|:)|raspberrypi-(kernel|bootloader)|rpi-eeprom)')
APT = ('apt-get','-o','DPkg::Options::=--force-confold','-o','APT::Get::AutomaticRemove=false')
DEFAULT = 'unknown'


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def description(data):
    record=(data or {}).get('os_upgrade',{})
    return {'not-started':'Not started','running':'Interrupted (previous process did not finish)',
            'interrupted':'Interrupted','completed':'Completed'}.get(record.get('status'),'Unknown')


def reboot_pending(data):
    recorded=(data or {}).get('os_upgrade',{}).get('reboot_boot')
    return bool(recorded and recorded==boot_id())


@contextmanager
def apt_environment(host):
    original=host.env.copy()
    host.env.pop('APT_CONFIG',None)
    host.env.update(LC_ALL='C', DEBIAN_FRONTEND='noninteractive')
    try:
        yield
    finally:
        host.env.clear()
        host.env.update(original)


def repository_release(host, options=()):
    policy=host.run(['apt-cache',*options,'policy'],capture=True).stdout
    releases=set()
    for line in policy.splitlines():
        match=re.search(r'\brelease\s+(.*)',line)
        if match:
            fields=dict(item.split('=',1) for item in match[1].split(',') if '=' in item)
            origin=fields.get('o','').lower()
            if origin in ('debian','raspbian') or 'raspberry pi' in origin:
                if codename:=fields.get('n'):
                    releases.add(codename)
    allowed={'trixie','trixie-updates','trixie-security','trixie-backports','trixie-backports-sloppy'}
    if not releases or releases-allowed:
        shown=', '.join(sorted(releases)) or 'no recognized distribution repository'
        raise ValueError(f'APT repository codenames require review for Trixie: {shown}.')


def simulate(host, options=(), packages=()):
    return host.run([*APT,*options,'--simulate','full-upgrade',*packages],capture=True).stdout


def package_actions(output):
    return tuple(line for line in output.splitlines() if re.match(r'^(Inst|Conf|Remv|Purg)\s',line))


def isolated_lists(host, work):
    """Refresh APT package lists without running system hooks or touching live lists."""
    (work/'lists/partial').mkdir(parents=True)
    (work/'archives/partial').mkdir(parents=True)
    config=work/'update.conf'
    config.write_text('#clear APT::Update::Pre-Invoke;\n#clear APT::Update::Post-Invoke;\n'
                      '#clear APT::Update::Post-Invoke-Success;\n')
    options=('-o',f'Dir::State::lists={work}/lists','-o',f'Dir::Cache::archives={work}/archives',
             '-o','Dir::Cache::pkgcache=','-o','Dir::Cache::srcpkgcache=')
    host.run(['apt-get',*options,'-c',config,'-o','APT::Update::Error-Mode=any','update'],capture=True)
    repository_release(host,options)
    return options


def removed_packages(plan, architecture):
    removed=set()
    for line in plan.splitlines():
        if match:=re.match(r'^(?:Remv|Purg)\s+(\S+)',line):
            name,_,arch=match[1].partition(':')
            removed.add(f'{name}:{arch or architecture}')
    return removed


def actual_removals(stream):
    if stream.readline().strip()!='VERSION 3':
        raise ValueError('APT did not provide the version 3 package plan.')
    for line in stream:
        if not line.strip():
            break
    else:
        raise ValueError('APT package plan is incomplete.')
    removed=set()
    for line in stream:
        fields=line.split(maxsplit=8)
        if len(fields)!=9:
            raise ValueError('APT supplied a malformed package action.')
        if fields[-1].strip()=='**REMOVE**':
            removed.add(f'{fields[0]}:{fields[2]}')
    return removed


@contextmanager
def removal_guard(directory, approved):
    if not approved:
        yield ['--no-remove']
        return
    with tempfile.TemporaryDirectory(prefix='apt-guard-',dir=directory) as temporary:
        hook=Path(temporary)/'check-removals'
        command=shlex.join(['/usr/bin/python3','-IB',str(Path(__file__).resolve()),*sorted(approved)])
        hook.write_text('#!/bin/sh\nexec '+command+'\n')
        hook.chmod(0o700)
        yield ['-o',f'DPkg::Pre-Install-Pkgs::={hook}',
               '-o',f'DPkg::Tools::Options::{hook}::Version=3']


def preview(host):
    with apt_environment(host):
        print('APT simulation using currently cached package lists; apply refreshes and reviews the live plan.')
        result=host.run([*APT,'-o','Dir::Cache::pkgcache=','-o','Dir::Cache::srcpkgcache=',
                         '--simulate','full-upgrade'],capture=True)
        print(result.stdout.rstrip())


def confirm_removals(packages):
    print('APT proposes removing: '+', '.join(packages),flush=True)
    return sys.stdin.isatty() and input('Type REMOVE to approve these removals, or Enter to cancel: ').strip()=='REMOVE'


def run(host, store, inventory, approve, approve_removals, *, first_install=False):
    record=store.data.setdefault('os_upgrade',{'status':DEFAULT})
    if reboot_pending(store.data):
        print('Kernel/firmware: Reboot required from the completed OS upgrade.')
        return True
    if not record.get('recover_dpkg'):
        record['kernel_before']={k:v for k,v in inventory(host).items() if KERNEL_PACKAGE.match(k)}
    record.update(status='running',phase='lists',first_install=first_install or record.get('first_install',False))
    store.save()
    if getattr(host,'log',None):
        host.log.stage='os-upgrade'
    try:
        with apt_environment(host):
            print('\nRaspberry Pi OS Update',flush=True)
            host.run(['apt-get','-o','APT::Update::Error-Mode=any','update'])
            repository_release(host)
            print('APT package lists: PASS',flush=True)
            if record.get('recover_dpkg') and host.run(['dpkg','--audit'],capture=True).stdout.strip():
                record['phase']='recovery'
                store.save()
                print('Resume configuration of packages unpacked by the interrupted upgrade.',flush=True)
                host.run(['dpkg','--force-confold','--configure','-a'])
            record['phase']='review'
            store.save()
            plan=simulate(host)
            print(plan.rstrip(),flush=True)
            architecture=host.run(['dpkg','--print-architecture'],capture=True).stdout.strip()
            removed=removed_packages(plan,architecture)
            if not approve() or (removed and not approve_removals(sorted(removed))):
                record.update(status='interrupted',phase='review')
                store.save()
                print('OS upgrade paused before package changes. Review and rerun when ready.')
                return False
            record.update(phase='packages',recover_dpkg=True)
            store.save()
            with removal_guard(store.directory,{*removed,*(pkg.rsplit(':',1)[0]+':all'
                               for pkg in removed if pkg.endswith(':'+architecture))}) as guard:
                host.run([*APT,*guard,'-y','full-upgrade'])
            if host.run(['dpkg','--audit'],capture=True).stdout.strip():
                raise ValueError('dpkg reports incomplete package configuration after the upgrade.')
            host.run([*APT,'check'])
        packages=inventory(host)
        after={k:v for k,v in packages.items() if KERNEL_PACKAGE.match(k)}
        reboot=REBOOT_REQUIRED.exists() or after!=record['kernel_before']
        store.data['apt_current']=packages
        record.update(status='completed',phase='complete',recover_dpkg=False,
                      completed=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                      reboot_boot=boot_id() if reboot else None)
        store.save()
    except BaseException as error:
        record['status']='interrupted'
        try:
            store.save()
        except OSError as journal_error:
            error.add_note(f'Could not write interrupted upgrade state: {journal_error}')
        print('APT package lists: FAIL' if record['phase']=='lists' else 'Full OS upgrade: FAIL',flush=True)
        print(f"OS upgrade incomplete during {record['phase']}; see the installation log and rerun setup.",flush=True)
        raise
    print('Full OS upgrade: PASS',flush=True)
    print('Kernel/firmware:', 'Reboot required' if reboot else 'No reboot required',flush=True)
    return True


if __name__=='__main__':
    try:
        if unexpected:=actual_removals(sys.stdin)-set(sys.argv[1:]):
            raise ValueError('APT proposed unapproved removals: '+', '.join(sorted(unexpected)))
    except ValueError as error:
        sys.exit(str(error))
