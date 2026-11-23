"""Plan explicit lab314 updates; apply only on request, preserving package ownership.

Run with the target environment's Python. Updates are NOT transactional.
Stop its consumers and take an external prefix backup before --apply.
"""
import argparse
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from packaging.version import InvalidVersion, Version
from lab314_policy import (Requirement, canonical, missing_scientific_defaults, opencv_specs,
                           ownership, policy, requirements, solved_spyder)

CONDA='/opt/conda/bin/conda'


def pip_plan_args(python, targets, constraints, report, no_deps=False, initialize=False, repair=False):
    config=policy()
    args=[python,'-IB','-m','pip','install','--dry-run','--report',str(report),
          '--only-binary=:all:','--index-url',config['pip_index'],
          '--extra-index-url',config['pip_extra_index'],'--constraint',str(constraints)]
    if not initialize:args+=['--upgrade','--upgrade-strategy','only-if-needed']
    if repair:args.append('--force-reinstall')
    if no_deps:args+=['--no-deps']
    return args+targets


def validate_pip_plan(report, conda, frozen, specs=None):
    planned=[]
    if specs is None:specs=requirements()
    for item in report.get('install',[]):
        name=canonical(item['metadata']['name']);version=item['metadata']['version']
        if name in {canonical(n) for n in conda} or name in frozen:raise ValueError('pip plan would replace Conda-owned '+name)
        for text in specs:
            req=Requirement(text)
            if canonical(req.name)==name and not req.specifier.contains(version,prereleases=True):
                raise ValueError('pip plan violates compatibility: '+str(req))
        planned.append(name+'=='+version)
    return planned


def validate_conda_plan(plan, conda, pip):
    actions=plan.get('actions',{})
    linked={i['name'] for i in actions.get('LINK',[])}
    if any(i['name'] not in linked for i in actions.get('UNLINK',[])):
        raise ValueError('Conda plan removes a package without replacement')
    for action in ('LINK','UNLINK'):
        for item in actions.get(action,[]):
            name=item['name']
            # Names catch direct conflicts; archive file inspection catches aliases.
            if canonical(name) in pip:
                raise ValueError('Conda plan crosses ownership boundary: '+name+'; review in an isolated clone')
            if name in ('python','libpython') and not item['version'].startswith('3.14.'):
                raise ValueError('Conda plan changes Python series')


def conda_transaction(plan):
    actions = plan.get('actions',{})
    return {
        action: {item['name']: (item['version'],item.get('build_string') or item['build'])
                 for item in actions.get(action,[])}
        for action in ('UNLINK','LINK')
    }


def validate_additions(plan, installed, requested):
    actions=plan.get('actions',{})
    additions={canonical(item['name']) for item in actions.get('LINK',[])}
    if actions.get('UNLINK') or additions.intersection(canonical(name) for name in installed):
        raise ValueError('Adding missing packages would replace installed packages. Review through --manage.')
    if missing:=set(requested)-additions:
        raise ValueError('Conda plan does not add the required packages: '+', '.join(sorted(missing)))


def conda_plan_token(transaction):
    data = json.dumps(transaction,sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


def report_conda_transaction(transaction):
    before, after = transaction['UNLINK'], transaction['LINK']
    print('Reviewed Conda transaction',flush=True)
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name), after.get(name)
        if old is None:
            operation = 'install'
        elif new is None:
            operation = 'remove'
        else:
            operation = 'replace build'
            try:
                if Version(old[0]) > Version(new[0]):
                    operation = 'downgrade'
                elif Version(old[0]) < Version(new[0]):
                    operation = 'upgrade'
            except InvalidVersion:
                pass
        print(f"{operation:14} {name}: {' '.join(old) if old else 'absent'} -> {' '.join(new) if new else 'absent'}",
              flush=True)
    if not before and not after:
        print('No package changes.',flush=True)


def opencv_migration_targets(targets, conda):
    requested = [item for item in targets if item.split('=',1)[0]!='opencv']
    selected = [*opencv_specs(),'h5py','netcdf4']
    if 'spyder' in conda:
        selected.append('spyder=='+conda['spyder'])
    return [*requested,*selected]


