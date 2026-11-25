"""APT lifecycle regression tests with a private journal and a mocked host."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_rpi_setup import FakeHost, m
from installation_state import Store
import os_upgrade as upgrade


class Host(FakeHost):
    def __init__(self):
        super().__init__()
        self.apt={'linux-image-rpi-2712':'1','previous':'2'}
        self.failure=None
        self.audit=''
        self.plan='Inst linux-image-rpi-2712 [1] (2 Raspberry Pi Archive:trixie [arm64])\n'
        self.repo=' release o=Debian,n=trixie\n release o=Raspberry Pi Archive,n=trixie\n'

    def run(self,args,capture=False,**kwargs):
        command=list(map(str,args))
        self.calls.append(command)
        last=command[-1]
        if last==self.failure and '--simulate' not in command:
            raise subprocess.CalledProcessError(100,command)
        output=''
        if last=='policy':
            output=self.repo
        elif '--simulate' in command:
            output=self.plan
        elif last=='--audit':
            output=self.audit
        elif last=='--print-architecture':
            output='arm64\n'
        elif '--configure' in command:
            self.audit=''
        elif last=='full-upgrade':
            self.apt['linux-image-rpi-2712']='2'
        return subprocess.CompletedProcess(command,0,output,'')


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.host=Host()
        self.store=Store(self.root/'state')
        with self.store.locked():
            self.store.start(self.host.snapshot(),self.host.apt.copy())
        self.host.records=self.store
        self.boot='boot-one'
        for patcher in (patch.object(upgrade,'REBOOT_REQUIRED',self.root/'reboot-marker'),
                        patch.object(upgrade,'boot_id',side_effect=lambda:self.boot),
                        patch.object(m.lifecycle,'apt_inventory',side_effect=lambda host:host.apt.copy())):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_approved_country_applies_before_first_reboot_and_verifies_on_resume(self):
        self.host.wlan_state=lambda: wire.copy()
        wire=dict(stored='',country='00',blocks=[('1','0')],radio='disabled')
        args=m.parser().parse_args(['--profile','HOME','--share-later','--yes','--wlan-country','SE'])
        run=self.host.run
        def execute(command,**options):
            if 'do_wifi_country' in command:
                wire.update(stored=command[-1],country=command[-1])
            if 'unblock' in command:
                wire.update(blocks=[('0','0')])
            if command[0]=='nmcli':
                wire.update(radio='enabled')
            return run(command,**options)
        with patch.object(self.host,'run',side_effect=execute), \
                patch.object(m.wlan,'read_state',side_effect=lambda host:host.wlan_state()), \
                patch.object(m.wlan,'boot_id',side_effect=lambda:self.boot), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(m.normal_setup(args,self.host.snapshot(),self.host,True,True),0)
            self.assertEqual(self.store.data['wlan_country'],'SE')
            self.assertIn('post-reboot verification pending',out.getvalue())
            self.boot='boot-two'
            def resume(a,plan,state,host):
                self.assertEqual(plan['wlan_country'],'SE')
                self.assertIn('verified after reboot',m.apply_wlan(host,plan,self.store))
                return 0
            with patch.object(m,'apply',side_effect=resume) as apply:
                self.assertEqual(m.normal_setup(m.parser().parse_args(['--yes']),self.host.snapshot(),self.host,True,True),0)
                apply.assert_called_once()
        self.assertEqual(sum('do_wifi_country' in args for args in self.host.calls),1)

    def perform(self, approve=lambda:True, approve_removals=lambda _packages:False):
        return upgrade.run(self.host,self.store,m.lifecycle.apt_inventory,approve,approve_removals,first_install=True)

    def test_fresh_full_upgrade_precedes_reboot_and_never_repeats_after_reboot(self):
        ready=m.preboot.BootStatus.READY
        reboot=m.preboot.BootStatus.REBOOT_REQUIRED
        def preboot(**kwargs):
            self.host.calls.append(['preboot'])
            return (reboot if self.boot=='boot-one' else ready),'fi'
        args=m.parser().parse_args(['--profile','HOME','--yes'])
        with patch.object(self.host,'run_preboot',side_effect=preboot), \
                patch.object(m,'show_plan'), \
                patch.object(m,'apply',return_value=0) as install,redirect_stdout(io.StringIO()) as output:
            self.assertEqual(m.normal_setup(args,self.host.snapshot(),self.host,True,True),0)
            install.assert_not_called()
            update_index=next(i for i,cmd in enumerate(self.host.calls) if cmd[-1]=='update')
            self.assertEqual(self.host.calls[0],['preboot'])
            self.assertGreater(update_index,0)
            self.assertTrue(upgrade.reboot_pending(self.store.data))
            self.assertEqual(m.normal_setup(args,self.host.snapshot(),self.host,True,True),0)
            install.assert_not_called()
            self.boot='boot-two'
            self.assertEqual(m.normal_setup(args,self.host.snapshot(),self.host,True,True),0)
        self.assertEqual(install.call_count,1)
        self.assertEqual(sum(cmd[-1]=='update' for cmd in self.host.calls),1)
        self.assertTrue(any('--no-remove' in cmd for cmd in self.host.calls))
        self.assertIn('Full OS upgrade: PASS',output.getvalue())
        self.assertEqual(self.store.load()['os_upgrade']['status'],'completed')

    def test_old_or_preexisting_installation_stays_unknown(self):
        old=self.host.snapshot()
        old['existing']={'/opt/lab314':True}
        other=Store(self.root/'other')
        with other.locked():
            other.start(old,self.host.apt)
        for data in (other.data,{k:v for k,v in self.store.data.items() if k!='os_upgrade'}):
            self.store.data=data
            args=m.parser().parse_args(['--profile','HOME','--yes'])
            with patch.object(m,'show_plan'),patch.object(m,'apply',return_value=0),redirect_stdout(io.StringIO()) as out:
                self.assertEqual(m.normal_setup(args,old,self.host,True,True),0)
            self.assertIn('Unknown',out.getvalue())
        self.assertFalse(any(cmd[-1]=='update' for cmd in self.host.calls))

    def test_missing_network_leaves_retryable_state_and_never_runs_upgrade(self):
        self.host.failure='update'
        with self.assertRaises(subprocess.CalledProcessError),redirect_stdout(io.StringIO()) as out:
            self.perform()
        self.assertIn('APT package lists: FAIL',out.getvalue())
        self.assertNotIn('Full OS upgrade: PASS',out.getvalue())
        self.assertEqual(self.store.load()['os_upgrade']['phase'],'lists')
        self.assertFalse(any(cmd[-1]=='full-upgrade' for cmd in self.host.calls))
        self.host.failure=None
        with redirect_stdout(io.StringIO()): self.assertTrue(self.perform())
        self.assertFalse(any('--configure' in cmd for cmd in self.host.calls))

    def test_interrupted_upgrade_resumes_dpkg_and_preserves_other_manifest_state(self):
        self.store.data.update(profile='HOME',keyboard='fi',selected={'spyder':True})
        self.host.failure='full-upgrade'
        with self.assertRaises(subprocess.CalledProcessError),redirect_stdout(io.StringIO()): self.perform()
        self.assertTrue(self.store.load()['os_upgrade']['recover_dpkg'])
        self.host.apt['linux-image-rpi-2712']='2'
        self.host.audit='incomplete package\n'
        self.host.failure=None
        with redirect_stdout(io.StringIO()): self.assertTrue(self.perform())
        self.assertIn(['dpkg','--force-confold','--configure','-a'],self.host.calls)
        self.assertTrue(upgrade.reboot_pending(self.store.data))
        self.assertEqual((self.store.data['profile'],self.store.data['keyboard'],self.store.data['selected']),
                         ('HOME','fi',{'spyder':True}))

    def test_unexpected_removals_need_separate_approval(self):
        self.host.plan+='Remv example [1]\nRemv other:armhf [2]\n'
        presented=[]
        with redirect_stdout(io.StringIO()):
            self.assertFalse(self.perform(approve_removals=lambda pkgs: presented.extend(pkgs) or False))
        self.assertEqual(presented,['example:arm64','other:armhf'])
        self.assertFalse(any('-y' in cmd for cmd in self.host.calls))
        with redirect_stdout(io.StringIO()): self.assertTrue(self.perform(approve_removals=lambda _:True))
        self.assertTrue(any(any('Pre-Install-Pkgs' in arg for arg in cmd) for cmd in self.host.calls))

    def test_apt_hook_rejects_a_different_removal_or_wrong_protocol(self):
        def payload(name):
            return f'VERSION 3\nSome::option=x\n\n{name} 1 arm64 same > - - none **REMOVE**\n'
        with upgrade.removal_guard(self.store.directory,{'example:arm64'}) as options:
            hook=options[1].split('=',1)[1]
            for data,status in ((payload('example'),0),(payload('other'),1),('VERSION 2\n',1)):
                result=subprocess.run([hook],input=data,text=True,capture_output=True)
                self.assertEqual(result.returncode,status,result.stderr)

    def test_wrong_release_blocks_the_transaction(self):
        self.host.repo+=' release o=Debian,n=forky\n'
        with redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'forky'):
            self.perform()
        self.assertFalse(any('-y' in cmd for cmd in self.host.calls))

    def test_preview_is_nonmutating(self):
        old=self.store.file.read_bytes()
        with redirect_stdout(io.StringIO()): upgrade.preview(self.host)
        self.assertEqual(self.store.file.read_bytes(),old)
        self.assertEqual(len(self.host.calls),1)
        self.assertIn('--simulate',self.host.calls[0])
