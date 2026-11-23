"""Shared, small requirement/ownership helpers for lab314 lifecycle commands."""
import importlib.metadata as md
import json
import os
import sys
from pathlib import Path
import subprocess
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name as canonical
from packaging.specifiers import SpecifierSet
from packaging.version import Version

CONFIG = Path(__file__).resolve().parents[1]/'config/lab314'


def policy():
    return json.loads((CONFIG/'requirements.json').read_text())


def opencv_specs():
    versions = policy()['native']
    return [f"opencv={versions['opencv']}=qt6*", f"hdf5={versions['hdf5']}"]


def native_conda_specs(with_spyder=True):
    config = policy()
    specs = [*config['conda'], 'python-gil', *opencv_specs()]
    specs.extend(name.lower() for name in config['pip'] if name != 'opencv-python')
    if with_spyder:
        specs.append(f"spyder=={config['native']['spyder']}")
    return specs


def native_layout(prefix):
    return any(path for name in ('opencv','py-opencv','spyder')
               for path in (Path(prefix)/'conda-meta').glob(f'{name}-[0-9]*.json'))


def prefix_distributions(prefix):
    root=prefix.resolve()
    return (dist for dist in md.distributions()
            if Path(dist.locate_file('')).resolve().is_relative_to(root))


def missing_scientific_defaults(prefix):
    """Find absent direct defaults. OpenCV has its own layout-specific installer."""
    installed={canonical(dist.metadata['Name']) for dist in prefix_distributions(prefix)}
    return [canonical(name) for name in policy()['pip']
            if name!='opencv-python' and canonical(name) not in installed]


def solved_spyder(plan):
    for record in plan.get('actions', {}).get('LINK', []):
        if record['name'] == 'spyder':
            version = Version(record['version'])
            if not (version.is_prerelease or version.is_devrelease):
                return record['version']
            raise ValueError(f'The conda-forge solve selected a non-stable Spyder version: {version}')
    raise ValueError('The conda-forge solve did not select a Spyder package')


def spyder_requirement():
    # Read the selected external IDE's metadata in its interpreter, never import it here.
    code = "import importlib.metadata as m,json; print(json.dumps(m.requires('spyder')))"
    selected=Path(sys.prefix)/'.lab314-ide.json'
    if selected.is_symlink():raise ValueError('Symlinked IDE selection refused')
    saved=json.loads(selected.read_text())['interpreter'] if selected.is_file() else policy()['spyder_python']
    exe=os.environ.get('LAB314_SPYDER_PYTHON',saved)
    if not Path(exe).is_absolute():raise ValueError('Select an absolute IDE interpreter')
    if any(Path(exe).resolve().is_relative_to(Path(p)) for p in ('/opt/lab314','/opt/rpi')):
        raise ValueError('The IDE must be separate from scientific/hardware environments')
    result = subprocess.run([exe,'-IB','-c',code],capture_output=True,text=True)
    if result.returncode:
        raise ValueError('Selected Spyder IDE metadata unavailable: '+exe)
    for text in json.loads(result.stdout):
        req = Requirement(text)
        if canonical(req.name)=='spyder-kernels':
            return str(req)
    raise ValueError('Installed Spyder does not declare a spyder-kernels requirement')


def requirements():
    return list(policy()['pip'])+[spyder_requirement()]


def version_errors(versions, python, snapshot=False, native=False):
    config = json.loads((CONFIG/'packages.json').read_text()) if snapshot else policy()
    expected = '=='+config['python']
    errors=[]
    if not SpecifierSet(expected).contains(python):errors.append('Unsupported Python '+python+'; required '+expected)
    versions={canonical(k):v for k,v in versions.items()}
    if snapshot:
        specs=[k+'=='+v for k,v in config['packages'].items()]
    elif native:
        specs=list(config['pip'])
        # Conda OpenCV exports the opencv-python distribution metadata. Read
        # Spyder's actual kernel constraint from the installed IDE in this prefix.
        if 'spyder' in versions:
            kernel_specs = [text for text in md.requires('spyder') or []
                            if canonical(Requirement(text).name)=='spyder-kernels']
            if not kernel_specs:errors.append('Integrated Spyder does not declare a kernel requirement')
            if Version(versions['spyder']).is_prerelease:errors.append('Integrated Spyder must be a stable release')
            specs.extend(kernel_specs)
    else:
        specs=requirements()
    for text in specs:
        req=Requirement(text);found=versions.get(canonical(req.name))
        if found is None or not req.specifier.contains(found,prereleases=True):
            errors.append(str(req)+': installed '+str(found))
    if not snapshot:
        for name in ('opencv-python-headless','opencv-contrib-python','opencv-contrib-python-headless'):
            if name not in versions:continue
            # Conda-forge's Qt build publishes same-version headless metadata
            # to satisfy dependency declarations; it ships only one cv2 module.
            if native and name=='opencv-python-headless' and versions[name]==versions.get('opencv-python'):continue
            errors.append('Conflicting OpenCV distribution: '+name)
    return errors


def ownership(prefix):
    """Conda records take precedence over INSTALLER labels, including file overlap."""
    conda={};owned=set()
    for f in (prefix/'conda-meta').glob('*.json'):
        record=json.loads(f.read_text());conda[record['name']]=record['version']
        owned.update(str((prefix/n).resolve()) for n in record.get('files',[]))
    pip={};frozen={}
    for dist in prefix_distributions(prefix):
        name=canonical(dist.metadata['Name'])
        overlap=any(str(Path(dist.locate_file(f)).resolve()) in owned for f in dist.files or [])
        if name in {canonical(n) for n in conda} or overlap:frozen[name]=dist.version
        elif (dist.read_text('INSTALLER') or '').strip()=='pip':pip[name]=dist.version
    return conda,pip,frozen


if __name__=='__main__':
    if sys.argv[1:] in (['--conda-specs','integrated'], ['--conda-specs','none']):
        print('\n'.join(native_conda_specs(sys.argv[-1]=='integrated')))
    elif sys.argv[1:] == ['--solved-spyder']:
        try:print(solved_spyder(json.load(sys.stdin)))
        except ValueError as error:sys.exit(f'ERROR: {error}')
    else:
        print('\n'.join(requirements()))
