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

CONFIG = Path(__file__).resolve().parents[1]/'config/lab314'


def policy():
    return json.loads((CONFIG/'requirements.json').read_text())


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


def version_errors(versions, python, snapshot=False):
    config = json.loads((CONFIG/'packages.json').read_text()) if snapshot else policy()
    expected = '=='+config['python']
    errors=[]
    if not SpecifierSet(expected).contains(python):errors.append('Unsupported Python '+python+'; required '+expected)
    versions={canonical(k):v for k,v in versions.items()}
    specs=[k+'=='+v for k,v in config['packages'].items()] if snapshot else requirements()
    for text in specs:
        req=Requirement(text);found=versions.get(canonical(req.name))
        if found is None or not req.specifier.contains(found,prereleases=True):
            errors.append(str(req)+': installed '+str(found))
    if not snapshot:
        for name in ('opencv-python-headless','opencv-contrib-python','opencv-contrib-python-headless'):
            if canonical(name) in versions:errors.append('Conflicting OpenCV distribution: '+name)
    return errors


def ownership(prefix):
    """Conda records take precedence over INSTALLER labels, including file overlap."""
    conda={};owned=set()
    for f in (prefix/'conda-meta').glob('*.json'):
        record=json.loads(f.read_text());conda[record['name']]=record['version']
        owned.update(str((prefix/n).resolve()) for n in record.get('files',[]))
    pip={};frozen={}
    for dist in md.distributions():
        if not Path(dist.locate_file('')).resolve().is_relative_to(prefix.resolve()):continue
        name=canonical(dist.metadata['Name'])
        overlap=any(str(Path(dist.locate_file(f)).resolve()) in owned for f in dist.files or [])
        if name in {canonical(n) for n in conda} or overlap:frozen[name]=dist.version
        elif (dist.read_text('INSTALLER') or '').strip()=='pip':pip[name]=dist.version
    return conda,pip,frozen


if __name__=='__main__':
    print('\n'.join(requirements()))
