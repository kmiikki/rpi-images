"""Only temporary filesystem state and mocked privileged commands."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_rpi_setup import FakeHost, m
import diagnostics
import lifecycle
from installation_state import ABSENT, Store


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/'host'
        self.root.mkdir(mode=0o755)
        self.store=Store(Path(temp.name)/'state',self.root)
        self.host=FakeHost()
        self.host.log=None
        self.apt={}
        self.service={'ssh_enabled':'disabled','ssh_active':'inactive','ntp':'yes','timesync':'active'}
        patcher=patch.multiple(lifecycle,apt_inventory=lambda host:self.apt.copy(),
                               consumers=lambda path:[],remote_session=lambda:False,
                               services=lambda host:self.service.copy())
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.store.locked():
            self.store.start(self.host.snapshot(),{'base-files':'13'})

    def file(self,name,content):
        path=self.store.path(name)
        path.parent.mkdir(parents=True,exist_ok=True)
        for parent in path.parents:
            if parent==self.root:
                break
            parent.chmod(0o755)
        path.write_text(content)
        path.chmod(0o644)
        return path

    def environment(self,name):
        self.file(name+'/conda-meta/history','test environment')
        return self.file(name+'/work.dat','installed payload')

    def record(self,component,files=(),trees=()):
        targets=[*((p,False) for p in files),*((p,True) for p in trees)]
        return self.store.stage(component,targets)

    def reset(self):
        actions,blocked=lifecycle.removal_plan(self.store,self.host)
        with redirect_stdout(io.StringIO()):
            return lifecycle.apply_removal(self.store,self.host,actions,blocked)

    def test_reset_restores_known_files_and_preserves_keyboard_accounts_and_data(self):
        firmware=self.file('/boot/firmware/config.txt','dtparam=spi=off\n# original')
        keyboard=self.file('/etc/default/keyboard','XKBLAYOUT="de"\n')
        command=self.file('/usr/local/bin/rpi-keyboard','keyboard tool')
        prefs=self.store.directory/'keyboard.json'
        prefs.write_text('{"version":1,"layout":"de"}')
        data=self.file('/home/alice/results/data.csv','measurement')
        pw=self.file('/etc/passwd','alice account data')
        with self.record('preboot',files=lifecycle.FIRMWARE_PATHS):
            firmware.write_text('dtparam=spi=on\n# original')
            module=self.file(lifecycle.FIRMWARE_PATHS[1],'i2c-dev\n')
        with self.record('lab314',trees=['/opt/lab314']):
            science=self.environment('/opt/lab314')
        self.assertEqual(self.reset(),0)
        self.assertEqual(firmware.read_text(),'dtparam=spi=off\n# original')
        self.assertFalse(module.exists())
        self.assertFalse(science.exists())
        self.assertEqual(keyboard.read_text(),'XKBLAYOUT="de"\n')
        self.assertEqual(command.read_text(),'keyboard tool')
        self.assertEqual(json.loads(prefs.read_text())['layout'],'de')
        self.assertEqual(pw.read_text(),'alice account data')
        self.assertEqual(data.read_text(),'measurement')
        self.assertEqual(self.reset(),0)
        with self.record('lab314',trees=['/opt/lab314']):
            self.environment('/opt/lab314')
        self.assertEqual(self.reset(),0)

    def test_drift_blocks_only_the_affected_restoration_and_keeps_untracked_data(self):
        cfg=self.file(lifecycle.NTP_FILE,'original')
        with self.record('profile',files=[lifecycle.NTP_FILE]):
            cfg.write_text('installed')
        with self.record('shell',files=['/usr/local/bin/envrun']):
            executable=self.file('/usr/local/bin/envrun','managed')
        with self.record('lab314',trees=['/opt/lab314']):
            self.environment('/opt/lab314')
        cfg.write_text('external edits')
        untracked=self.file('/opt/lab314/observations.txt','measurement')
        self.assertEqual(self.reset(),1)
        self.assertEqual(cfg.read_text(),'external edits')
        self.assertEqual(untracked.read_text(),'measurement')
        self.assertFalse(executable.exists())

    def test_preexisting_environment_and_unknown_manifest_not_adopted(self):
        original=self.environment('/opt/lab314')
        with self.record('lab314',trees=['/opt/lab314']):
            pass
        actions,blocked=lifecycle.removal_plan(self.store,self.host,'lab314')
        self.assertFalse(actions)
        self.assertIn(lifecycle.UNKNOWN,blocked[0])
        self.store.data=None
        self.assertEqual(lifecycle.removal_plan(self.store,self.host),([], [lifecycle.UNKNOWN]))
        self.assertTrue(original.exists())

    def test_conda_removal_is_blocked_by_environment_or_active_consumer(self):
        with self.record('conda',trees=['/opt/conda']):
            conda=self.environment('/opt/conda')
        self.environment('/opt/custom')
        self.assertIn('dependent environments',lifecycle.removal_plan(self.store,self.host,'conda')[1][0])
        with patch.object(lifecycle,'conda_dependents',return_value=[]),patch.object(lifecycle,'consumers',return_value=['42']):
            actions,blocked=lifecycle.removal_plan(self.store,self.host,'conda')
        self.assertFalse(actions)
        self.assertIn('PID(s): 42',blocked[0])
        self.assertTrue(conda.exists())

    def test_selective_conda_removal_keeps_an_untracked_link(self):
        with self.record('conda',trees=['/opt/conda'],files=['/usr/local/bin/conda']):
            self.environment('/opt/conda')
            command=self.file('/usr/local/bin/conda','managed')
        foreign=self.file('/usr/local/bin/unrelated','foreign')
        actions,blocked=lifecycle.removal_plan(self.store,self.host,'conda')
        self.assertIn(('tree','/opt/conda'),actions)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(lifecycle.apply_removal(self.store,self.host,actions,blocked),0)
        self.assertFalse(command.exists())
        self.assertTrue(foreign.exists())

    def test_remote_session_keeps_ssh_and_hostname(self):
        real=self.file('/etc/hostname','original\n')
        with self.record('accounts',files=['/etc/hostname']):
            real.write_text('installed\n')
        with self.store.stage('profile',service_probe=lambda:self.service.copy()):
            self.service.update(ssh_enabled='enabled',ssh_active='active')
        with patch.object(lifecycle,'remote_session',return_value=True):
            actions,blocked=lifecycle.removal_plan(self.store,self.host)
        self.assertFalse(actions)
        self.assertTrue(any('SSH restoration' in msg for msg in blocked))
        self.assertEqual(real.read_text(),'installed\n')
        self.assertEqual(self.host.calls,[])

    def test_failed_or_interrupted_stage_does_not_adopt_partial_files(self):
        with self.assertRaises(KeyboardInterrupt):
            with self.record('lab314',trees=['/opt/lab314']):
                partial=self.file('/opt/lab314/partial','unknown')
                raise KeyboardInterrupt
        stored=self.store.load()
        self.assertEqual(stored['components']['lab314']['status'],'failed')
        self.assertIn('conflict',stored['paths']['/opt/lab314'])
        self.assertFalse(lifecycle.removal_plan(self.store,self.host,'lab314')[0])
        self.assertTrue(partial.exists())

    def test_symlink_path_is_rejected_without_following_target(self):
        destination=self.root/'opt'
        destination.symlink_to('/opt')
        with self.assertRaisesRegex(ValueError,'Symlinked parent'):
            self.store.snapshot('/opt/lab314',True)

    def test_readonly_plan_does_not_write_manifest_or_remove_existing_files(self):
        with self.record('shell',files=['/usr/local/bin/envrun']):
            command=self.file('/usr/local/bin/envrun','managed')
        original=self.store.file.read_bytes()
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lifecycle.main(['--manage','--action','reset','--dry-run'],self.host,self.store),0)
        self.assertIn('Remove installer-created file',out.getvalue())
        self.assertEqual(original,self.store.file.read_bytes())
        self.assertTrue(command.exists())

    def test_status_and_verification_distinguish_blocked_and_installed_components(self):
        self.store.data['selected']={'hardware':True,'lab314':True}
        self.store.data['components']['hardware']={'status':'blocked'}
        self.host.existing.add('/opt/conda')
        with redirect_stdout(io.StringIO()) as output:
            lifecycle.status(self.store,self.host)
            self.assertEqual(lifecycle.verify(self.store,self.host),1)
        report=output.getvalue()
        self.assertIn('Blocked by an earlier installation failure',report)
        self.assertIn('BLOCKED Raspberry Pi hardware Python',report)
        self.assertIn('NOT INSTALLED Scientific Python',report)
        self.assertIn('PASS Miniforge',report)
        self.assertNotIn('verify_rpi_env.sh',' '.join(str(call) for call in self.host.calls))

    def test_default_deny_keeps_reset_changes_unapplied_even_with_yes(self):
        with self.record('shell',files=['/usr/local/bin/envrun']):
            command=self.file('/usr/local/bin/envrun','managed')
        with patch.object(lifecycle,'require_root'),patch.object(sys.stdin,'isatty',return_value=False),redirect_stdout(io.StringIO()):
            self.assertEqual(lifecycle.main(['--manage','--action','reset','--yes'],self.host,self.store),0)
        self.assertTrue(command.exists())

    def test_apt_removal_refuses_to_remove_dependents(self):
        self.apt={'wolfram-engine':'1.2','shared':'1.0'}
        self.store.data['wolfram_owned']='1.2'
        with patch.object(self.host,'run',return_value=subprocess.CompletedProcess([],0,'Remv wolfram-engine [1.2]\nRemv shared [1.0]\n','')):
            actions,blocked=lifecycle.removal_plan(self.store,self.host,'wolfram')
        self.assertFalse(actions)
        self.assertIn('not limited',blocked[0])

    def test_quarantine_keeps_partial_environment_and_its_diagnostics(self):
        path=self.file('/opt/lab314/error.log','download stopped')
        with patch.object(self.host,'environment',side_effect=ValueError('missing metadata')),redirect_stdout(io.StringIO()):
            planned=lifecycle.quarantine_plan(self.store,self.host)
            self.assertEqual(lifecycle.quarantine(self.store,self.host,planned),0)
        self.assertFalse(path.exists())
        saved=Path(self.store.data['operation']['backup'])
        self.assertEqual((saved/'error.log').read_text(),'download stopped')
        self.assertEqual(self.store.data['operation']['status'],'complete')

    def test_update_plan_delegates_to_existing_python_package_updater(self):
        self.environment('/opt/lab314')
        self.host.existing.add('/opt/lab314')
        lifecycle.software_action(self.store,self.host,'update','lab314',['numpy'],True)
        call=self.host.calls[0]
        self.assertTrue(any(arg.endswith('update_lab314.py') for arg in call))
        self.assertEqual(call[-2:],['--package','numpy'])
        self.assertNotIn('--apply',call)

    def test_opencv_update_passes_the_reviewed_transaction_to_the_updater(self):
        self.host.existing.add('/opt/lab314')
        with self.record('lab314',trees=['/opt/lab314']):
            self.environment('/opt/lab314')
        observed='fedcba98'*8
        preview=subprocess.CompletedProcess([],0,f'CONDA PLAN TOKEN {observed}\n','')
        with (patch.object(self.host,'native_lab314',return_value=True),
              patch.object(self.host,'run',return_value=preview) as run,
              redirect_stdout(io.StringIO())):
            approved=lifecycle.software_action(self.store,self.host,'update','lab314',['opencv'],True)
            lifecycle.software_action(self.store,self.host,'update','lab314',['opencv'],False,approved)
        self.assertEqual(approved,observed)
        self.assertTrue(run.call_args_list[0].kwargs['capture'])
        self.assertNotIn('--apply',run.call_args_list[0].args[0])
        command=run.call_args_list[1].args[0]
        self.assertEqual(command[command.index('--approved-conda-plan')+1],observed)
        self.assertNotIn('/opt/rpi',command)

    def test_existing_spyder_repair_checks_kernel_before_requesting_package_changes(self):
        self.host.existing.update(('/opt/lab314','/opt/lab314/bin/spyder'))
        with redirect_stdout(io.StringIO()) as output:
            lifecycle.software_action(self.store,self.host,'repair','spyder',[],True)
        self.assertEqual(len(self.host.calls),1)
        self.assertIn('--kernel-only',self.host.calls[0])
        self.assertIn('Spyder IPython console: PENDING',output.getvalue())
        self.host.calls.clear()
        with redirect_stdout(io.StringIO()):
            lifecycle.software_action(self.store,self.host,'repair','spyder',[],False)
        self.assertIn('--kernel-only',self.host.calls[0])
        self.assertEqual(len(self.host.calls),1)
        for source,destination,mode in lifecycle.SPYDER_LAUNCHER:
            installed=self.store.path(destination)
            self.assertEqual(installed.read_bytes(),source.read_bytes())
            self.assertEqual(stat.S_IMODE(installed.stat().st_mode),int(mode,8))

    def test_resume_checks_failed_existing_lab314_before_dependent_stages(self):
        self.store.data['components']['lab314']={'status':'failed'}
        self.host.records=self.store
        self.host.existing.update(('/opt/conda','/opt/lab314','/opt/lab314/bin/spyder'))
        self.file('/opt/conda/bin/conda','fixture')
        self.file('/opt/conda/bin/mamba','fixture')
        self.file('/etc/bash.bashrc','# fixture\n')
        self.file('/opt/lab314/conda-meta/history','fixture')
        args=m.parser().parse_args(['--profile','HOME','--yes','--share-later','--no-hardware'])
        state=self.host.snapshot()
        plan=m.resolve(args,state,self.host)
        with patch.object(m,'os',wraps=os) as mocked_os,patch.object(m.accounts,'ensure_user'), \
                patch.object(lifecycle,'install_missing_apt'), \
                redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            mocked_os.geteuid.return_value=0
            m.apply(args,plan,state,self.host)
        calls=[' '.join(call) for call in self.host.calls]
        check=next(index for index,command in enumerate(calls) if 'check_lab314.py' in command)
        self.assertTrue(self.store.path('/usr/local/share/applications/rpi-lab314-spyder.desktop').is_file())
        self.assertIn('--functional',calls[check])
        self.assertFalse(any('create_lab314_env.sh' in call for call in calls))

    def test_normal_reruns_reuse_profile_and_reconcile_only_managed_changes(self):
        self.host.records=self.store
        self.host.existing.update(('/opt/conda','/opt/lab314','/opt/lab314/bin/spyder','/usr/local/bin/rpi-share'))
        self.file('/opt/conda/bin/conda','fixture')
        self.file('/opt/conda/bin/mamba','fixture')
        self.file('/opt/lab314/conda-meta/history','fixture')
        bashrc=self.file('/etc/bash.bashrc','# original shell configuration\n')
        self.host.run_preboot=lambda **kwargs: (m.preboot.BootStatus.READY,'us')
        original_run=self.host.run

        def run(argv,**kwargs):
            response=original_run(argv,**kwargs)
            if argv[:2]==['id','-nG']:
                response.stdout='alice sudo'
            return response

        with patch.object(m,'os',wraps=os) as mocked_os, patch.object(m.accounts,'ensure_user'), \
                patch.object(self.host,'run',side_effect=run),patch.object(sys.stdin,'isatty',return_value=False), \
                patch.object(lifecycle,'install_missing_apt'),patch.object(m.os_upgrade,'description',return_value='Completed'), \
                redirect_stdout(io.StringIO()) as output:
            mocked_os.geteuid.return_value=0
            self.store.data['os_upgrade']={'status':'completed'}
            self.assertEqual(m.main(['--profile','HOME','--yes','--no-hardware','--no-wolfram',
                                     '--ntp-server','time.example.org','--ssh','keep'],self.host),0)
            self.assertEqual(self.store.data['profile'],'HOME')
            self.assertFalse(self.store.data['selected']['wolfram'])
            source,destination,mode=lifecycle.SPYDER_LAUNCHER[2]
            desktop=self.store.path(destination)
            original_bytes=desktop.read_bytes()
            original_stat=desktop.stat()
            ntp=self.store.path(lifecycle.NTP_FILE)
            ntp_stat=ntp.stat()
            catalog=self.file('/home/alice/.config/rpi-share/shares.json','local catalog')
            helper=self.store.path('/etc/profile.d/lab314-bash.sh')
            helper.write_bytes(helper.read_bytes()+b'# local helper setting\n')
            bashrc.write_bytes(bashrc.read_bytes()+b'# local shell setting\n')
            self.host.calls.clear()
            self.store.reconciled.clear()
            self.assertEqual(m.main([],self.host),0)
            self.assertEqual((desktop.stat().st_mtime_ns,ntp.stat().st_mtime_ns),
                             (original_stat.st_mtime_ns,ntp_stat.st_mtime_ns))
            self.assertIn(b'NTP=time.example.org',ntp.read_bytes())
            self.assertIn(b'# local helper setting',helper.read_bytes())
            self.assertEqual(catalog.read_text(),'local catalog')
            self.assertNotIn('apt-get',' '.join(str(cmd) for cmd in self.host.calls))
            additions=[command for command in self.host.calls if '--add-defaults' in command]
            self.assertEqual(len(additions),1)
            self.assertIn('--apply',additions[0])
            self.assertNotIn('--all',additions[0])
            self.assertIn(['sudo','-n','-u','alice','sudo','-kn','true'],self.host.calls)
            self.assertFalse(self.store.path('/etc/sudoers.d/010_alice-nopasswd').exists())
            self.assertFalse(any('create_' in str(cmd) or 'install_optional_wolfram' in str(cmd) for cmd in self.host.calls))

            changed=self.file('/updated-desktop',source.read_text()+'# revised launcher\n')
            definitions=list(lifecycle.SPYDER_LAUNCHER)
            definitions[2]=(changed,destination,mode)
            with patch.object(lifecycle,'SPYDER_LAUNCHER',definitions):
                self.assertEqual(m.main([],self.host),0)
                updated_stat=desktop.stat()
                self.assertEqual(m.main([],self.host),0)
                self.assertEqual(desktop.stat().st_ino,updated_stat.st_ino)
            self.assertEqual(desktop.read_bytes(),changed.read_bytes())
            self.assertIn(original_bytes,[backup.read_bytes() for backup in (self.store.directory/'original').iterdir()])
            self.assertIn(b'# local shell setting',bashrc.read_bytes())
            self.assertEqual(bashrc.read_bytes().count(b'# >>> LAB314 BEGIN >>>'),1)
            self.assertIn(f'CONFIGURATION updated: {destination}',output.getvalue())

    def test_missing_apt_component_refuses_updates_and_skips_installed(self):
        self.apt={'already':'1'}
        lifecycle.install_missing_apt(self.host,['already'])
        self.assertEqual(self.host.calls,[])
        command=self.host.run
        def resolve(argv,**kwargs):
            result=command(argv,**kwargs)
            if '--simulate' in argv:
                result.stdout='Inst already [1] (2 trixie)\nInst missing (1 trixie)\n'
            return result
        with patch.object(self.host,'run',side_effect=resolve),self.assertRaisesRegex(ValueError,'would change'):
            lifecycle.install_missing_apt(self.host,['missing','already'])
        self.assertEqual([cmd[1] for cmd in self.host.calls],['update','--simulate'])

    def test_scientific_browser_uses_one_definition_for_all_profiles(self):
        self.host.existing.add('/opt/lab314')
        self.file('/opt/lab314/conda-meta/history','fixture')
        state=self.host.snapshot()
        scheduled=m.stages
        with (
            patch.object(m,'os',wraps=os) as mocked_os,
            patch.object(m,'stages',return_value=[('lab314','Scientific Python')]),
            redirect_stdout(io.StringIO()),
        ):
            mocked_os.geteuid.return_value=0
            for profile in ('GENERAL','HOME','AALTO'):
                with self.subTest(profile=profile), tempfile.TemporaryDirectory() as temp:
                    self.host.records=Store(Path(temp)/'state',self.root)
                    with self.host.records.locked():
                        self.host.records.start(state,{})
                    args=m.parser().parse_args(['--profile',profile,'--yes'])
                    plan=m.resolve(args,state,self.host)
                    self.assertIn('lab314',[name for name,_ in scheduled(args,plan)])
                    self.assertTrue(plan['components']['lab314'])
                    self.assertEqual(m.apply(args,plan,state,self.host),0)
                    launcher=self.host.records.path(lifecycle.SCIENTIFIC_BROWSER)
                    hook=self.host.records.path(lifecycle.scientific_browser_hook(args.lab_prefix))
                    self.assertEqual(stat.S_IMODE(launcher.stat().st_mode),0o755)
                    self.assertEqual(stat.S_IMODE(hook.stat().st_mode),0o644)
                    self.assertEqual(launcher.read_bytes(),(lifecycle.BASE/'bin/rpi-scientific-browser').read_bytes())
                    self.assertEqual(hook.read_bytes(),(lifecycle.BASE/'config/lab314/rpi-scientific-browser.pth').read_bytes())
                    timestamps=(launcher.stat().st_mtime_ns,hook.stat().st_mtime_ns)
                    self.assertEqual(m.apply(args,plan,state,self.host),0)
                    self.assertEqual((launcher.stat().st_mtime_ns,hook.stat().st_mtime_ns),timestamps)
                    launcher.unlink()
                    hook.unlink()

    def test_terminal_lifecycle_tracks_only_the_sudo_invoker_and_rechecks_before_reset(self):
        target=lifecycle.terminal_target(self.host.snapshot())
        self.assertEqual(target['name'],'alice')
        changed=subprocess.CompletedProcess([],0,'changed\n','')
        with patch.object(self.host,'run',return_value=changed) as run,redirect_stdout(io.StringIO()):
            lifecycle.apply_terminal_shortcuts(self.store,self.host,target,'se')
            self.assertEqual(run.call_args_list[0].args[0][:3],['runuser','-u','alice'])
            self.assertIn('--plan',run.call_args_list[0].args[0])
            self.assertEqual(self.store.data['terminal_shortcuts']['alice']['layout'],'se')
            actions,blocked=lifecycle.removal_plan(self.store,self.host,'terminal-shortcuts')
            self.assertEqual(blocked,[])
            self.assertEqual(actions,[('terminal-shortcuts','/home/alice/.config/lxterminal/lxterminal.conf')])
            self.assertEqual(lifecycle.apply_removal(self.store,self.host,actions,blocked),0)
            self.assertIn('--restore',run.call_args.args[0])
            self.assertEqual(self.store.data['terminal_shortcuts'],{})

    def test_missing_owned_envrun_is_repaired_and_recorded_again(self):
        with self.record('shell',files=['/usr/local/bin/envrun']):
            tool=self.file('/usr/local/bin/envrun','old')
        tool.unlink()
        def install(*args,**kwargs):
            self.file('/usr/local/bin/envrun','repaired')
        with patch.object(self.host,'run',side_effect=install),redirect_stdout(io.StringIO()):
            lifecycle.software_action(self.store,self.host,'repair','envrun',[],False)
        self.assertEqual(tool.read_text(),'repaired')
        self.assertNotIn('conflict',self.store.data['paths']['/usr/local/bin/envrun'])

    def test_failed_repair_keeps_prior_files_and_records_error(self):
        with self.record('lab314',trees=['/opt/lab314']):
            payload=self.environment('/opt/lab314')
        self.host.existing.add('/opt/lab314')
        self.host.fail='update_lab314.py'
        with redirect_stdout(io.StringIO()),self.assertRaises(subprocess.CalledProcessError):
            lifecycle.software_action(self.store,self.host,'repair','lab314',['numpy'],False)
        self.assertEqual(payload.read_text(),'installed payload')
        self.assertEqual(self.store.load()['components']['lab314']['status'],'failed')


class InstallerFailureTests(unittest.TestCase):
    def test_failure_summary_omits_dependent_verification_and_preserves_success(self):
        host=FakeHost(fail='create_lab314_env.sh')
        args=m.parser().parse_args(['--profile','HOME','--yes'])
        state=host.snapshot()
        plan=m.resolve(args,state,host)
        output=io.StringIO()
        with patch.object(os,'geteuid',return_value=0),patch.object(m.accounts,'ensure_user'), \
                redirect_stdout(output),redirect_stderr(io.StringIO()):
            self.assertEqual(m.apply(args,plan,state,host),1)
        text=output.getvalue()
        for expected in ('PASS profile','PASS conda','FAIL lab314','BLOCKED hardware','VERIFY BLOCKED share'):
            self.assertIn(expected,text)
        self.assertFalse(any('verify_rpi_env.sh' in ' '.join(call) or 'rpi-share' in ' '.join(call) for call in host.calls))

    def test_rerun_after_correction_keeps_miniforge_and_finishes_blocked_stages(self):
        host=FakeHost(fail='create_lab314_env.sh')
        args=m.parser().parse_args(['--profile','HOME','--yes','--share-later'])
        with patch.object(os,'geteuid',return_value=0),patch.object(m.accounts,'ensure_user'), \
                redirect_stdout(io.StringIO()) as output,redirect_stderr(io.StringIO()):
            state=host.snapshot()
            self.assertEqual(m.apply(args,m.resolve(args,state,host),state,host),1)
            host.existing.add('/opt/conda')
            host.calls.clear()
            host.fail=None
            self.assertEqual(m.apply(args,m.resolve(args,state,host),state,host),0)
        commands='\n'.join(' '.join(call) for call in host.calls)
        self.assertNotIn('install_conda_base.sh',commands)
        self.assertIn('create_lab314_env.sh',commands)
        self.assertIn('create_rpi_env.sh',commands)
        self.assertIn('verify_rpi_env.sh',commands)
        self.assertIn('PASS hardware',output.getvalue())

    def test_structural_probe_requires_valid_conda_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix=Path(tmp)/'lab314'
            python=prefix/'bin/python'
            python.parent.mkdir(parents=True,mode=0o755)
            prefix.chmod(0o755)
            python.write_text('#!/bin/sh\nexit 0\n')
            python.chmod(0o755)
            metadata=prefix/'conda-meta'
            metadata.mkdir()
            host=m.Host()
            with self.assertRaisesRegex(ValueError,'incomplete'):
                host.environment(prefix)
            (metadata/'history').touch()
            record=metadata/'python-3.14-test.json'
            record.write_text('{invalid')
            with self.assertRaisesRegex(ValueError,'incomplete'):
                host.environment(prefix)
            record.write_text('{"name":"python","version":"3.14"}')
            self.assertTrue(host.environment(prefix))

    def test_persistent_log_preserves_command_output_and_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=diagnostics.Log(Path(tmp))
            log.stage='lab314'
            try:
                with redirect_stdout(io.StringIO()),self.assertRaises(diagnostics.CommandFailure) as exc:
                    log.run([sys.executable,'-c',
                             'import sys; print("download failed token=hidden"); print("solver error",file=sys.stderr); sys.exit(18)'],
                            os.environ.copy())
            finally:
                log.close()
            data=log.path.read_text()
            self.assertEqual(stat.S_IMODE(log.path.stat().st_mode),0o600)
            self.assertIn('[lab314]',data)
            self.assertIn('solver error',str(exc.exception))
            self.assertIn('download failed token=[redacted]',data)
            self.assertNotIn('hidden',data)
            self.assertIn(str(log.path),str(exc.exception))
