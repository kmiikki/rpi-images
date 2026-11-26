"""Review and apply a whole-installation update using the saved selection."""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import grp
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import tempfile

from diagnostics import Log, redact
from installation_state import ABSENT, UNKNOWN, atomic_write, now, sync_directory, tree_fingerprint
import lifecycle
import os_upgrade
import preboot
import wolfram

HERE = lifecycle.HERE
BASE = lifecycle.BASE
CONDA = '/opt/conda/bin/conda'


@dataclass
class FileChange:
    component: str
    name: str
    current: dict
    desired: dict
    content: bytes = b''


def checked_path(store, name):
    path = store.path(name)
    for parent in path.parents:
        if parent.exists():
            info = parent.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o022):
                raise ValueError(f'Unsafe parent for {name}: {parent}')
        if parent == store.root:
            break
    return path


def add_file(store, files, component, name, content=None, mode=0o644, link=None, managed_only=False):
    current = store.inspect(name)
    record = store.data['paths'].get(name)
    desired = {'uid': os.geteuid(), 'gid': os.getegid(), 'mode': mode}
    if link is None:
        desired.update(kind='file', sha256=hashlib.sha256(content).hexdigest())
    else:
        desired.update(kind='symlink', mode=0o777, target=link)
    if current == desired:
        print(f'  KEEP {name}')
        return
    if ((managed_only and not record) or current.get('kind') == 'unavailable'
            or (record and (record.get('conflict') or record.get('component') != component
                or current != record.get('installed') and not (
                    current == ABSENT and record.get('original') == ABSENT)))
            or (not record and current != ABSENT)):
        print(f'  PRESERVE {name} (operator changes or unknown ownership)')
        return
    checked_path(store, name)
    print(f'  {"ADD" if current == ABSENT else "UPDATE"} {name}')
    files.append(FileChange(component, name, current, desired, content or b''))


def install_file(store, file):
    path = checked_path(store, file.name)
    if store.snapshot(file.name) != file.current:
        raise ValueError(f'File changed after review: {file.name}')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    mode, uid, gid = (file.desired[k] for k in ('mode','uid','gid'))
    if file.desired['kind'] == 'symlink':
        with tempfile.TemporaryDirectory(dir=path.parent) as temporary:
            link = Path(temporary)/'link'
            link.symlink_to(file.desired['target'])
            os.lchown(link, uid, gid)
            os.replace(link, path)
            sync_directory(path.parent)
    else:
        atomic_write(path, file.content, mode, (uid, gid))
    if store.snapshot(file.name) != file.desired:
        raise ValueError(f'Could not verify managed file: {file.name}')


