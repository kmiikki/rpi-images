"""Isolated lifecycle plans and ownership checks; no real package operations."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'install'))
import lab314_policy as policy
import update_lab314 as update
ORIGINAL_SPYDER=policy.spyder_requirement
KERNEL='spyder-kernels>=3.0.3,<3.1.0'


class RollingTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.prefix=self.root/'env';self.prefix.mkdir()
        self.spy=patch.object(policy,'spyder_requirement',return_value=KERNEL);self.spy_mock=self.spy.start();self.addCleanup(self.spy.stop)

    def test_normal_accepts_updated_distribution_snapshot_rejects(self):
        versions=json.loads((BASE/'config/lab314/packages.json').read_text())['packages']
        versions['numpy']='2.5.5'
        self.assertEqual(policy.version_errors(versions,'3.14.11'),[])
        self.assertTrue(policy.version_errors(versions,'3.14.11',snapshot=True))

    def test_python_minor_and_kernel_incompatibility_rejected(self):
        versions=json.loads((BASE/'config/lab314/packages.json').read_text())['packages']
        versions['spyder-kernels']='3.1.0'
        errors=policy.version_errors(versions,'3.15.0')
        self.assertTrue(any('Python' in e for e in errors));self.assertTrue(any('spyder-kernels' in e for e in errors))
        with self.assertRaisesRegex(ValueError,'compatibility'):
            update.validate_pip_plan({'install':[{'metadata':{'name':'spyder-kernels','version':'3.1.0'}}]}, {},{})

    def test_pip_targeted_strategy_and_frozen_conda(self):
        args=update.pip_plan_args('python',['urllib3>=2.8.1'],self.root/'constraints',self.root/'report')
        self.assertIn('only-if-needed',args);self.assertNotIn('--no-deps',args)
        self.assertEqual(args[-1],'urllib3>=2.8.1');self.assertNotIn('--all',args)
        with self.assertRaisesRegex(ValueError,'Conda-owned'):
            update.validate_pip_plan({'install':[{'metadata':{'name':'pip','version':'26.3'}}]}, {'pip':'26.2.2'},{'pip':'26.2.2'})

    def test_conda_plan_guards(self):
        known={'python':'3.14.10','pip':'26.2.2','openssl':'3.6.5'}
        update.validate_conda_plan({'actions':{'LINK':[{'name':'openssl','version':'3.6.6'}]}},known,{'numpy':'2.5.4'})
        for record in [{'name':'python','version':'3.15.0'},{'name':'numpy','version':'2.5.5'}]:
            with self.assertRaises(ValueError):update.validate_conda_plan({'actions':{'LINK':[record]}},known,{'numpy':'2.5.4'})
        with self.assertRaises(ValueError):update.validate_conda_plan({'actions':{'UNLINK':[{'name':'pip','version':'26.2.2'}]}},known,{})

    def test_conda_new_dependency_files_are_checked_before_link(self):
        update.validate_conda_plan({'actions':{'LINK':[{'name':'new-native-dependency','version':'1'}]}},{'python':'3.14.10'},{})
        cache=self.root/'cache';package=cache/'alias-1-0/info';package.mkdir(parents=True)
        (package/'files').write_text('site-packages/numpy/__init__.py\n')
        class Dist:
            metadata={'Name':'numpy'};files=['numpy/__init__.py']
            def locate_file(d,f):return self.prefix/'lib/python3.14/site-packages'/str(f)
        with patch.object(update.md,'distributions',return_value=[Dist()]),self.assertRaisesRegex(ValueError,'overwrite'):
            update.check_conda_files(cache,[dict(name='alias',version='1',build_string='0')],self.prefix,{'numpy':'2.5.4'})

    def test_conda_file_ownership_overrides_installer_label(self):
        meta=self.prefix/'conda-meta';meta.mkdir()
        (meta/'pip.json').write_text(json.dumps(dict(name='pip',version='26.2.2',files=['site/fake.dist-info/METADATA'])))
        class Dist:
            metadata={'Name':'alias'};version='1';files=['fake.dist-info/METADATA']
            def locate_file(d,f):return self.prefix/'site'/str(f)
            def read_text(d,n):return 'pip'
        with patch.object(policy.md,'distributions',return_value=[Dist()]):
            conda,pip,frozen=policy.ownership(self.prefix)
        self.assertFalse(pip);self.assertEqual(frozen,{'alias':'1'})

    def run_manager(self,package,version,conda=False,all_packages=False,current=False):
        calls=[];records=self.root/'records'
        def run(args,**kwargs):
            calls.append(args)
            if '--report' in args:
                Path(args[args.index('--report')+1]).write_text(json.dumps({'install':[] if current else [{'metadata':dict(name=package,version=version)}]}))
            return None
        def output(args,**kwargs):
            calls.append(args)
            if '--dry-run' in args:return json.dumps({'success':True,'actions':{'LINK':[] if current else [dict(name='pip' if all_packages else package,version='26.2.3' if all_packages else version,build_string='0')]}})
            return 'fixture before state\n'
        ownership=({'python':'3.14.10','pip':'26.2.2'}, {'urllib3':'2.8.0','spyder-kernels':'3.0.5','numpy':'2.5.4','scipy':'1.18.1','opencv-python':'5.0.0.93','shapely':'2.2.0'}, {'pip':'26.2.2'})
        argv=['update','--prefix',str(self.prefix),*(['--all'] if all_packages else ['--package',package]),'--apply','--record-dir',str(records)]
        with patch.object(sys,'argv',argv),patch.object(sys,'prefix',str(self.prefix)),patch.object(update.platform,'python_version',return_value='3.14.10'),patch.object(update,'ownership',return_value=ownership),patch.object(update.subprocess,'run',side_effect=run),patch.object(update.subprocess,'check_output',side_effect=output),patch.object(update,'check_conda_files'),patch.object(update,'reverse_constraints',return_value=[]),contextlib.redirect_stdout(io.StringIO()):
            update.main()
        self.assertTrue((records/'before.json').is_file())
        self.assertTrue(any('check_lab314.py' in ' '.join(c) for c in calls))
        return calls

    def test_security_update_is_planned_applied_and_verified(self):
        calls=self.run_manager('urllib3','2.8.1')
        apply=[c for c in calls if 'install' in c and '--dry-run' not in c]
        self.assertEqual(len(apply),1);self.assertIn('urllib3==2.8.1',apply[0]);self.assertIn('--no-deps',apply[0])
        self.assertNotIn('numpy',' '.join(apply[0]))

    def test_spyder_kernel_update_does_not_update_scientific_stack(self):
        calls=self.run_manager('spyder-kernels','3.0.6')
        apply=[c for c in calls if 'install' in c and '--dry-run' not in c][0]
        self.assertIn('spyder-kernels==3.0.6',apply)
        self.assertNotIn('numpy',' '.join(apply));self.assertFalse(any('apt' in c for c in calls))

    def test_spyder_605_to_618_compatibility_transition(self):
        versions=json.loads((BASE/'config/lab314/packages.json').read_text())['packages']
        self.assertFalse(policy.version_errors(versions,'3.14.10'))
        self.spy_mock.return_value='spyder-kernels>=3.1.0,<3.2.0'
        self.assertTrue(any('spyder-kernels' in e for e in policy.version_errors(versions,'3.14.10')))
        calls=self.run_manager('spyder-kernels','3.1.7')
        self.assertTrue(any('spyder-kernels==3.1.7' in c for c in calls))
        versions['spyder-kernels']='3.1.7'
        self.assertEqual(policy.version_errors(versions,'3.14.11'),[])
        versions['spyder-kernels']='3.2.0'
        self.assertTrue(policy.version_errors(versions,'3.14.11'))

    def test_conda_selected_update_is_not_update_all(self):
        calls=self.run_manager('pip','26.2.3',conda=True)
        plan=next(c for c in calls if '--dry-run' in c)
        self.assertIn('--freeze-installed',plan);self.assertIn('python=3.14',plan)
        self.assertNotIn('--all',plan);self.assertNotIn('numpy',' '.join(plan))

    def test_reverse_dependency_ranges_are_not_permanent_version_pins(self):
        class Dist:
            def __init__(d,name,requires):d.metadata={'Name':name};d.requires=requires
        with patch.object(update.md,'distributions',return_value=[Dist('numpy',[]),Dist('numba',['numpy<3'])]):
            self.assertEqual(update.reverse_constraints(['numpy']),['numpy<3'])
            self.assertEqual(update.reverse_constraints(['numpy','numba']),[])

    def test_current_environment_does_not_reinstall_packages(self):
        calls=self.run_manager('numpy','2.5.4',all_packages=True,current=True)
        self.assertFalse(any('install' in c and '--dry-run' not in c for c in calls))

    def test_explicit_ide_selection_is_saved_and_reused(self):
        ide=str(self.root/'ide/bin/python')
        with patch.dict(os.environ,LAB314_SPYDER_PYTHON=ide):self.run_manager('spyder-kernels','3.0.6')
        self.assertEqual(json.loads((self.prefix/'.lab314-ide.json').read_text()),{'interpreter':ide})
        with patch.object(policy,'spyder_requirement',ORIGINAL_SPYDER),patch.object(sys,'prefix',str(self.prefix)),patch.dict(os.environ,{},clear=True),patch.object(policy.subprocess,'run') as run:
            run.return_value.returncode=0;run.return_value.stdout=json.dumps([KERNEL])
            policy.spyder_requirement()
            self.assertEqual(run.call_args.args[0][0],ide)

    def test_selected_scientific_library_is_not_frozen(self):
        calls=self.run_manager('numpy','2.5.5')
        apply=[c for c in calls if 'install' in c and '--dry-run' not in c][0]
        self.assertIn('numpy==2.5.5',apply)
        self.assertNotIn('scipy',' '.join(apply))

    def test_explicit_all_requests_all_scientific_roots(self):
        calls=self.run_manager('numpy','2.5.5',all_packages=True)
        conda_plan=next(c for c in calls if '--dry-run' in c)
        self.assertIn('--update-all',conda_plan)
        pip_plan=next(c for c in calls if '--report' in c)
        for name in ('numpy','scipy','opencv-python','shapely'):self.assertIn(name,pip_plan)

    def test_separate_ide_plan_and_apply_do_not_touch_lab314(self):
        ide=self.root/'chosen-ide';records=self.root/'ide-records';calls=[]
        plan={'success':True,'actions':{'LINK':[dict(name='spyder',version='6.1.8',build_string='0')]}}
        def output(args,**kwargs):
            calls.append(args)
            if '--dry-run' in args:return json.dumps(plan)
            return json.dumps({'version':'6.1.8','requires':['spyder-kernels>=3.1.0,<3.2.0']})
        def run(args,**kwargs):calls.append(args)
        with patch.object(sys,'argv',['update','--ide-prefix',str(ide),'--apply','--record-dir',str(records)]),patch.object(update.subprocess,'check_output',side_effect=output),patch.object(update.subprocess,'run',side_effect=run),contextlib.redirect_stdout(io.StringIO()):
            update.main()
        self.assertTrue((records/'ide-plan.json').exists())
        self.assertTrue(any('spyder=6.1.8=0' in c for c in calls))
        self.assertFalse(any('/opt/lab314' in c or '/opt/rpi' in c for c in calls))

    def test_selected_ide_metadata_is_used(self):
        # Undo the fixture's metadata override for this isolated interpreter test.
        with patch.object(policy,'spyder_requirement',ORIGINAL_SPYDER),patch.dict(os.environ,LAB314_SPYDER_PYTHON='/administrator/chosen/bin/python'),patch.object(policy.subprocess,'run') as run:
            run.return_value.returncode=0
            run.return_value.stdout=json.dumps(['spyder-kernels>=3.1.0,<3.2.0'])
            self.assertIn('3.1.0',policy.spyder_requirement())
            self.assertEqual(run.call_args.args[0][0],'/administrator/chosen/bin/python')

    def test_normal_and_snapshot_install_command_paths(self):
        for snapshot in (False,True):
            with self.subTest(snapshot=snapshot),tempfile.TemporaryDirectory(dir=self.root) as tmp:
                root=Path(tmp);install=root/'install';install.mkdir();shutil.copytree(BASE/'config',root/'config')
                log=root/'calls';prefix=root/'prefix'
                conda=root/'conda';conda.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "'+str(log)+'"\nmkdir -p "'+str(prefix)+'/bin"\ncp "'+str(root/'python')+'" "'+str(prefix)+'/bin/python"\n')
                conda.chmod(0o755)
                (root/'python').write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "'+str(log)+'"\n');(root/'python').chmod(0o755)
                fake=root/'bin';fake.mkdir();(fake/'uname').write_text('#!/bin/sh\necho aarch64\n');(fake/'uname').chmod(0o755)
                (install/'lab314_policy.py').write_text('print("numpy")\n')
                source=(BASE/'install/create_lab314_env.sh').read_text().replace('/opt/conda/bin/conda',str(conda))
                (install/'create.sh').write_text(source)
                import subprocess
                result=subprocess.run(['bash',str(install/'create.sh'),'--prefix',str(prefix),*(['--snapshot'] if snapshot else [])],env=dict(os.environ,PATH=str(fake)+':/usr/bin:/bin'),capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                text=log.read_text()
                self.assertEqual('--file' in text,snapshot);self.assertEqual('--require-hashes' in text,snapshot)
                self.assertEqual('--initialize' in text,not snapshot)
                if not snapshot:self.assertIn('python=3.14',text)


if __name__=='__main__':unittest.main()
