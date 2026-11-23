"""Isolated lifecycle plans and ownership checks; no real package operations."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
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
ADDED_DEFAULTS={
    'shap':'0.51.0', 'pywavelets':'1.9.0', 'optuna':'4.8.0', 'plotly':'6.8.0',
    'hypothesis':'6.150.0', 'polars':'1.41.0', 'xgboost':'3.2.0',
}


def rolling_versions():
    snapshot=json.loads((BASE/'config/lab314/packages.json').read_text())['packages']
    return snapshot | ADDED_DEFAULTS


class RollingTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.prefix=self.root/'env';self.prefix.mkdir()
        self.spy=patch.object(policy,'spyder_requirement',return_value=KERNEL);self.spy_mock=self.spy.start();self.addCleanup(self.spy.stop)

    def test_normal_accepts_updated_distribution_snapshot_rejects(self):
        versions=rolling_versions()
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
        versions=rolling_versions()
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
                conda=root/'conda';conda.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "'+str(log)+'"\n'
                    'if [[ " $* " == *" --dry-run "* ]]; then echo \'{"actions":{"LINK":[{"name":"spyder","version":"6.1.8"}]}}\'; exit 0; fi\n'
                    'mkdir -p "'+str(prefix)+'/bin"\ncp "'+str(root/'python')+'" "'+str(prefix)+'/bin/python"\n')
                conda.chmod(0o755)
                (root/'python').write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "'+str(log)+'"\n');(root/'python').chmod(0o755)
                fake=root/'bin';fake.mkdir();(fake/'uname').write_text('#!/bin/sh\necho aarch64\n');(fake/'uname').chmod(0o755)
                shutil.copy(BASE/'install/lab314_policy.py',install)
                source=(BASE/'install/create_lab314_env.sh').read_text().replace('/opt/conda/bin/conda',str(conda)).replace('/opt/conda/bin/python',sys.executable)
                (install/'create.sh').write_text(source)
                result=subprocess.run(['bash',str(install/'create.sh'),'--prefix',str(prefix),*(['--snapshot'] if snapshot else [])],env=dict(os.environ,PATH=str(fake)+':/usr/bin:/bin'),capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                text=log.read_text()
                self.assertEqual('--file' in text,snapshot);self.assertEqual('--require-hashes' in text,snapshot)
                self.assertNotIn('--initialize',text)
                if not snapshot:
                    for expected in ('python=3.14','opencv=5.1.0=qt6*','hdf5=1.14.6','--dry-run',
                                     'spyder==6.1.8','--require-spyder','--require-opencv-target'):
                        self.assertIn(expected,text)

    def test_creation_preserves_failure_code_and_identifies_subphase(self):
        cases = (
            ('solver', 17, 'resolving ARM64', 'solver diagnostic'),
            ('download', 18, 'downloading and installing', 'download diagnostic'),
            ('verify', 19, 'checking installed packages', 'verification diagnostic'),
        )
        install = self.root/'install'
        install.mkdir()
        shutil.copytree(BASE/'config', self.root/'config')
        shutil.copy(BASE/'install/lab314_policy.py', install)
        fake = self.root/'bin'
        fake.mkdir()
        uname = fake/'uname'
        uname.write_text('#!/bin/sh\necho aarch64\n')
        uname.chmod(0o755)
        conda = fake/'conda'
        conda.write_text('''#!/bin/bash
if [[ " $* " == *" --dry-run "* ]]; then
    if [[ $FAILED_PHASE == solver ]]; then echo 'solver diagnostic'; exit 17; fi
    echo '{"actions":{"LINK":[{"name":"spyder","version":"6.1.8"}]}}'
else
    mkdir -p "$TEST_PREFIX/bin"
    if [[ $FAILED_PHASE == download ]]; then echo 'download diagnostic' >&2; exit 18; fi
    printf '#!/bin/bash\necho "verification diagnostic" >&2\nexit 19\n' > "$TEST_PREFIX/bin/python"
    chmod +x "$TEST_PREFIX/bin/python"
fi
''')
        conda.chmod(0o755)
        script = install/'create.sh'
        script.write_text((BASE/'install/create_lab314_env.sh').read_text()
                          .replace('/opt/conda/bin/conda',str(conda))
                          .replace('/opt/conda/bin/python',sys.executable))
        for phase, code, heading, diagnostic in cases:
            with self.subTest(phase=phase):
                prefix = self.root/phase
                result = subprocess.run(['bash',script,'--prefix',prefix],capture_output=True,text=True,
                                        env=dict(os.environ,PATH=f'{fake}:/usr/bin:/bin',
                                                 FAILED_PHASE=phase,TEST_PREFIX=str(prefix)))
                self.assertEqual(result.returncode,code,result.stderr)
                self.assertIn(heading,result.stderr)
                self.assertIn(diagnostic,result.stderr)
                self.assertEqual(prefix.exists(),phase!='solver')
                self.assertEqual(list(self.root.glob('.lab314-build.*')),[])

    def test_native_spyder_and_kernel_compatibility_without_system_ide(self):
        versions=rolling_versions()
        versions.update(spyder='6.1.8', **{'spyder-kernels':'3.1.7'})
        with patch.object(policy.md,'requires',return_value=['spyder-kernels>=3.1,<3.2']):
            self.assertEqual(policy.version_errors(versions,'3.14.10',native=True),[])
            versions['spyder-kernels']='3.2.0'
            self.assertTrue(policy.version_errors(versions,'3.14.10',native=True))
        self.spy_mock.assert_not_called()
        self.assertIn('opencv=5.1.0=qt6*',policy.native_conda_specs())
        self.assertIn('hdf5=1.14.6',policy.native_conda_specs())
        self.assertIn('spyder==6.1.8',policy.native_conda_specs())
        self.assertNotIn('spyder==6.1.8',policy.native_conda_specs(with_spyder=False))
        with self.assertRaisesRegex(ValueError,'non-stable'):
            policy.solved_spyder({'actions':{'LINK':[{'name':'spyder','version':'6.2.0a1'}]}})

    def test_approved_defaults_are_required_in_each_native_install(self):
        prior=json.loads((BASE/'config/lab314/packages.json').read_text())['packages']
        self.assertEqual(policy.version_errors(prior,'3.14.10',native=True),
                         [f'{name}: installed None' for name in ADDED_DEFAULTS])
        for include_spyder in (False,True):
            self.assertLessEqual(set(ADDED_DEFAULTS),set(policy.native_conda_specs(include_spyder)))
        self.assertEqual(policy.policy()['pip']['pywavelets'],'pywt')

    def test_default_reconciliation_without_missing_packages_does_no_package_work(self):
        records=self.root/'record'
        arguments=['update','--prefix',str(self.prefix),'--add-defaults','--apply','--record-dir',str(records)]
        with (patch.object(sys,'prefix',str(self.prefix)),patch.object(sys,'argv',arguments),
              patch.object(update.platform,'python_version',return_value='3.14.10'),
              patch.object(update,'missing_scientific_defaults',return_value=[]),
              patch.object(update,'ownership') as ownership,
              patch.object(update.subprocess,'run') as run,contextlib.redirect_stdout(io.StringIO())):
            update.main()
        ownership.assert_not_called()
        run.assert_not_called()
        self.assertFalse(records.exists())

    def test_default_reconciliation_freezes_existing_builds_and_requires_requested_links(self):
        records=self.root/'record'
        args=['update','--prefix',str(self.prefix),'--add-defaults','--apply','--record-dir',str(records)]
        plan={'success':True,'actions':{'LINK':[dict(name='plotly',version='6.8.0',build_string='build')]}}
        inventory=({'python':'3.14.10','opencv':'5.1.0','numpy':'2.5.5'}, {}, {})
        with (patch.object(sys,'prefix',str(self.prefix)),patch.object(sys,'argv',args),
              patch.object(update.platform,'python_version',return_value='3.14.10'),
              patch.object(update,'missing_scientific_defaults',return_value=['plotly']),
              patch.object(update,'ownership',return_value=inventory),patch.dict(os.environ,{},clear=True),
              patch.object(update,'check_conda_files'),patch.object(update.subprocess,'run') as run,
              patch.object(update.subprocess,'check_output',side_effect=['','',json.dumps(plan),json.dumps(plan)]) as solver,
              contextlib.redirect_stdout(io.StringIO())):
            update.main()
        commands=[entry.args[0] for entry in solver.call_args_list]
        self.assertIn('--freeze-installed',commands[2])
        self.assertIn('plotly',commands[2])
        self.assertIn('--offline',commands[3])
        self.assertNotIn('numpy',commands[2])
        self.assertNotIn('shap',commands[2])
        self.assertTrue(any('--offline' in entry.args[0] for entry in run.call_args_list))
        with self.assertRaisesRegex(ValueError,'replace installed'):
            update.validate_additions({'actions':{'LINK':[{'name':'numpy'}]}},inventory[0],['plotly'])
        with self.assertRaisesRegex(ValueError,'required packages: plotly'):
            update.validate_additions({'actions':{}},inventory[0],['plotly'])

    def test_native_update_keeps_python_and_graphical_opencv_in_conda(self):
        inventory=({'python':'3.14.10','opencv':'5.0.0','spyder':'6.1.8'}, {}, {})
        solved=json.dumps({'success':True,'actions':{'LINK':[]}})
        with patch.object(sys,'prefix',str(self.prefix)),patch.object(sys,'argv',['update','--prefix',str(self.prefix),'--all']), \
                patch.object(update.platform,'python_version',return_value='3.14.10'), \
                patch.object(update,'ownership',return_value=inventory),patch.dict(os.environ,{},clear=True), \
                patch.object(update.subprocess,'check_output',return_value=solved) as solver, \
                patch.object(update.subprocess,'run') as apply,contextlib.redirect_stdout(io.StringIO()):
            update.main()
        for spec in ('--dry-run','--update-all','python=3.14','python-gil','opencv=5.1.0=qt6*',
                     'hdf5=1.14.6','spyder'):
            self.assertIn(spec,solver.call_args.args[0])
        self.spy_mock.assert_not_called()
        apply.assert_not_called()

    def test_opencv_upgrade_can_replace_hdf5_dependents_and_displays_the_downgrade(self):
        inventory=({'python':'3.14.10','opencv':'5.0.0','hdf5':'2.2.0','spyder':'6.1.8'}, {}, {})
        unlink=[dict(name='hdf5',version='2.2.0',build_string='new')]
        link=[dict(name='hdf5',version='1.14.6',build_string='old')]
        plan={'success':True,'actions':{'UNLINK':unlink,'LINK':link}}
        args=['update','--prefix',str(self.prefix),'--package','opencv']
        with (patch.object(sys,'prefix',str(self.prefix)), patch.object(sys,'argv',args),
              patch.object(update.platform,'python_version',return_value='3.14.10'),
              patch.object(update,'ownership',return_value=inventory), patch.dict(os.environ,{},clear=True),
              patch.object(update.subprocess,'check_output',return_value=json.dumps(plan)) as solver,
              contextlib.redirect_stdout(io.StringIO()) as output):
            update.main()
        command=solver.call_args.args[0]
        for spec in ('opencv=5.1.0=qt6*','hdf5=1.14.6','h5py','netcdf4','spyder==6.1.8'):
            self.assertIn(spec,command)
        self.assertNotIn('--freeze-installed',command)
        self.assertIn('downgrade      hdf5: 2.2.0 new -> 1.14.6 old',output.getvalue())
        self.assertIn(update.conda_plan_token(update.conda_transaction(plan)),output.getvalue())

    def test_opencv_upgrade_refuses_a_changed_transaction_before_installing(self):
        inventory=({'python':'3.14.10','opencv':'5.0.0','spyder':'6.1.8'}, {}, {})
        plan={'success':True,'actions':{'LINK':[dict(name='opencv',version='5.1.0',build_string='qt6_build')]}}
        args=['update','--prefix',str(self.prefix),'--package','opencv','--apply','--record-dir',
              str(self.root/'record'),'--approved-conda-plan','0'*64]
        with (patch.object(sys,'prefix',str(self.prefix)), patch.object(sys,'argv',args),
              patch.object(update.platform,'python_version',return_value='3.14.10'),
              patch.object(update,'ownership',return_value=inventory), patch.dict(os.environ,{},clear=True),
              patch.object(update.subprocess,'check_output',side_effect=['', '', json.dumps(plan)]),
              patch.object(update.subprocess,'run') as apply,
              contextlib.redirect_stdout(io.StringIO())):
            with self.assertRaisesRegex(ValueError,'Review this OpenCV transaction'):
                update.main()
        apply.assert_not_called()


if __name__=='__main__':unittest.main()