def file_plan(store, host, selected, layout):
    files = []

    def source(component, path, destination, mode=0o644):
        add_file(store, files, component, destination, path.read_bytes(), mode)

    if selected.get('system'):
        source('system', HERE/'sci-path.sh', '/etc/profile.d/sci-path.sh')
    if selected.get('conda'):
        for tool in ('conda','mamba'):
            add_file(store, files, (store.data['paths'].get('/usr/local/bin/'+tool) or {}).get('component','conda'),
                     '/usr/local/bin/'+tool, link='/opt/conda/bin/'+tool)
        name='/etc/profile.d/conda-path.sh'
        stage=(store.data['paths'].get(name) or {}).get('component','conda')
        add_file(store, files, stage, name, b'# Conda is available through /usr/local/bin.\n')
    if selected.get('lab314'):
        source('shell', BASE/'bin/envrun', '/usr/local/bin/envrun', 0o755)
        if lifecycle.location(store.data,'lab314') == '/opt/lab314':
            source('shell', HERE/'lab314-bash.sh', '/etc/profile.d/lab314-bash.sh')
            name='/etc/bash.bashrc'
            if store.inspect(name).get('kind')=='file':
                data=store.path(name).read_bytes()
                template=(HERE/'lab314-bashrc-block.sh').read_bytes()
                old=re.compile(br'^# >>> LAB314 BEGIN >>>\r?\n.*?^# <<< LAB314 END <<<\r?\n',
                               re.MULTILINE | re.DOTALL)
                blocks=list(old.finditer(data))
                if len(blocks)==1:
                    target=old.sub(lambda _:template,data,count=1)
                    add_file(store,files,'shell',name,target,store.snapshot(name)['mode'],managed_only=True)
                else:
                    print(f'  PRESERVE {name} (activation markers need review).')
            else:
                print(f'  PRESERVE {name} (regular system shell startup file required).')
    if (selected.get('spyder') and not store.data.get('ide_prefix')
            and lifecycle.location(store.data,'lab314') == '/opt/lab314'
            and host.exists('/opt/lab314/bin/spyder')):
        for path,name,mode in lifecycle.SPYDER_LAUNCHER:
            source('spyder-desktop', path, name, int(mode,8))
    if selected.get('share'):
        prefix=Path(store.data.get('share_prefix','/usr/local'))
        for destination in lifecycle.share_paths(prefix):
            name=Path(destination).name
            executable=Path(destination).parent==prefix/'bin'
            source('share', (BASE/('bin' if executable else 'config')/name), destination,
                   0o755 if executable and name!='rpi_share_catalog.py' else 0o644)
        print('  KEEP existing rpi-share catalogs and mount settings.')
    if lifecycle.selected_chromium(store.data)=='shared' and host.exists('/usr/bin/chromium'):
        for path, destination in reversed(lifecycle.CHROMIUM_FILES):
            source('chromium', path, destination)
    if store.data.get('components',{}).get('preboot',{}).get('status')=='applied':
        name=str(preboot.FIRMWARE)
        path=store.path(name)
        if store.inspect(name).get('kind')=='file':
            data=path.read_bytes().decode('utf-8','surrogateescape')
            updated, _, edits=preboot.firmware_plan(data)
            if edits:
                mode=store.snapshot(name)['mode']
                add_file(store,files,'preboot',name,updated.encode('utf-8','surrogateescape'),mode,managed_only=True)
            else:
                print('  KEEP active I²C and SPI boot configuration.')
        if not preboot.module_configured():
            add_file(store,files,'preboot',str(preboot.MODULE_FILE),b'i2c-dev\n',managed_only=True)
    if layout or 'keyboard' in store.data.get('components',{}):
        name=str(preboot.KEYBOARD)
        # Older receipts protected the keyboard utility from reset without tracking its content.
        add_file(store,files,'keyboard',name,preboot.SOURCE.read_bytes(),0o755)
        print(f'  KEEP keyboard layout {layout or "unknown"}.')
    print('  KEEP account settings, hostname, sudo and SSH policy.')
    if lifecycle.NTP_FILE in store.data['paths']:
        ntp=store.data.get('ntp')
        if ntp:
            add_file(store,files,'profile',lifecycle.NTP_FILE,
                     f'[Time]\nNTP={ntp}\nFallbackNTP=time.cloudflare.com pool.ntp.org\n'.encode(),
                     managed_only=True)
        if store.data.get('services',{}).get('profile',{}).get('installed')!=lifecycle.services(host):
            print('  PRESERVE current SSH and time service state (differs from the receipt).')
    return files


def required_apt(selected):
    required=set()
    if selected.get('system'):
        required.update(line for path in ('common-apt.txt','rpi-apt.txt')
                        for raw in (HERE/'packages'/path).read_text().splitlines()
                        if (line:=raw.strip()) and not line.startswith('#'))
        required.difference_update(('spyder','python3-spyder-kernels',*lifecycle.APT_CAMERA))
    if selected.get('hardware'):
        required.update(lifecycle.APT_CAMERA)
    return required


