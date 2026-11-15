"""Camera-free Bash step and release contract tests."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
INSTALL = BASE/'install'


class AppTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir='/tmp')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.src = self.root/'source/app'
        self.src.mkdir(parents=True)
        self.target = self.root/'sci'
        self.entry = self.src/'entry.py'
        self.entry.write_text('#!/usr/bin/env python3\nimport sys\nprint("demo 1" if "--version" in sys.argv else sys.executable)\n')
        self.helper = self.src/'private.py'
        self.helper.write_text('VALUE = 1\n')
        self.profile = self.root/'demo.json'
        self.data = dict(name='demo',version='1',category='bin',source='app',entry='entry.py',
                         environment='system',interpreter='/usr/bin/python3',dependencies=['json'],
                         import_root='modules',verify_imports=[],version_output='demo 1',
                         files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.entry,self.helper)})
        self.link = self.target/'bin/demo'
        self.env=dict(os.environ, PATH='/usr/bin:/bin',HOME=str(self.root),CONDA_PREFIX='')
        self.env.pop('PYTHONPATH',None)

    def step(self,*args,ok=True,verify=False):
        self.profile.write_text(json.dumps(self.data))
        cmd='verify_sci_apps.sh' if verify else 'install_sci_apps.sh'
        result=subprocess.run(['bash',str(INSTALL/cmd),'--source',str(self.src.parent),
                               '--target',str(self.target),'--profile',str(self.profile),*args],
                               input='',capture_output=True,text=True,env=self.env)
        self.assertEqual(result.returncode==0,ok,result.stdout+result.stderr)
        return result

    def install(self):
        return self.step('--approve','demo')

    def test_plan_and_refusal(self):
        self.step('--plan')
        self.step(ok=False)
        self.step('--approve','different',ok=False)
        self.assertFalse(self.target.exists())

    def test_layout_and_reinstall(self):
        old=self.entry.read_bytes()
        self.install()
        self.assertEqual({p.name for p in self.target.iterdir()},{'bin','lib','bin-rpi'})
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o755 for p in self.target.iterdir()))
        self.assertEqual(self.link.read_bytes().partition(b'\n')[2],old.partition(b'\n')[2])
        self.assertEqual(self.entry.read_bytes(),old)
        self.assertEqual(subprocess.check_output([self.link]).strip(),b'/usr/bin/python3')
        body=self.target/'lib/demo-1/private.py'
        self.assertEqual(body.read_bytes(),self.helper.read_bytes())
        before={p:p.lstat().st_ctime_ns for p in self.target.rglob('*')}
        self.assertIn('KEEP',self.install().stdout)
        self.step(verify=True)
        self.assertEqual(before,{p:p.lstat().st_ctime_ns for p in before})

    def test_portable(self):
        self.data.update(environment='portable',interpreter='/usr/bin/env python3')
        self.install()
        self.assertEqual(self.link.read_bytes(),self.entry.read_bytes())

    def test_missing_dependency(self):
        self.data['dependencies']=['imaginary_module_for_test']
        self.step('--approve','demo',ok=False)
        self.assertFalse(self.target.exists())

    def test_missing_source(self):
        self.helper.unlink()
        self.step('--approve','demo',ok=False)
        self.assertFalse(self.target.exists())

    def test_invalid_profile(self):
        self.data['entry']='../escape'
        self.step('--approve','demo',ok=False)
        self.assertFalse(self.target.exists())

    def test_changed_helper(self):
        self.install()
        (self.target/'lib/demo-1/private.py').write_text('changed')
        self.step(verify=True,ok=False)
        self.step('--remove','--approve','demo',ok=False)
        self.assertTrue(self.link.exists())

    def test_foreign_command(self):
        self.link.parent.mkdir(parents=True)
        self.link.write_text('older install')
        self.step('--approve','demo',ok=False)
        self.assertEqual(self.link.read_text(),'older install')

    def test_stage_failure(self):
        self.data['version_output']='wrong'
        self.step('--approve','demo',ok=False)
        self.assertFalse(self.target.exists())

    def test_interrupted_publish_rolls_back(self):
        fault=self.root/'commands'
        fault.mkdir()
        mv=fault/'mv'
        mv.write_text('#!/bin/sh\n/bin/mv "$@" || exit 1\nkill -TERM "$PPID"\n')
        mv.chmod(0o755)
        self.env['PATH']=str(fault)+':'+self.env['PATH']
        self.step('--approve','demo',ok=False)
        self.assertFalse(self.target.exists())
        self.assertTrue(self.entry.read_bytes().startswith(b'#!/usr/bin/env python3'))

    def test_missing_environment(self):
        if Path('/opt/rpi/bin/python3').exists():
            self.skipTest('this fixture requires a machine without the rpi prefix')
        self.data.update(environment='rpi',interpreter='/opt/rpi/bin/python3')
        self.step('--approve','demo',ok=False)
        self.assertFalse(self.target.exists())

    def test_remove_and_reinstall(self):
        self.install()
        self.step('--remove','--approve','demo')
        self.assertFalse(self.link.is_symlink())
        self.assertEqual(list((self.target/'lib').iterdir()),[])
        self.install()

    def test_symlink_and_wrong_interpreter(self):
        self.target.symlink_to(self.src)
        self.step('--approve','demo',ok=False)
        self.target.unlink()
        self.data['interpreter']='/opt/conda/bin/python'
        self.step('--approve','demo',ok=False)

    def test_write_permission(self):
        if os.geteuid()==0:
            self.skipTest('requires unprivileged account')
        self.target.mkdir(mode=0o555)
        self.addCleanup(self.target.chmod,0o755)
        self.step('--approve','demo',ok=False)
        self.assertEqual(list(self.target.iterdir()),[])


class BaseTests(unittest.TestCase):
    def test_shell_startup(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root=Path(tmp)
            prefix=root/'lab314'
            subprocess.run(['/usr/bin/python3','-m','venv','--without-pip',prefix],check=True)
            # Fake ONLY Conda activation, then execute both actual venv binaries.
            hook=root/'conda.sh'
            hook.write_text('''__conda_reactivate() { :; }
conda() {
                if [[ $1 == activate ]]; then
                    oldpath=$PATH; export PATH="$2/bin:$PATH" CONDA_PREFIX="$2"; PS1="(lab314) $PS1"
                else
                    export PATH="$oldpath"; unset CONDA_PREFIX; PS1='bash$ '
                fi
            }
''')
            block=(INSTALL/'lab314-bash.sh').read_text()
            profile=root/'sci-path.sh';profile.write_text((INSTALL/'sci-path.sh').read_text())
            bashrc=root/'bashrc'
            bashrc.write_text(block.replace('/opt/lab314',str(prefix)).replace('/opt/conda/etc/profile.d/conda.sh',str(hook)).replace('/etc/profile.d/sci-path.sh',str(profile)))
            for login in (True,False):
                script=f'PATH=/usr/bin:/bin; . "{bashrc}"; '
                if login:
                    script+=f'. "{profile}"; '
                script+='''__lab314_before_prompt; [[ $PS1 == "(lab314) "* ]] && python -c 'import os,sys;assert sys.prefix==os.environ["CONDA_PREFIX"]' &&
                    python3 -c 'import os,sys;assert sys.prefix==os.environ["CONDA_PREFIX"]' &&
                    [[ ${PATH//:/ } == *"/opt/sci/bin /opt/sci/bin-rpi"* ]] &&
                    [[ $(tr : '\\n' <<< "$PATH" | sort | uniq -d | wc -l) == 0 ]] &&
                    conda deactivate && [[ $(command -v python3) == /usr/bin/python3 ]]'''
                flags=['--login'] if login else []
                result=subprocess.run(['bash',*flags,'--noprofile','--norc','-ic',script],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertNotIn('export PATH=/opt/conda/bin:',(INSTALL/'install_conda_base.sh').read_text())

    def test_existing_profiles(self):
        # Exercise actual orchestration, replacing only device-changing steps.
        for name in ('home','aalto'):
            for selected in (False,True):
                with self.subTest(name=name,selected=selected),tempfile.TemporaryDirectory(dir='/tmp') as tmp:
                    root=Path(tmp)
                    run=INSTALL/f'run_rpi_{name}.sh'
                    shutil.copy(run,root/run.name)
                    log=root/'steps'
                    for step in INSTALL.glob('*.sh'):
                        if step!=run:
                            (root/step.name).write_text(f'echo "{step.name} $*" >> "{log}"\n')
                    args=[]
                    if selected:
                        entry=root/'apps/capture/rpi/cam-imgcheck/cam-imgcheck.py'
                        entry.parent.mkdir(parents=True);entry.touch()
                        args=['--with-cam-imgcheck',tmp]
                    subprocess.run(['bash',root/run.name,*args],check=True,capture_output=True)
                    steps=[line.split()[0] for line in log.read_text().splitlines()]
                    expected=[f'pre_{name}.sh','install_rpi_base.sh','install_conda_base.sh','create_lab314_env.sh']
                    if selected and not Path('/opt/rpi').exists():
                        expected+=['create_rpi_env.sh']
                    expected+=['enable_lab314_autoactivate_rpi.sh','install_envrun.sh']
                    if selected:expected+=['install_sci_apps.sh']
                    expected+=['verify_rpi_lab314.sh']
                    if selected:expected+=['verify_rpi_env.sh','verify_sci_apps.sh']
                    self.assertEqual(steps,expected)


if __name__=='__main__':
    unittest.main()