def reverse_constraints(targets):
    """Protect installed dependents without freezing unrelated package versions.

The selected packages' existing forward dependency closure may move. Other
installed packages contribute their declared compatibility ranges, not exact
installed versions. A deliberate --all removes these pip-side restrictions.
"""
    installed={canonical(d.metadata['Name']):d for d in md.distributions()}
    active={}
    for name,dist in installed.items():
        active[name]=[Requirement(s) for s in dist.requires or []
                      if not Requirement(s).marker or Requirement(s).marker.evaluate({'extra':''})]
    movable={canonical(Requirement(s).name) for s in targets}
    previous=set()
    while previous!=movable:
        previous=set(movable)
        movable.update(canonical(q.name) for name in previous for q in active.get(name,[]))
    result=[]
    for name,reqs in active.items():
        if name not in movable:
            for req in reqs:
                if req.url:raise ValueError('Installed dependent uses a URL requirement; review separately: '+name)
                result.append(req.name+str(req.specifier))
    return result


def check_conda_files(cache, links, prefix, pip):
    owned=set()
    for dist in md.distributions():
        if canonical(dist.metadata['Name']) in pip:
            owned.update(str(Path(dist.locate_file(f)).resolve()) for f in dist.files or [])
    for item in links:
        directory=cache/(item['name']+'-'+item['version']+'-'+item['build_string'])
        paths=directory/'info/paths.json'
        if paths.is_file():names=[p['_path'] for p in json.loads(paths.read_text())['paths']]
        elif (directory/'info/files').is_file():names=(directory/'info/files').read_text().splitlines()
        else:raise ValueError('Missing downloaded Conda file manifest for '+item['name'])
        for name in names:
            if name.startswith('site-packages/'):name='lib/python3.14/'+name
            elif name.startswith('python-scripts/'):name='bin/'+name[len('python-scripts/'):]
            if str((prefix/name).resolve()) in owned:
                raise ValueError('Conda package would overwrite pip-owned file: '+name)