def apt_plan(host, store, work, selected):
    if store.data.get('os_upgrade',{}).get('recover_dpkg'):
        raise ValueError('Finish the interrupted OS upgrade using --action os-upgrade before Update All.')
    if os_upgrade.reboot_pending(store.data):
        raise ValueError('Reboot after the completed OS upgrade before running Update All.')
    current=lifecycle.apt_inventory(host)
    required=required_apt(selected)
    present={name.partition(':')[0] for name in current}
    missing=sorted(required-present)
    with os_upgrade.apt_environment(host):
        if host.run(['dpkg','--audit'],capture=True).stdout.strip():
            raise ValueError('dpkg reports unfinished package configuration; review it before Update All.')
        options=os_upgrade.isolated_lists(host,work)
        output=os_upgrade.simulate(host,options,missing)
        architecture=host.run(['dpkg','--print-architecture'],capture=True).stdout.strip()
    print(output.rstrip(),flush=True)
    removed=os_upgrade.removed_packages(output,architecture)
    protected=required | ({'wolfram-engine'} if selected.get('wolfram') else set())
    if protected & {name.partition(':')[0] for name in removed}:
        raise ValueError('APT would remove a selected component dependency; review APT separately.')
    optional={'wolfram-engine','spyder','python3-spyder-kernels'}-present
    added={line.split()[1].partition(':')[0] for line in os_upgrade.package_actions(output)
           if line.startswith('Inst ')}
    if (added & optional)-({'wolfram-engine'} if selected.get('wolfram') else set()):
        raise ValueError('APT would install an unselected optional application.')
    return current,options,missing,os_upgrade.package_actions(output),removed,architecture


def apply_apt(store,host,plan):
    current,options,missing,actions,removed,architecture=plan
    record=store.data.setdefault('os_upgrade',{})
    with os_upgrade.apt_environment(host):
        if (lifecycle.apt_inventory(host)!=current
                or os_upgrade.package_actions(os_upgrade.simulate(host,options,missing))!=actions):
            raise ValueError('APT changed after review; run Update All again.')
        before={k:v for k,v in current.items() if os_upgrade.KERNEL_PACKAGE.match(k)}
        if actions:
            record.update(status='running',phase='packages',recover_dpkg=True,kernel_before=before)
            store.save()
            try:
                approved=removed | {pkg.rsplit(':',1)[0]+':all' for pkg in removed if pkg.endswith(':'+architecture)}
                with os_upgrade.removal_guard(store.directory,approved) as guard:
                    host.run([*os_upgrade.APT,*options,*guard,'-y','full-upgrade',*missing])
                if host.run(['dpkg','--audit'],capture=True).stdout.strip():
                    raise ValueError('dpkg reports unfinished package configuration after the update.')
            except BaseException:
                record['status']='interrupted'
                store.save()
                raise
        host.run([*os_upgrade.APT,*options,'check'])
    packages=lifecycle.apt_inventory(host)
    after={k:v for k,v in packages.items() if os_upgrade.KERNEL_PACKAGE.match(k)}
    store.data['apt_current']=packages
    record.update(status='completed',phase='complete',recover_dpkg=False,completed=now(),
                  reboot_boot=os_upgrade.boot_id() if after!=before or os_upgrade.REBOOT_REQUIRED.exists() else None)
    if selected_wolfram := store.data.get('wolfram_owned'):
        if current.get('wolfram-engine')==selected_wolfram and 'wolfram-engine' in packages:
            store.data['wolfram_owned']=packages['wolfram-engine']
    store.save()


@dataclass
class CondaChange:
    component: str
    name: str
    source: dict
    transaction: dict
    plan: dict


def records(prefix):
    result={}
    for file in sorted((prefix/'conda-meta').glob('*.json')):
        if file.is_symlink():
            raise ValueError(f'Unsafe Conda metadata: {file}')
        data=json.loads(file.read_text())
        if 'name' in data and 'build' in data:
            result[data['name']]=data
    return result


def transaction(plan):
    if plan.get('success') is not True:
        raise ValueError('Conda rejected the transaction: '+redact(plan))
    actions=plan.get('actions',{})
    return {
        event: {item['name']: (item['version'], item.get('build_string') or item['build'])
                for item in actions.get(event,[])}
        for event in ('UNLINK','LINK')
    }


def numeric_version(version):
    return tuple(map(int,version.split('.'))) if re.fullmatch(r'\d+(?:\.\d+)*',version) else ()


def conda_command(host, command):
    try:
        output=host.run(command,capture=True).stdout
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise ValueError('Conda did not return a JSON plan: '+redact(output[-1500:])) from error


