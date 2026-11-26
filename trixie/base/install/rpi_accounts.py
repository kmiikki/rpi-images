#!/usr/bin/env python3
"""Small, explicit local-account recovery/removal helper. Never removes homes."""
import argparse
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent


def username(name):
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,30}',name) or name in ('root','nobody'):
        raise ValueError('choose a normal local username (1..31 lowercase characters)')
    return name



CHEM_PRIMARY='chem'
CHEM_MAINTENANCE='chem-it'


def aalto_account_plan(primary=None, additional=None, school=None, no_additional=False):
    """Pure CHEM policy shared by setup, profile validation and legacy entrypoints."""
    if school not in (None,'CHEM'):
        raise ValueError('AALTO requires CHEM policy; --school custom is incompatible. Use GENERAL for custom installations.')
    if no_additional or additional==[]:
        raise ValueError('AALTO requires its maintenance account; no-additional-users or an empty additional-account list is incompatible')
    primary=CHEM_PRIMARY if primary is None else username(primary)
    requested=[] if additional is None else additional
    if not isinstance(requested,list):raise ValueError('additional accounts must be a list')
    for name in requested:username(name)
    if len(set(requested))!=len(requested):raise ValueError('duplicate additional accounts')
    extras=[CHEM_MAINTENANCE]+[name for name in requested if name!=CHEM_MAINTENANCE]
    if primary in extras:raise ValueError('duplicate primary/additional accounts; the maintenance account must remain separate')
    return dict(school='CHEM',primary=primary,additional=extras)


def local_accounts():
    # Deliberately use local passwd, not a remote NSS directory.
    result={}
    for line in Path('/etc/passwd').read_text().splitlines():
        p=line.split(':')
        if len(p)==7:
            result[p[0]]=dict(uid=int(p[2]),gid=int(p[3]),home=p[5],shell=p[6])
    return result


def uid_min():
    match=re.search(r'^\s*UID_MIN\s+(\d+)',Path('/etc/login.defs').read_text(),re.M)
    return int(match[1]) if match else 1000


def invoking_user(accounts, env=None):
    env=os.environ if env is None else env
    name=env.get('SUDO_USER')
    if name and name!='root' and name in accounts and accounts[name]['uid']>=uid_min():
        uid=env.get('SUDO_UID')
        if uid is not None and (not uid.isdecimal() or int(uid)!=accounts[name]['uid']):
            raise ValueError('SUDO_USER/SUDO_UID disagree; specify the primary account explicitly')
        return name
    if os.getuid()!=0:
        return next((n for n,a in accounts.items() if a['uid']==os.getuid()),None)
    return None


def run(argv, **kwargs):
    return subprocess.run([str(x) for x in argv],check=True,**kwargs)


def ensure_user(name, admin=False, passwordless=False):
    username(name)
    accounts=local_accounts()
    if name in accounts:
        if accounts[name]['uid']<uid_min() or accounts[name]['shell'].endswith(('nologin','false')):
            raise ValueError('not a usable normal local account: '+name)
        print('KEEP account and password: '+name)
    else:
        try: pwd.getpwnam(name)
        except KeyError: pass
        else: raise ValueError('name conflicts with a non-local identity: '+name)
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError('new accounts require secure interactive passwd input')
        # No login shell until passwd and the requested privileges succeed.
        run(['useradd','--create-home','--shell','/usr/sbin/nologin','--',name])
        try:
            role = 'primary administrator' if passwordless else 'additional administrator' if admin else 'local user'
            print(f"Creating {role} account: {name}\nSet password for account '{name}'.", flush=True)
            run(['passwd',name])
            if admin: run(['usermod','-aG','sudo',name])
            if passwordless: run(['bash',HERE/'account-policy.sh',name])
            if passwordless: run(['sudo','-n','-u',name,'sudo','-n','true'])
            run(['usermod','--shell','/bin/bash',name])
        except BaseException:
            subprocess.run(['usermod','--lock','--expiredate','1','--shell','/usr/sbin/nologin',name],check=False)
            raise
        print('CREATED account; password and privileges configured: '+name)
    if name in accounts:
        if admin: run(['usermod','-aG','sudo',name])
        if passwordless: run(['bash',HERE/'account-policy.sh',name])
    return local_accounts()[name]