def maintain_ide(args):
    """Manage a wholly Conda-owned IDE prefix, independently of lab314."""
    prefix=args.ide_prefix
    protected=[Path('/opt/lab314'),Path('/opt/rpi'),Path('/opt/conda'),Path('/opt/sci')]
    if not prefix.is_absolute() or prefix!=prefix.resolve() or any(prefix.is_relative_to(p) or p.is_relative_to(prefix) for p in protected):
        raise ValueError('Choose a canonical IDE prefix outside existing production prefixes')
    if args.no_deps:raise ValueError('--no-deps does not apply to IDE management')
    existing=prefix.exists()
    if existing:
        if not (prefix/'conda-meta').is_dir() or not (prefix/'bin/python').is_file():
            raise ValueError('Existing IDE prefix is not a managed Conda environment')
        code="import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from lab314_policy import ownership;print(json.dumps(ownership(Path(sys.prefix))))"
        state=json.loads(subprocess.check_output([str(prefix/'bin/python'),'-IB','-c',code,str(Path(__file__).parent)],text=True))
        if state[1]:raise ValueError('IDE has pip-owned packages; review ownership separately before Conda updates')
    if args.apply and (not args.record_dir or args.record_dir.exists() or args.record_dir.is_symlink() or args.record_dir.resolve().is_relative_to(prefix) or any(args.record_dir.resolve().is_relative_to(p) for p in protected)):
        raise ValueError('--apply requires a new external record directory')
    base=[CONDA,'install' if existing else 'create','-p',str(prefix),'--override-channels','-c','conda-forge','--json']
    base+=['--update-specs'] if existing else ['--no-default-packages']
    with tempfile.TemporaryDirectory(prefix='spyder-ide-plan-') as tmp:
        env=dict(os.environ,CONDA_PKGS_DIRS=str(Path(tmp)/'cache'))
        plan=json.loads(subprocess.check_output(base+['--dry-run','spyder'],env=env,text=True))
        if plan.get('success') is False:raise ValueError('IDE solver rejected request: '+str(plan))
        print('IDE PLAN',json.dumps(plan),flush=True)
        if not args.apply:
            print('PLAN ONLY: IDE and scientific environments unchanged');return
        args.record_dir.mkdir(mode=0o700)
        (args.record_dir/'ide-plan.json').write_text(json.dumps(plan,indent=2))
        if existing:
            (args.record_dir/'ide-before-explicit.txt').write_text(subprocess.check_output([CONDA,'list','--explicit','-p',str(prefix)],text=True,env=env))
        links=plan.get('actions',{}).get('LINK',[])
        linked={i['name'] for i in links}
        if any(i['name'] not in linked for i in plan.get('actions',{}).get('UNLINK',[])):
            raise ValueError('IDE plan removes a package without replacement')
        exact=[i['name']+'='+i['version']+'='+i['build_string'] for i in links]
        if exact:subprocess.run(base+['-y','--no-deps',*exact],env=env,check=True)
        result=subprocess.check_output([str(prefix/'bin/python'),'-IB','-c',
            "import spyder,importlib.metadata as m,json;print(json.dumps({'version':m.version('spyder'),'requires':m.requires('spyder')}))"],text=True)
        (args.record_dir/'ide-after.json').write_text(result)
        print('IDE verified. Launch directly:',prefix/'bin/spyder')
        print('Select LAB314_SPYDER_PYTHON='+str(prefix/'bin/python')+' for lab314 kernel maintenance.')
        print('APT Spyder retained. No lab314 packages changed; no automatic rollback.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix',type=Path,default=Path('/opt/lab314'))
    select=parser.add_mutually_exclusive_group(required=True)
    select.add_argument('--package',action='append',help='installed package requirement, repeat for a selected set')
    select.add_argument('--ide-prefix',type=Path,help='plan/create/update a separate Conda Spyder IDE, at an administrator-selected path')
    select.add_argument('--all',action='store_true',help='explicitly update the whole environment')
    select.add_argument('--initialize',action='store_true',help='installer-only: populate a new Conda prefix')
    select.add_argument('--add-spyder',action='store_true',help='add the pinned integrated Spyder to native lab314 without replacing packages')
    select.add_argument('--add-defaults',action='store_true',help='add missing scientific manifest defaults without replacing packages')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--record-dir',type=Path,help='new external directory for before-state and plans; required with --apply')
    parser.add_argument('--no-deps',action='store_true',help='pip only: update selected packages without dependency changes')
    parser.add_argument('--repair',action='store_true',help='reinstall named packages without recreating the environment')
    parser.add_argument('--approved-conda-plan',help='fingerprint from a reviewed OpenCV transaction')
    args=parser.parse_args();prefix=args.prefix
    if args.repair and not args.package:
        raise ValueError('--repair requires at least one --package')
    if args.ide_prefix:
        maintain_ide(args);return
    if prefix!=prefix.resolve() or prefix.resolve()!=Path(sys.prefix).resolve() or prefix in (Path('/opt/rpi'),Path('/opt/conda'),Path('/usr'),Path('/')):
        raise ValueError('Run with the selected lab314 Python; hardware/base/system prefixes are forbidden')
    if platform.python_version().split('.')[:2]!=['3','14']:raise ValueError('Python 3.14 is required')
    if args.apply and (not args.record_dir or args.record_dir.exists() or args.record_dir.is_symlink() or args.record_dir.resolve().is_relative_to(prefix)):
        raise ValueError('--apply requires a new record directory outside the target prefix')
    defaults=missing_scientific_defaults(prefix) if args.add_defaults else []
    if args.add_defaults and not defaults:
        print('KEEP Scientific Python package defaults: all present.')
        return
    add_only=args.add_spyder or args.add_defaults
    conda,pip,frozen=ownership(prefix)
    if not conda:raise ValueError('Missing Conda ownership records')
    selection=prefix/'.lab314-ide.json'
    if selection.is_symlink():raise ValueError('Symlinked IDE selection refused')
    if selection.exists() and set(json.loads(selection.read_text()))!={'interpreter'}:
        raise ValueError('Unexpected existing IDE selection file')
    native=bool({'opencv','py-opencv','spyder'} & conda.keys())
    if args.add_spyder and (not native or 'spyder' in conda or 'spyder' in pip or 'spyder' in frozen):
        raise ValueError('Adding Spyder requires native lab314 without an existing Spyder package')
    if native and 'LAB314_SPYDER_PYTHON' in os.environ:
        raise ValueError('The integrated Conda environment maintains its own Spyder kernel; use the external IDE independently.')
    specs=[] if native else requirements()
    if args.add_defaults:
        targets=defaults
        print('Missing Scientific Python defaults: '+', '.join(defaults),flush=True)
    elif args.add_spyder:
        targets=[f"spyder=={policy()['native']['spyder']}"]
    elif args.initialize:
        if pip:raise ValueError('--initialize requires a new prefix without pip-owned distributions')
        targets=[str(Requirement(s)) for s in specs if canonical(Requirement(s).name) not in conda and canonical(Requirement(s).name) not in frozen]
    elif args.all:targets=list(conda)+list(pip)+specs
    else:targets=args.package
    ctargets=[];ptargets=[]
    for text in targets:
        match=re.fullmatch(r'([A-Za-z0-9_][A-Za-z0-9_.-]*)([<>=!0-9A-Za-z.*,+-]*)',text)
        if not match:raise ValueError('Use a simple package name/version requirement')
        name=canonical(match[1]);cname=next((n for n in conda if canonical(n)==name),None)
        if cname:
            ctargets.append(cname+match[2]);continue
        if add_only:
            ctargets.append(text);continue
        if args.repair and native and name in {'spyder','opencv',*(canonical(n) for n in policy()['pip'] if n!='opencv-python')} and name not in pip and name not in frozen:
            ctargets.append(name+match[2]);continue
        req=Requirement(text)
        if name in frozen:raise ValueError('Use the owning Conda package name for '+name)
        if name in pip or args.initialize or (args.all and name in {canonical(Requirement(s).name) for s in specs}):ptargets.append(str(req))
        else:raise ValueError('Unknown ownership: '+name)
    if ctargets and args.no_deps:raise ValueError('--no-deps is only supported for pip updates')
    opencv_upgrade = native and args.package and any(item=='opencv' for item in ctargets)
    if opencv_upgrade:
        ctargets = opencv_migration_targets(ctargets,conda)
    with tempfile.TemporaryDirectory(prefix='lab314-update-') as tmp:
        work=Path(tmp);constraints=work/'constraints.txt';report=work/'pip-plan.json'
        conda_env=dict(os.environ,CONDA_PKGS_DIRS=str(work/'conda-cache'))
        if add_only:
            conda_env['CONDA_PATH_CONFLICT']='prevent'
        if args.apply:
            args.record_dir.mkdir(mode=0o700)
            (args.record_dir/'before.json').write_text(json.dumps(dict(conda=conda,pip=pip,frozen=frozen),indent=2))
            explicit=subprocess.check_output([CONDA,'list','--explicit','-p',str(prefix)],text=True,env=conda_env)
            (args.record_dir/'conda-explicit.txt').write_text(explicit)
            (args.record_dir/'pip-freeze.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze','--all'],text=True))
        if ctargets:
            base=[CONDA,'install','-p',str(prefix),'--override-channels','-c','conda-forge','--json']
            if args.all:
                base.append('--update-all')
            elif not opencv_upgrade:
                base.append('--freeze-installed')
            if args.repair:base.append('--force-reinstall')
            constraints_for_conda = ['python=3.14']
            if native:
                constraints_for_conda.append('python-gil')
                if args.all:
                    constraints_for_conda.extend(opencv_specs())
                elif not opencv_upgrade:
                    constraints_for_conda.append('opencv=*=qt6*')
            try:
                solved = subprocess.check_output(base+['--dry-run',*ctargets,*constraints_for_conda],
                                                 text=True,stderr=subprocess.PIPE,env=conda_env)
            except subprocess.CalledProcessError as error:
                raise ValueError('Conda solver rejected update:\n'+(error.stdout or error.stderr or '').strip()) from error
            plan=json.loads(solved)
            if plan.get('success') is False:
                raise ValueError('Conda solver rejected update: '+str(plan))
            validate_conda_plan(plan,conda,pip)
            if add_only:
                validate_additions(plan,conda.keys() | pip.keys() | frozen.keys(),
                                   ['spyder'] if args.add_spyder else defaults)
            if native and any(i['name']=='spyder' for i in plan.get('actions',{}).get('LINK',[])):
                solved_spyder(plan)
            print('CONDA PLAN',json.dumps(plan),flush=True)
            if opencv_upgrade:
                transaction = conda_transaction(plan)
                report_conda_transaction(transaction)
                token = conda_plan_token(transaction)
                print('CONDA PLAN TOKEN '+token,flush=True)
                if args.apply and token!=args.approved_conda_plan:
                    raise ValueError('Review this OpenCV transaction and repeat the lifecycle update.')
            if args.apply:
                (args.record_dir/'conda-plan.json').write_text(json.dumps(plan,indent=2))
                # Download into a temporary cache; use the reviewed versions and
                # --no-deps to prevent a different dependency solve at apply time.
                links=plan.get('actions',{}).get('LINK',[])
                exact=[str(i['name'])+'='+i['version']+'='+i['build_string'] for i in links]
                if exact:
                    env=conda_env
                    apply=[CONDA,'install','-y','-p',str(prefix),'--no-deps','--override-channels','-c','conda-forge',*exact]
                    if args.repair:apply.append('--force-reinstall')
                    subprocess.run(apply+['--download-only'],env=env,check=True)
                    check_conda_files(work/'conda-cache',links,prefix,pip)
                    if add_only:
                        exact_plan=json.loads(subprocess.check_output(apply+['--dry-run','--offline','--json'],env=env,text=True))
                        if (exact_plan.get('success') is False or
                                conda_transaction(exact_plan)!=conda_transaction(plan)):
                            raise ValueError('Offline transaction differs from the reviewed add-only plan')
                    subprocess.run(apply+['--offline'],env=env,check=True)
                # Re-inventory after Conda: never freeze stale ownership/version data.
                conda,pip,frozen=ownership(prefix)
        if ptargets:
            env=dict(os.environ,PIP_NO_CACHE_DIR='1',TMPDIR=str(work))
            constraints.write_text('\n'.join(specs+reverse_constraints(ptargets)+[n+'=='+v for n,v in frozen.items()])+'\n')
            subprocess.run(pip_plan_args(sys.executable,ptargets,constraints,report,args.no_deps,args.initialize,args.repair),env=env,check=True)
            plan=json.loads(report.read_text());exact=validate_pip_plan(plan,conda,frozen,specs)
            print('PIP PLAN',exact,flush=True)
            if args.apply:
                (args.record_dir/'pip-plan.json').write_text(json.dumps(plan,indent=2))
                if exact:
                    config=policy()
                    subprocess.run([sys.executable,'-IB','-m','pip','install','--no-deps','--only-binary=:all:',
                                    '--index-url',config['pip_index'],'--extra-index-url',config['pip_extra_index'],
                                    *(['--force-reinstall'] if args.repair else []),*exact],env=env,check=True)
        if args.apply and not args.initialize and not native and not args.add_defaults:
            fonts=prefix/'lib/python3.14/site-packages/cv2/qt/fonts'
            fonts.mkdir(parents=True,exist_ok=True)
            for name in ('DejaVuSans.ttf','DejaVuSans-Bold.ttf'):
                target=fonts/name
                if not target.exists() and not target.is_symlink():
                    source=Path('/usr/share/fonts/truetype/dejavu')/name
                    if not source.is_file():raise ValueError('Missing Qt font '+name)
                    target.symlink_to(source)
        if args.apply and not args.initialize:
            verify = [sys.executable,'-IB',str(Path(__file__).with_name('check_lab314.py')),
                      '--prefix',str(prefix),'--functional']
            if opencv_upgrade or (native and args.all):
                verify.append('--require-opencv-target')
            if 'spyder' in conda:
                verify.append('--require-spyder')
            subprocess.run(verify,check=True)
        if args.apply and not args.add_defaults and 'LAB314_SPYDER_PYTHON' in os.environ:
            data=json.dumps({'interpreter':os.environ['LAB314_SPYDER_PYTHON']})+'\n'
            if not selection.exists() or selection.read_text()!=data:
                with tempfile.NamedTemporaryFile(mode='w',dir=prefix,delete=False) as f:
                    f.write(data);saved=Path(f.name)
                saved.chmod(0o644);os.replace(saved,selection)
        print('APPLIED; see records; no automatic rollback' if args.apply else 'PLAN ONLY: no packages changed')


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.SubprocessError) as exc:sys.exit('ERROR: '+str(exc))