def prefix_fingerprint(store, name):
    root_group=not grp.getgrgid(0).gr_mem and not any(
        item.pw_uid!=0 and item.pw_gid==0 for item in pwd.getpwall())
    return tree_fingerprint(store.path(name),root_only_group=root_group,
                            ignore_package_cache=name=='/opt/conda')


def conda_plan(host, store, component, name, specs):
    prefix=checked_path(store,name)
    entry=store.data['paths'].get(name,{})
    if not entry.get('tree') or entry.get('conflict') or not host.environment(prefix):
        raise ValueError(f'{name}: expect a complete recorded Conda environment. Review or repair it separately.')
    fingerprint=prefix_fingerprint(store,name)
    saved=records(prefix)
    if not saved:
        raise ValueError(f'{name}: no Conda packages found.')
    base=store.path(CONDA)
    code=('import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); '
          'from lab314_policy import ownership; import json; '
          'print(json.dumps(ownership(Path(sys.prefix))[1]))')
    if conda_command(host,[prefix/'bin/python','-IB','-c',code,HERE]):
        raise ValueError(f'{name} has pip-owned packages; review their constraints separately before Update All.')
    command=[base,'install','-p',prefix,'--override-channels','-c','conda-forge',
             '--update-all','--dry-run','--json']
    plan=conda_command(host,[*command,*specs])
    changes=transaction(plan)
    removed=changes['UNLINK'].keys()-changes['LINK'].keys()
    if removed:
        # A new dependency layout can make an installed library unnecessary.
        # Keep such packages by first trying a solve with all installed roots.
        roots=sorted(saved.keys()-{spec.partition('=')[0] for spec in specs})
        plan=conda_command(host,[*command,*roots,*specs])
        changes=transaction(plan)
        removed=changes['UNLINK'].keys()-changes['LINK'].keys()
    print(f'\n{lifecycle.LABELS[component]} ({name})')
    print('  Current:',', '.join(f'{k} {v}' for k,v in lifecycle.environment_versions(prefix).items()))
    for package in sorted(changes['UNLINK'].keys() | changes['LINK'].keys()):
        old=changes['UNLINK'].get(package)
        new=changes['LINK'].get(package)
        operation='ADD' if old is None else 'REMOVE' if new is None else 'UPDATE'
        if old and new:
            previous,target=map(numeric_version,(old[0],new[0]))
            if previous and target and previous>target:
                operation='DOWNGRADE'
        print(f'  {operation:9} {package}: {" ".join(old) if old else "-"} -> {" ".join(new) if new else "-"}')
    if removed:
        raise ValueError(f'{name}: Conda proposes removing packages without replacement: {", ".join(sorted(removed))}.')
    if not changes['LINK']:
        print('  KEEP all packages; they already match the update plan.')
    return CondaChange(component,name,fingerprint,changes,plan)


def conda_plans(host,store,selected):
    config=json.loads((BASE/'config/lab314/requirements.json').read_text())
    targets=config['native']
    specs=[*config['conda'],'python-gil',f"opencv={targets['opencv']}=qt6*",f"hdf5={targets['hdf5']}"]
    specs.extend(name.lower() for name in config['pip'] if name!='opencv-python')
    data=store.data
    result=[]
    if selected.get('lab314'):
        lab=lifecycle.location(data,'lab314')
        if not host.native_lab314(store.path(lab)):
            raise ValueError(f'{lab}: migrate the historical mixed Scientific Python environment separately.')
        if selected.get('spyder') and not data.get('ide_prefix'):
            if not host.exists(store.path(lab)/'bin/spyder'):
                raise ValueError('The selected integrated Spyder is missing; repair it before Update All.')
            specs.append(f"spyder=={targets['spyder']}")
        elif not data.get('ide_prefix') and host.exists(store.path(lab)/'bin/spyder'):
            version=lifecycle.environment_versions(store.path(lab)).get('spyder')
            if version:
                specs.append('spyder=='+version)
        result.append(conda_plan(host,store,'lab314',lab,specs))
    if selected.get('spyder') and data.get('ide_prefix'):
        if not selected.get('lab314'):
            print('  Separate Spyder is selected without Scientific Python.')
        result.append(conda_plan(host,store,'spyder-ide',data['ide_prefix'],[f"spyder=={targets['spyder']}"]))
    if selected.get('hardware'):
        path=store.path('/opt/rpi/lib/python3.13/site-packages/aalto-system-dist-packages.pth')
        if path.is_symlink() or not path.is_file() or path.read_text()!='/usr/lib/python3/dist-packages\n':
            raise ValueError('The Raspberry Pi Python 3.13 camera bridge needs review.')
        result.append(conda_plan(host,store,'hardware','/opt/rpi',['python=3.13']))
    if selected.get('conda'):
        base=store.path('/opt/conda')
        version=lifecycle.environment_versions(base).get('python','')
        if not re.fullmatch(r'\d+\.\d+\.\d+.*',version):
            raise ValueError('Unable to identify the Miniforge Python series.')
        result.append(conda_plan(host,store,'conda','/opt/conda',['python=' + '.'.join(version.split('.')[:2])]))
    return result