def removal_review(old, replacement):
    username(old);username(replacement);accounts=local_accounts();caller=invoking_user(accounts)
    if old not in accounts or replacement not in accounts: raise ValueError('both accounts must exist locally')
    a=accounts[old];new=accounts[replacement]
    if old==replacement or old==caller or a['uid']==os.getuid() or a['uid']<uid_min():
        raise ValueError('cannot remove the current login account or a system account')
    if caller!=replacement or new['uid']<uid_min() or new['shell'].endswith(('nologin','false')):
        raise ValueError('log in as the intended replacement account and invoke through sudo')
    # Fail closed if session/process inspection is unavailable.
    sessions=subprocess.run(['loginctl','list-sessions','--no-legend','--no-pager'],capture_output=True,text=True,check=True).stdout
    if any(len(line.split())>1 and line.split()[1]==str(a['uid']) for line in sessions.splitlines()):
        raise ValueError('old account has active login sessions')
    processes=subprocess.run(['pgrep','-u',str(a['uid'])],capture_output=True,text=True)
    if processes.returncode not in (0,1):raise ValueError('cannot inspect old account processes')
    if processes.returncode==0:raise ValueError('old account still owns running processes')
    if not any(len(line.split())>1 and line.split()[1]==str(new['uid']) for line in sessions.splitlines()):
        raise ValueError('replacement must have a successful active login session')
    # Verifies the replacement can administer this machine under approved policy.
    run(['sudo','-n','-u',replacement,'sudo','-n','true'],stdout=subprocess.DEVNULL)
    jobs=subprocess.run(['crontab','-u',old,'-l'],capture_output=True,text=True)
    if jobs.returncode not in (0,1):raise ValueError('cannot inspect old crontab')
    if jobs.returncode==0 and jobs.stdout.strip():raise ValueError('review/remove old scheduled tasks before account removal')
    if Path('/var/lib/systemd/linger',old).exists():raise ValueError('review systemd lingering/user services before removal')
    if any(f.is_file() and f.stat().st_uid==a['uid'] for f in Path('/var/spool/cron/atjobs').glob('*')):
        raise ValueError('review old at jobs before removal')
    relevant=[Path('/etc/lightdm/lightdm.conf'),*Path('/etc/lightdm/lightdm.conf.d').glob('*.conf'),Path('/etc/ssh/sshd_config'),*Path('/etc/ssh/sshd_config.d').glob('*.conf'),Path('/etc/crontab'),*Path('/etc/cron.d').glob('*')]
    blockers=[]
    for file in relevant:
        if file.is_file():
            lines=[line for line in file.read_text(errors='replace').splitlines() if not line.lstrip().startswith('#')]
            if any(re.search(r'(?<![a-z0-9_-])'+re.escape(old)+r'(?![a-z0-9_-])',line) for line in lines):blockers.append(str(file))
    if blockers:raise ValueError('review old account references first: '+', '.join(blockers))
    home=Path(a['home'])
    return dict(old=old,replacement=replacement,uid=a['uid'],home=str(home),home_preserved=True,
                ssh_directory_present=(home/'.ssh').exists(),sudo_access_verified=True,
                note='Review all other UID-owned files, systemd user units, at jobs and backups before confirming.')


def main(argv=None):
    import json
    p=argparse.ArgumentParser(description=__doc__)
    action=p.add_mutually_exclusive_group(required=True)
    action.add_argument('--create');action.add_argument('--remove')
    p.add_argument('--admin',action='store_true');p.add_argument('--passwordless',action='store_true')
    p.add_argument('--replacement');p.add_argument('--plan',action='store_true')
    p.add_argument('--apply',action='store_true');p.add_argument('--confirm-remove')
    p.add_argument('--login-verified',action='store_true');p.add_argument('--files-reviewed',action='store_true')
    a=p.parse_args(argv)
    if a.create:
        username(a.create)
        if a.plan: print('KEEP' if a.create in local_accounts() else 'CREATE WITH INTERACTIVE PASSWORD',a.create);return
        if not a.apply:raise ValueError('account creation requires --apply')
        if os.geteuid()!=0:raise ValueError('run through sudo')
        ensure_user(a.create,a.admin,a.passwordless);return
    if not a.replacement:raise ValueError('--replacement is required')
    review=removal_review(a.remove,a.replacement);print(json.dumps(review,indent=2))
    if not a.apply or a.plan:return
    if os.geteuid()!=0:raise ValueError('run through sudo')
    if not a.login_verified or not a.files_reviewed:raise ValueError('verify the replacement login and review UID-owned files first')
    if a.confirm_remove!=a.remove:
        if not sys.stdin.isatty() or input('Type REMOVE '+a.remove+' to remove only the account: ')!='REMOVE '+a.remove:
            raise ValueError('separate removal confirmation required')
    removal_review(a.remove,a.replacement)  # Recheck immediately before deletion.
    run(['userdel','--',a.remove])  # Intentionally no --remove/-r.
    print('Account removed. Home and UID-owned data preserved; review residual sudo policy separately.')


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.SubprocessError) as exc:sys.exit('Error: '+str(exc))
