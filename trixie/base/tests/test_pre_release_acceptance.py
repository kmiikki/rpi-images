"""Regression checks for the final installer corrections on temporary hosts."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_rpi_setup import FakeHost, accounts, m as setup
import lifecycle
from installation_state import Store
import update_all
import wlan
import wolfram


class ResumeTests(unittest.TestCase):
    def test_approved_name_country_and_components_resume_across_reboot(self):
        for profile, mode in (('GENERAL','shared'),('HOME','shared'),('AALTO','personal')):
            with self.subTest(profile=profile):
                self.check_resume(profile, mode)

    def check_resume(self, profile, mode):
        with tempfile.TemporaryDirectory() as tmp:
            host = FakeHost('alice')
            store = Store(Path(tmp)/'journal')
            with store.locked():
                store.start(host.snapshot(), {})
                store.data['os_upgrade']['status'] = 'completed'
                store.save()
            host.records = store
            state = {'stored': 'FI', 'country': 'FI', 'blocks': [('0','0')], 'radio': 'enabled'}
            host.wlan_state = lambda: state.copy()
            boot = 'initial'
            host.run_preboot = lambda **kwargs: (setup.preboot.BootStatus.REBOOT_REQUIRED if boot == 'initial'
                                                 else setup.preboot.BootStatus.READY, 'fi')

            def run(argv, **kwargs):
                if argv[:3] == ['/usr/bin/raspi-config', 'nonint', 'do_wifi_country']:
                    state.update(stored=argv[3], country=argv[3])
                return FakeHost.run(host, argv, **kwargs)

            answers = {
                'Profile GENERAL / HOME / AALTO': profile,
                'Hostname': 'test-station',
                'WLAN regulatory country (two-letter ISO code)': 'SE',
                'Apply this installation plan? y/N/customize': 'y',
                'Reboot now? y/N': 'n',
            }
            with (redirect_stdout(io.StringIO()) as output,
                  patch.object(sys.stdin, 'isatty', return_value=True),
                  patch.object(host, 'run', side_effect=run),
                  patch.object(setup, 'ask', side_effect=lambda prompt, default: answers[prompt]) as prompts,
                  patch.object(wlan, 'read_state', side_effect=lambda host: state.copy()),
                  patch.object(wlan, 'boot_id', side_effect=lambda: boot),
                  patch.object(setup, 'apply', return_value=0) as apply):
                self.assertEqual(setup.main(['--no-wolfram','--no-spyder','--share-later','--chromium-policy',mode], host), 0)
                apply.assert_not_called()
                store.load()
                self.assertEqual(store.data['pending_hostname']['name'], 'test-station')
                self.assertEqual(store.data['wlan_country'], 'SE')
                self.assertEqual(store.data['chromium_policy'], mode)
                boot = 'after-reboot'
                prompts.reset_mock()
                self.assertEqual(setup.main([], host), 0)
                prompts.assert_not_called()
                plan = apply.call_args.args[1]
                self.assertEqual((plan['hostname'], plan['desktop_account'], plan['wlan_country'],plan['chromium_policy']),
                                 ('test-station', 'chem' if profile=='AALTO' else 'alice', 'SE', mode))
                self.assertFalse(plan['components']['wolfram'])
                self.assertFalse(plan['components']['spyder'])
                self.assertTrue(apply.call_args.args[0].share_later)
                self.assertIn('verified after reboot', plan['wlan_readback'])
                self.assertIn('Reconciling saved installation choices', output.getvalue())
                self.assertEqual(sum(argv[0] == '/usr/bin/raspi-config' for argv in host.calls), 1)

    def test_all_profiles_plan_browser_defaults_and_wolfram_overrides(self):
        for profile, default in (('GENERAL','personal'),('HOME','personal'),('AALTO','shared')):
            host=FakeHost()
            options=['--profile',profile,'--share-later']
            with self.subTest(profile=profile):
                args=setup.parser().parse_args([*options,'--plan'])
                plan=setup.resolve(args,host.snapshot(),host)
                self.assertEqual(plan['chromium_policy'],default)
                self.assertEqual(plan['components']['wolfram'],profile=='AALTO')
                for audit, mode, option in (('--plan','shared','--wolfram'),('--dry-run','personal','--no-wolfram')):
                    with redirect_stdout(io.StringIO()) as output, patch.object(setup,'apply') as apply:
                        self.assertEqual(setup.main([*options,audit,'--chromium-policy',mode,option],host),0)
                    apply.assert_not_called()
                    self.assertIn('Chromium policy          '+mode,output.getvalue())
                    self.assertEqual('Wolfram terms' in output.getvalue(),option=='--wolfram')
                self.assertFalse(host.calls)

    def test_customize_retries_invalid_browser_policy_and_accepts_shared(self):
        for profile in ('GENERAL','HOME','AALTO'):
            host=FakeHost()
            answers=iter(('invalid','shared'))
            args=setup.parser().parse_args(['--profile',profile])
            def answer(prompt,default):
                if prompt.startswith('Chromium policy'):
                    self.assertEqual(default,'shared' if profile=='AALTO' else 'personal')
                    return next(answers)
                return default
            with self.subTest(profile=profile), redirect_stdout(io.StringIO()) as output, patch.object(setup,'ask',side_effect=answer):
                setup.customize(args,host.snapshot())
                self.assertEqual(args.chromium_policy,'shared')
                self.assertIn('Choose personal or shared',output.getvalue())

    def test_hostname_retry_and_hosts_mapping(self):
        with patch.object(setup, 'ask', side_effect=['-bad','STATION-5']) as prompt, redirect_stdout(io.StringIO()):
            self.assertEqual(setup.ask_hostname('rpi-test','rpi-test'), 'station-5')
        self.assertEqual([call.args for call in prompt.call_args_list], [('Hostname','rpi-test')]*2)
        original = '127.0.0.1 localhost\n127.0.1.1 Pi.example alias # Pi preserved in comment\n'
        result = setup.hosts_alias(original,'pi','new-pi')
        self.assertEqual(result, original.replace('Pi.example','new-pi.example')+'127.0.1.1\tnew-pi\n')
        self.assertEqual(setup.hosts_alias(result,'pi','new-pi'), result)

    def test_hostname_decline_and_dry_run_never_change_host(self):
        host=FakeHost()
        with (redirect_stdout(io.StringIO()) as output, patch.object(sys.stdin, 'isatty', return_value=True),
              patch.object(setup, 'ask', side_effect=['pi-5','n']), patch.object(setup, 'apply') as apply):
            self.assertEqual(setup.main(['--profile','GENERAL'],host),0)
            self.assertEqual(setup.main(['--profile','GENERAL','--dry-run','--hostname','pi-6'],host),0)
        apply.assert_not_called()
        self.assertFalse(host.calls)
        self.assertIn('pi-5',output.getvalue())
        self.assertIn('pi-6',output.getvalue())

    def test_password_notice_precedes_passwd_and_names_the_role(self):
        for admin, primary, role in ((False,False,'local user'),(True,False,'additional administrator'),
                                     (True,True,'primary administrator')):
            with self.subTest(role=role):
                output = io.StringIO()
                output.isatty = lambda: True
                def execute(argv, **kwargs):
                    if argv[0] == 'passwd':
                        self.assertEqual(argv,['passwd','new-user'])
                        self.assertIn(f'Creating {role} account: new-user',output.getvalue())
                        self.assertTrue(output.getvalue().endswith("Set password for account 'new-user'.\n"))
                local = {'new-user': {'uid': 1000}}
                with (redirect_stdout(output), patch.object(sys.stdin,'isatty',return_value=True),
                      patch.object(accounts,'pwd',Mock(getpwnam=Mock(side_effect=KeyError))),
                      patch.object(accounts,'local_accounts',side_effect=[{},local]),
                      patch.object(accounts,'run',side_effect=execute)):
                    accounts.ensure_user('new-user',admin=admin,passwordless=primary)

    def test_ssh_probes_report_disabled_service_and_active_socket(self):
        units = {('is-active','ssh.service'):'inactive', ('is-enabled','ssh.service'):'disabled',
                 ('is-active','ssh.socket'):'active', ('is-enabled','ssh.socket'):'enabled'}
        host=FakeHost()
        host.probe = lambda argv: SimpleNamespace(stdout=units[tuple(argv[1:])],returncode=3)
        with redirect_stdout(io.StringIO()) as out:
            lifecycle.report_ssh('keep',lifecycle.ssh_status(host))
        self.assertEqual([line.split()[-1] for line in out.getvalue().splitlines()],
                         ['keep','inactive','disabled','active','enabled'])
        self.assertFalse(host.calls)

    def test_yes_alone_does_not_approve_wolfram_license(self):
        host=FakeHost('chem')
        package=wolfram.Candidate('15.0.1',2170000000,5440000000)
        args=['--profile','AALTO','--yes','--share-later']
        with (redirect_stdout(io.StringIO()), patch.object(wolfram,'candidate',return_value=package),
              patch.object(wolfram,'disk_requirements',return_value=[]),
              patch.object(setup,'apply',return_value=0) as apply):
            self.assertEqual(setup.main(args,host),0)
            self.assertEqual(apply.call_args.args[1]['wolfram_candidate'],package)
            self.assertIsNone(apply.call_args.args[1].get('wolfram_reviewed'))
            self.assertEqual(setup.main([*args,'--accept-wolfram-license'],host),0)
            self.assertEqual(apply.call_args.args[1]['wolfram_reviewed'],package)


class DesktopAndAptTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        root = Path(self.work.name)/'root'
        root.mkdir(mode=0o755)
        self.store = Store(Path(self.work.name)/'state',root)
        self.host = FakeHost()
        with self.store.locked():
            self.store.start(self.host.snapshot(),{})

    def file(self,name,content,mode=0o644):
        path=self.store.path(name)
        path.parent.mkdir(parents=True,exist_ok=True)
        for parent in path.parents:
            if parent==self.store.root:
                break
            parent.chmod(0o755)
        path.write_text(content)
        path.chmod(mode)
        return path

    def test_wolfram_apt_metadata_disk_check_and_changed_candidate(self):
        fixture = {
            'policy': '  Candidate: 15.0.1+202608182322\n',
            'show': ('Package: wolfram-engine\nVersion: 15.0.1+202608182322\n'
                     'Installed-Size: 5312500\nSize: 2170000000\n'),
            'shell': "ARCHIVES='/var/cache/apt/archives/'\n",
        }
        def probe(argv):
            if 'apt-cache' in argv:
                self.assertEqual(argv[:2], ['env','LC_ALL=C'])
                self.assertIn('Dir::Cache::pkgcache=', argv)
                self.assertIn('Dir::Cache::srcpkgcache=', argv)
            return SimpleNamespace(returncode=0,stdout=next(fixture[arg] for arg in argv if arg in fixture))
        self.host.probe = probe
        candidate = wolfram.candidate(self.host)
        self.assertEqual((candidate.download,candidate.installed),(2170000000,5440000000))
        with redirect_stdout(io.StringIO()) as out, patch.object(wolfram,'disk_requirements',return_value=[(1,7610000000,'/')]):
            with self.assertRaisesRegex(ValueError,'Insufficient disk'):
                wolfram.show_preflight(self.host,candidate,strict=True)
        self.assertIn('2.17 GB download, 5.44 GB installed',out.getvalue())
        self.assertLess(out.getvalue().index('license'),out.getvalue().index('Insufficient'))
        with (redirect_stdout(io.StringIO()), patch.object(wolfram,'disk_requirements',return_value=[]),
              patch.object(lifecycle,'install_missing_apt') as apt):
            result=lifecycle.install_wolfram(self.host,self.store,installed=False,reviewed=None,confirm=lambda:False)
        self.assertTrue(result.startswith('DEFERRED'))
        self.assertEqual(self.host.calls,[['apt-get','update']])
        apt.assert_not_called()

    def test_wolfram_tr3_fractional_installed_size_uses_exact_apt_version(self):
        version='15.0.1+202608182322'
        probes = [
            subprocess.CompletedProcess([],0,f'  Candidate: {version}\t\n',''),
            subprocess.CompletedProcess([],0,f'Package: wolfram-engine\nVersion: {version}\n'
                                        'Installed-Size: 5316364.474609375\nSize: 2173675226\n',''),
        ]
        with patch.object(self.host,'probe',side_effect=probes) as probe:
            package=wolfram.candidate(self.host)
        self.assertEqual(package,wolfram.Candidate(version,2173675226,5443957222))
        self.assertEqual(probe.call_args.args[0][-2:],['show','wolfram-engine='+version])

        cases=(('123','1.00001',1025),('123','1,5',None),('123','0.0',None),
               ('123','-1',None),('12.3','4',None),('','4',None))
        for download, installed, expected in cases:
            with self.subTest(download=download,installed=installed), patch.object(
                    self.host,'probe',return_value=subprocess.CompletedProcess([],0,
                    f'Version: {version}\nInstalled-Size: {installed}\nSize: {download}\n','')):
                metadata=wolfram.package_metadata(self.host,version)
                self.assertEqual(metadata.installed if metadata else None,expected)

        with (redirect_stdout(io.StringIO()) as output,
              patch.object(wolfram,'candidate',return_value=package),
              patch.object(wolfram,'disk_requirements',return_value=[(20_000_000_000,7_617_632_448,'/')]),
              patch.object(lifecycle,'install_missing_apt') as apt,
              patch.object(lifecycle,'reconcile_wolfram_launchers'),
              patch.object(wolfram,'verify')):
            lifecycle.install_wolfram(self.host,self.store,installed=False,reviewed=package,
                                      confirm=lambda:self.fail('the same candidate was reviewed'))
        self.assertIn('2.17 GB download, 5.44 GB installed',output.getvalue())
        self.assertIn('Wolfram terms',output.getvalue())
        apt.assert_called_once_with(self.host,['wolfram-engine='+version],refresh=False)

    def test_wolfram_launchers_follow_package_update_and_remove_only_managed_entries(self):
        gui='/usr/share/applications/wolfram-mathematica.desktop'
        cli='/usr/share/applications/wolfram-desktop.desktop'
        duplicate='/usr/share/applications/wolfram-old.desktop'
        vendor_duplicate=f'{wolfram.VENDOR[0]}/wolfram-zz-legacy.desktop'
        script_menu='/usr/share/applications/wolframscript.desktop'
        self.file(gui,'[Desktop Entry]\nName=Mathematica\nName[fi]=Matematiikka\nExec=mathematica %F\n'
                      'Icon=mathematica-v15\nCategories=Education;Science;Math;\nMimeType=application/mathematica;\n')
        self.file(cli,'[Desktop Entry]\nName=Wolfram\nExec=lxterminal -e "/usr/bin/wolfram"\n'
                      'Icon=wolfram-v15\nCategories=Education;Science;Math;\n')
        self.file(duplicate,'[Desktop Entry]\nName=Wolfram\nExec=wolfram\nIcon=old\nNoDisplay=true\n')
        self.file(vendor_duplicate,'[Desktop Entry]\nName=Old kernel\nExec=wolfram\nIcon=wolfram-v15\n')
        self.file(script_menu,'[Desktop Entry]\nName=WolframScript\nExec=wolframscript\nIcon=wolfram-v15\n')
        for command in ('mathematica','wolfram','wolframscript'):
            self.file(f'/usr/bin/{command}','#!/bin/sh\nexit 0\n',0o755)
        own=self.file('/home/chem/.local/share/applications/own.desktop','personal file')
        listed=[gui,cli,duplicate,script_menu]
        self.host.probe=lambda argv: SimpleNamespace(returncode=0,stdout='\n'.join(listed))
        self.store.data['profile']='GENERAL'
        self.store.data['selected']={'wolfram':True}
        self.store.data['wolfram_owned']='15.0.1'
        with (redirect_stdout(io.StringIO()) as output,
              patch.object(lifecycle,'apt_inventory',return_value={'wolfram-engine':'15.0.1'}),
              patch.object(wolfram, 'package_metadata',return_value=None)):
            lifecycle.reconcile_wolfram_launchers(self.store,self.host)
            local_gui=self.store.path(wolfram.LOCAL+'/'+Path(gui).name)
            local_cli=self.store.path(wolfram.LOCAL+'/'+Path(cli).name)
            hidden=self.store.path(wolfram.LOCAL+'/'+Path(duplicate).name)
            before=local_gui.stat().st_ino
            self.assertEqual(lifecycle.verify(self.store,self.host,'wolfram'),0)
            lifecycle.reconcile_wolfram_launchers(self.store,self.host)
            self.assertEqual(local_gui.stat().st_ino,before)
            local_gui.unlink()
            approved=lifecycle.software_action(self.store,self.host,'repair','wolfram',[],True)
            self.assertFalse(local_gui.exists())
            lifecycle.software_action(self.store,self.host,'repair','wolfram',[],False,approved)
            self.assertIn('Name=Wolfram Mathematica (GUI)',local_gui.read_text())
            self.assertIn('Icon=mathematica-v15',local_gui.read_text())
            self.assertNotIn('Name[fi]',local_gui.read_text())
            self.assertIn('Name=Wolfram Language (CLI)',local_cli.read_text())
            self.assertIn('Exec=/usr/bin/wolfram\n',local_cli.read_text())
            self.assertIn('Terminal=true',local_cli.read_text())
            self.assertIn('Hidden=true',hidden.read_text())
            for original in (vendor_duplicate, script_menu):
                self.assertIn('Hidden=true',self.store.path(wolfram.LOCAL+'/'+Path(original).name).read_text())
            if os.path.exists('/usr/bin/desktop-file-validate'):
                subprocess.run(['desktop-file-validate',str(local_gui),str(local_cli),str(hidden)],check=True)
            listed.remove(duplicate)
            self.file(gui, self.store.path(gui).read_text().replace('mathematica-v15','mathematica-v16'))
            lifecycle.reconcile_wolfram_launchers(self.store,self.host)
            self.assertFalse(hidden.exists())
            self.assertIn('Icon=mathematica-v16',local_gui.read_text())
            with patch.object(lifecycle,'apt_removal'):
                actions,blocked=lifecycle.removal_plan(self.store,self.host,'wolfram')
            self.assertFalse(blocked)
            self.assertIn(('apt','wolfram-engine'),actions)
            with patch.object(lifecycle,'apt_removal'), patch.object(lifecycle,'apt_inventory',side_effect=[
                {'wolfram-engine':'15.0.1'}, {}
            ]):
                self.assertEqual(lifecycle.apply_removal(self.store,self.host,actions,blocked),0)
        self.assertIn('PENDING MANUAL ACCEPTANCE',output.getvalue())
        self.assertFalse(local_gui.exists())
        self.assertFalse(local_cli.exists())
        self.assertEqual(own.read_text(),'personal file')
        self.assertTrue(self.store.path(gui).exists())

    def test_chromium_repairs_r2_guest_policy_and_preserves_normal_launch(self):
        self.file('/usr/bin/chromium','#!/bin/sh\nfor f in /etc/chromium.d/*; do . "$f"; done\n',0o755)
        self.file('/usr/share/applications/chromium.desktop','[Desktop Entry]\nExec=/usr/bin/chromium %U\n')
        self.store.data['profile']='AALTO'
        targets=[(path,False) for _,path in lifecycle.CHROMIUM_FILES]
        with self.store.stage('chromium',targets):
            hook=self.file(targets[0][0],'CHROMIUM_FLAGS="$CHROMIUM_FLAGS --guest --password-store=basic"\n'
                           'export CHROME_USER_DATA_DIR="$XDG_RUNTIME_DIR/rpi-images-chromium"\n')
            policy=self.file(targets[1][0],'{ "BrowserGuestModeEnforced": true, "PasswordManagerEnabled": false }\n')
        with redirect_stdout(io.StringIO()):
            lifecycle.software_action(self.store,self.host,'repair','chromium',[],True)
            self.assertIn('--guest',hook.read_text())
            self.assertTrue(json.loads(policy.read_text())['BrowserGuestModeEnforced'])
            lifecycle.software_action(self.store,self.host,'repair','chromium',[],False)
            self.assertEqual(lifecycle.verify(self.store,self.host,'chromium'),0)
            before=hook.stat().st_ino
            lifecycle.software_action(self.store,self.host,'update','chromium',[],False)
            self.assertEqual(hook.stat().st_ino,before)
        self.assertEqual(json.loads(policy.read_text()),{'PasswordManagerEnabled':False})
        test_hook=Path(self.work.name)/'chromium-hook'
        test_hook.write_text(hook.read_text().replace('/etc/chromium/policies/managed/99-rpi-images-shared.json',str(policy)))
        env={key:value for key,value in os.environ.items() if key not in ('XDG_RUNTIME_DIR','CHROME_USER_DATA_DIR')}
        cmd=['dash','-c','CHROMIUM_FLAGS=--vendor; . "$1"; printf "%s\n" "$CHROMIUM_FLAGS" "${CHROME_USER_DATA_DIR-unset}"','dash',str(test_hook)]
        def launch(options):
            result=subprocess.run(cmd,env=options,capture_output=True,text=True,check=True)
            return result.stdout.splitlines()
        self.assertEqual(launch(env),['--vendor --password-store=basic','unset'])
        self.assertEqual(launch({**env,'CHROME_USER_DATA_DIR':'/existing/profile'}),
                         ['--vendor --password-store=basic','/existing/profile'])
        missing_hook=Path(self.work.name)/'chromium-hook-no-policy'
        missing_hook.write_text(test_hook.read_text().replace(str(policy),str(policy.with_suffix('.absent'))))
        cmd[-1]=str(missing_hook)
        self.assertEqual(launch(env),['--vendor','unset'])
        conflict=self.file('/etc/chromium/policies/managed/local.json','{"PasswordManagerEnabled":true}')
        with self.assertRaisesRegex(ValueError,'Conflicting Chromium policy'):
            lifecycle.chromium_policy(self.store)
        actions,blocked=lifecycle.removal_plan(self.store,self.host,'chromium')
        with redirect_stdout(io.StringIO()):
            self.assertEqual(lifecycle.apply_removal(self.store,self.host,actions,blocked),0)
        self.assertFalse(hook.exists())
        self.assertFalse(policy.exists())
        self.assertTrue(conflict.exists())

    def test_manage_and_update_all_follow_saved_policy_without_touching_personal_data(self):
        self.file('/usr/bin/chromium','#!/bin/sh\nfor f in /etc/chromium.d/*; do . "$f"; done\n',0o755)
        self.file('/usr/share/applications/chromium.desktop','[Desktop Entry]\nExec=/usr/bin/chromium %U\n')
        personal=self.file('/home/alice/.config/chromium/Preferences','personal browser data')
        bookmarks=self.file('/home/alice/.config/chromium/Default/Bookmarks','regular profile bookmarks')
        self.host.existing.add('/usr/bin/chromium')
        for profile in ('GENERAL','HOME','AALTO'):
            with self.subTest(profile=profile), redirect_stdout(io.StringIO()) as out:
                data=self.store.data
                data.update(profile=profile,chromium_policy='shared')
                self.store.save()
                repair=['--manage','--action','repair','--component','chromium','--dry-run']
                self.assertEqual(lifecycle.main(repair,self.host,store=self.store),0)
                files=[self.store.path(path) for _,path in lifecycle.CHROMIUM_FILES]
                self.assertFalse(any(path.exists() for path in files))
                self.assertEqual({change.component for change in update_all.file_plan(self.store,self.host,{},None)},{'chromium'})
                lifecycle.software_action(self.store,self.host,'repair','chromium',[],False)
                self.assertEqual(lifecycle.verify(self.store,self.host,'chromium'),0)
                self.store.data['chromium_policy']='personal'
                self.store.save()
                self.assertEqual(lifecycle.main(repair,self.host,store=self.store),0)
                self.assertTrue(all(path.exists() for path in files))
                self.assertFalse(update_all.file_plan(self.store,self.host,{},None))
                original=files[1].read_bytes()
                files[1].write_text('{"local":true}')
                with self.assertRaisesRegex(ValueError,'override preserved'):
                    lifecycle.chromium_policy(self.store,apply=True)
                self.assertTrue(files[0].exists())
                self.assertEqual(files[1].read_text(),'{"local":true}')
                files[1].write_bytes(original)
                lifecycle.software_action(self.store,self.host,'repair','chromium',[],False)
                self.assertEqual(lifecycle.verify(self.store,self.host,'chromium'),0)
                self.assertFalse(any(path.exists() for path in files))
                self.assertEqual(personal.read_text(),'personal browser data')
                self.assertEqual(bookmarks.read_text(),'regular profile bookmarks')
                self.assertIn('regular Chromium profile and keyring',out.getvalue())