def package_file(prefix, name):
    relative=Path(name)
    if relative.is_absolute() or '..' in relative.parts or relative==Path('.'):
        raise ValueError('Conda reported an unsafe package path.')
    path=prefix/relative
    if not path.parent.resolve().is_relative_to(prefix):
        raise ValueError(f'Conda package path escapes its prefix: {path}')
    return path


def check_conda_paths(prefix, cache, step):
    installed=records(prefix)
    package_files={name for item in installed.values() for name in item.get('files',[])}
    for name in step.transaction['UNLINK']:
        for entry in installed[name].get('paths_data',{}).get('paths',[]):
            if entry.get('path_type')!='hardlink':
                continue
            checksum=entry.get('sha256_in_prefix')
            if not checksum and not entry.get('prefix_placeholder'):
                checksum=entry.get('sha256')
            path=package_file(prefix,entry['_path'])
            if not checksum or not path.exists():
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError(f'Locally changed Conda file is preserved: {path}')
            with path.open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=checksum:
                    raise ValueError(f'Locally changed Conda file is preserved: {path}')
    for name,(version,build) in step.transaction['LINK'].items():
        paths=cache/f'{name}-{version}-{build}'/'info/paths.json'
        if not paths.is_file():
            raise ValueError(f'Cached Conda package lacks a file manifest: {name}')
        for entry in json.loads(paths.read_text())['paths']:
            if entry.get('path_type')=='directory' or entry['_path'] in package_files:
                continue
            path=package_file(prefix,entry['_path'])
            if path.exists() or path.is_symlink():
                raise ValueError(f'Untracked file would be replaced; preserved {path}.')


def verify_conda_transaction(host,store,step):
    base=store.path(CONDA)
    prefix=store.path(step.name)
    if prefix_fingerprint(store,step.name)!=step.source:
        raise ValueError(f'Environment changed after review: {step.name}')
    exact=[f'{name}={version}={build}' for name,(version,build) in sorted(step.transaction['LINK'].items())]
    command=[base,'install','-p',prefix,'--no-deps','--override-channels','-c','conda-forge',*exact]
    if exact:
        host.run([*command,'--download-only','-y'],capture=True)
        proposed=conda_command(host,[*command,'--offline','--dry-run','--json'])
        if transaction(proposed)!=step.transaction:
            raise ValueError(f'{step.name}: cached Conda transaction differs from the approved plan.')
        check_conda_paths(prefix,Path(host.env['CONDA_PKGS_DIRS']),step)
    return command


def apply_conda(host,store,step,command):
    if not step.transaction['LINK']:
        return
    prefix=store.path(step.name)
    if prefix_fingerprint(store,step.name)!=step.source:
        raise ValueError(f'Environment changed after review: {step.name}')
    entry=store.data['paths'][step.name]
    removal_receipt=store.inspect(step.name,True)
    can_refresh_removal=removal_receipt.get('kind')=='tree' and removal_receipt==entry.get('installed')
    before=records(prefix)
    with store.stage(step.component):
        host.run([*command,'--offline','-y'])
        expected={name:(item['version'],item['build']) for name,item in before.items()}
        expected.update(step.transaction['LINK'])
        installed={name:(item['version'],item['build']) for name,item in records(prefix).items()}
        if installed!=expected:
            raise ValueError(f'Installed package records differ from the approved plan: {step.name}')
        component=store.data['components'][step.component]
        component['versions']=lifecycle.environment_versions(prefix)
        component['maintenance_fingerprint']=prefix_fingerprint(store,step.name)
        if can_refresh_removal:
            receipt=store.inspect(step.name,True)
            if receipt.get('kind')=='tree':
                entry['installed']=receipt


def terminal_plan(store,host,layout):
    if layout not in ('fi','se') or not store.data.get('terminal_shortcuts'):
        print('  KEEP LXTerminal settings.')
        return None
    target=lifecycle.installed_desktop_target(store,host)
    tracked=store.data['terminal_shortcuts'].get(target['name']) if target else None
    if not tracked or any(tracked.get(key)!=value for key,value in target.items()):
        print('  PRESERVE LXTerminal settings (requires the recorded desktop user).')
        return None
    try:
        action=lifecycle.terminal_shortcuts(host,target,layout=layout,preview=True,tracked=True)
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        print('  PRESERVE LXTerminal settings:',redact(error))
        return None
    print('  LXTerminal zoom:',action)
    return target if action=='changed' else None


def verify(host,store,selected,layout,conda,imaging):
    stages={step.component for step in conda}
    if 'conda' in stages:
        host.run([store.path(CONDA),'--version'])
    if 'lab314' in stages:
        prefix=store.path(lifecycle.location(store.data,'lab314'))
        command=[prefix/'bin/python','-IB',HERE/'check_lab314.py','--prefix',prefix,
                 '--functional','--require-opencv-target']
        if selected.get('spyder') and not store.data.get('ide_prefix'):
            command.append('--require-spyder')
        host.run(command)
    if 'spyder-ide' in stages:
        prefix=store.path(store.data['ide_prefix'])
        host.run([prefix/'bin/python','-IB','-c','import spyder; print(spyder.__version__)'])
    if 'hardware' in stages:
        host.run(['bash',HERE/'verify_rpi_env.sh'])
    if selected.get('share'):
        host.run([store.path(lifecycle.location(store.data,'share')),'--check'])
    if selected.get('lab314'):
        runner=store.path('/usr/local/bin/envrun')
        if runner.is_file():
            host.run([runner,'--help'],capture=True)
    if selected.get('wolfram'):
        wolfram.verify(host,store)
    if store.data.get('profile'):
        print(lifecycle.chromium_policy(store))
    if imaging is not None:
        lifecycle.run_imaging(store,host,'diagnose')
    print('Keyboard layout retained:',layout or 'unknown')
    if selected.get('spyder'):
        lifecycle.spyder_pending()


@contextmanager
def log_operation(host,store):
    old=host.log
    host.log=Log(store.directory)
    host.log.stage='update-all'
    print('Diagnostic log:',host.log.path)
    store.data['operation']={'action':'update-all','target':'installation','status':'running','time':now()}
    store.save()
    try:
        yield
    except BaseException:
        store.data['operation']['status']='failed'
        raise
    else:
        store.data['operation']['status']='complete'
    finally:
        store.save()
        host.log.close()
        host.log=old


def plan_id(store, apt, conda, files, terminal, imaging):
    facts={
        'installation':store.data.get('id'),
        'selection':store.data['selected'],
        'apt':apt[3],
        'conda': [(step.name,step.source,step.transaction) for step in conda],
        'files': [(file.name,file.current,file.desired) for file in files],
        'terminal':terminal,
        'imaging':imaging,
    }
    return hashlib.sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest()


def run(host,store,args):
    if not store.data or not store.data.get('selected'):
        raise ValueError('Update All requires a saved component selection. '+UNKNOWN)
    initial=json.dumps(store.data,sort_keys=True)
    selected=store.data['selected']
    print('Update All ·',store.data.get('profile','saved installation'),flush=True)
    print('Installed selection:', ', '.join(name for name,present in selected.items() if present))
    print('Excluded optional components:', ', '.join(name for name,present in selected.items() if not present))
    with lifecycle.inspection(host):
        work=Path(host.env['TMPDIR'])
        apt=apt_plan(host,store,work/'apt',selected)
        wolfram_update=None
        for action in apt[3]:
            match=re.match(r'^Inst wolfram-engine(?::\S+)? (?:\[[^\]]+\] )?\((\S+)',action)
            if match:
                wolfram_update=wolfram.package_metadata(host,match[1],apt[1])
                wolfram.show_preflight(host,wolfram_update,strict=not args.plan)
                print('Approving this update authorizes installation under the displayed Wolfram terms.')
        conda=conda_plans(host,store,selected)
        print('\nManaged programs and settings')
        if selected.get('wolfram'):
            print('  Reconcile Wolfram desktop entries from the installed package after APT.')
        layout=preboot.active_layout()
        files=file_plan(store,host,selected,layout)
        terminal=terminal_plan(store,host,layout)
        imaging=None
        if selected.get('imaging'):
            imaging=lifecycle.run_imaging(store,host,'update',preview=True).stdout
            print(imaging.rstrip())
        print('\nVerifying the Conda plans in a private cache.',flush=True)
        commands=[verify_conda_transaction(host,store,step) for step in conda]
        fingerprint=plan_id(store,apt,conda,files,terminal,imaging)
        print('Update All plan ID:',fingerprint,flush=True)
        if args.expect_plan and args.expect_plan!=fingerprint:
            raise ValueError('Update All differs from the previously reviewed plan; approve the new plan.')
        if args.plan:
            print('PLAN ONLY: no installed files or packages changed.')
            return 0
        if wolfram_update and args.yes and not args.accept_wolfram_license:
            raise ValueError('Update All with --yes and a Wolfram package change requires --accept-wolfram-license.')
        if not lifecycle.confirm(args) or apt[4] and not os_upgrade.confirm_removals(sorted(apt[4])):
            print('Update All cancelled.')
            return 1
        with store.locked():
            if json.dumps(store.data,sort_keys=True)!=initial:
                raise ValueError('The installation record changed after review; run Update All again.')
            with log_operation(host,store):
                for step in conda:
                    if prefix_fingerprint(store,step.name)!=step.source:
                        raise ValueError(f'Environment changed after review: {step.name}')
                    if step.transaction['LINK'] and (active:=lifecycle.consumers(store.path(step.name))):
                        raise ValueError(f'Close processes using {step.name} before updating: '+', '.join(active))
                for file in files:
                    if store.snapshot(file.name)!=file.current:
                        raise ValueError(f'File changed after review: {file.name}')
                if imaging is not None and lifecycle.run_imaging(store,host,'update',preview=True).stdout!=imaging:
                    raise ValueError('Scientific Imaging plan changed after review.')
                apply_apt(store,host,apt)
                if selected.get('wolfram') and wolfram.PACKAGE in lifecycle.apt_inventory(host):
                    lifecycle.reconcile_wolfram_launchers(store,host)
                for step,command in zip(conda,commands):
                    apply_conda(host,store,step,command)
                for component in dict.fromkeys(file.component for file in files):
                    group=[file for file in files if file.component==component]
                    with store.stage(component,[(file.name,False) for file in group],repair_missing=True):
                        if component=='spyder-desktop':
                            with lifecycle.spyder_prefix_receipt(store):
                                for file in group:
                                    install_file(store,file)
                        else:
                            for file in group:
                                install_file(store,file)
                if any(file.component=='preboot' for file in files):
                    store.data['pending_boot']=os_upgrade.boot_id()
                if terminal:
                    print(lifecycle.apply_terminal_shortcuts(store,host,terminal,layout))
                if imaging is not None:
                    paths=[(lifecycle.app_record(app),False) for app in store.data['imaging']['apps']]
                    with store.stage('imaging',paths):
                        lifecycle.run_imaging(store,host,'update')
                with store.stage('verification'):
                    verify(host,store,selected,layout,conda,imaging)
                if (store.data.get('pending_boot')==os_upgrade.boot_id()
                        or os_upgrade.reboot_pending(store.data)):
                    print('Reboot manually to activate updated kernel or firmware settings.')
    print('Update All completed.')
    return 0
