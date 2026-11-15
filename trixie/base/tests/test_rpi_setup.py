"""Provisioning is mocked: no real accounts, services, /opt or package changes."""
import argparse
import copy
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'install'))
import setup_rpi as m
import rpi_accounts as accounts


def state(invoker='alice'):
    return dict(model='Raspberry Pi 5 Model B',ram_mib=8192,os='Raspberry Pi OS Trixie',os_id='debian',codename='trixie',architecture='aarch64',hostname='rpi-test',invoking_user=invoker,accounts={name:dict(uid=1000+i,gid=1000+i,home='/home/'+name,shell='/bin/bash') for i,name in enumerate(['alice','chem','chem-it'])},ssh={'is-active':'active'},existing={})


class FakeHost:
    def __init__(self,invoker='alice',existing=(),fail=None):
        self.env={};self.calls=[];self.data=state(invoker);self.existing={str(p) for p in existing};self.fail=fail
    def snapshot(self):return copy.deepcopy(self.data)
    def exists(self,path):return str(path) in self.existing
    def environment(self,prefix):return str(prefix) in self.existing
    def change_hostname(self,old,new):self.run(['hostnamectl','set-hostname',new])
    def run(self,argv,capture=False,**kwargs):
        args=[str(x) for x in argv];self.calls.append(args)
        if self.fail and any(self.fail in x for x in args):raise subprocess.CalledProcessError(1,args)
        text='Candidate: 1.0\n' if 'apt-cache' in args else 'yes\n' if 'timedatectl' in args else 'active\n'
        return SimpleNamespace(stdout=text,returncode=0)


class ProfileTests(unittest.TestCase):
    def resolve(self,*argv,host=None):
        host=host or FakeHost();a=m.parser().parse_args(list(argv)+['--plan']);return a,m.resolve(a,host.snapshot(),host)

    def test_general_uses_imager_account_no_private_assumptions(self):
        a,p=self.resolve('--profile','GENERAL')
        self.assertEqual(p['primary'],'alice');self.assertEqual(p['additional'],[])
        self.assertNotIn('aalto',p['ntp']);self.assertFalse(p['components']['share']);self.assertFalse(p['components']['wolfram'])

    def test_home_ntp_and_ssh(self):
        _,p=self.resolve('--profile','HOME')
        self.assertEqual(p['primary'],'alice');self.assertEqual(p['ntp'],'time.mikes.fi')
        self.assertEqual(p['ssh'],'enable');self.assertTrue(p['components']['share']);self.assertEqual(p['additional'],[])

    def test_aalto_chem_defaults(self):
        _,p=self.resolve('--profile','AALTO','--school','CHEM')
        self.assertEqual(p['primary'],'chem');self.assertEqual(p['additional'],['chem-it'])
        self.assertEqual(p['ntp'],'ntp.aalto.fi');self.assertTrue(p['components']['wolfram']);self.assertEqual(p['ssh'],'keep')

    def test_aalto_custom_policy_rejected(self):
        with self.assertRaisesRegex(ValueError,'school custom'):
            self.resolve('--profile','AALTO','--school','custom','--primary-user','alice','--no-wolfram')

    def test_unrelated_aalto_invoker_uses_chem_policy(self):
        _,p=self.resolve('--profile','AALTO')
        self.assertEqual(p['school'],'CHEM');self.assertEqual(p['primary'],'chem');self.assertEqual(p['additional'],['chem-it'])

    def test_aalto_default_is_independent_of_invoker(self):
        for invoker in ('chem','alice',None):
            with self.subTest(invoker=invoker):
                _,p=self.resolve('--profile','AALTO',host=FakeHost(invoker))
                self.assertEqual((p['school'],p['primary'],p['additional']),('CHEM','chem',['chem-it']))

    def test_aalto_sudo_invoker_does_not_change_account_policy(self):
        h=FakeHost()
        with patch.object(accounts,'uid_min',return_value=1000),patch.object(os,'getuid',return_value=0):
            h.data['invoking_user']=accounts.invoking_user(h.data['accounts'],{'SUDO_USER':'alice','SUDO_UID':'1000'})
        _,p=self.resolve('--profile','AALTO',host=h)
        self.assertEqual(h.data['invoking_user'],'alice');self.assertEqual(p['primary'],'chem');self.assertEqual(p['additional'],['chem-it'])

    def test_aalto_root_without_invoker_keeps_default_and_explicit_primary(self):
        h=FakeHost(None)
        with patch.object(os,'getuid',return_value=0):self.assertIsNone(accounts.invoking_user(h.data['accounts'],{}))
        _,p=self.resolve('--profile','AALTO',host=h);self.assertEqual(p['primary'],'chem')
        _,p=self.resolve('--profile','AALTO','--primary-user','alice',host=h)
        self.assertEqual((p['primary'],p['additional']),('alice',['chem-it']))

    def test_aalto_primary_override_keeps_required_maintenance_account(self):
        _,p=self.resolve('--profile','AALTO','--primary-user','alice')
        self.assertEqual((p['school'],p['primary'],p['additional']),('CHEM','alice',['chem-it']))

    def test_aalto_optional_accounts_complement_maintenance_without_duplicates(self):
        for requested in (['admin2'],['chem-it','admin2'],['admin2','chem-it']):
            with self.subTest(requested=requested):
                argv=[arg for user in requested for arg in ('--additional-user',user)]
                _,p=self.resolve('--profile','AALTO',*argv)
                self.assertEqual(p['additional'],['chem-it','admin2'])
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.resolve('--profile','AALTO','--additional-user','admin2','--additional-user','admin2')

    def test_aalto_no_additional_users_and_explicit_empty_list_rejected(self):
        with self.assertRaisesRegex(ValueError,'maintenance'):
            self.resolve('--profile','AALTO','--no-additional-users')
        a=m.parser().parse_args(['--profile','AALTO','--plan']);a.additional_user=[];h=FakeHost()
        with self.assertRaisesRegex(ValueError,'maintenance'):m.resolve(a,h.snapshot(),h)

    def test_aalto_maintenance_cannot_be_primary_and_additional(self):
        with self.assertRaisesRegex(ValueError,'maintenance'):
            self.resolve('--profile','AALTO','--primary-user','chem-it')

    def test_aalto_interactive_has_no_school_prompt(self):
        h=FakeHost();a=m.parser().parse_args(['--plan']);prompts=[]
        def answer(prompt,default):
            prompts.append(prompt)
            if prompt.startswith('Profile GENERAL'):return 'AALTO'
            if prompt.startswith('Additional sudo'):return 'admin2'
            return default
        with patch.object(m,'ask',side_effect=answer):m.interactive(a,h.snapshot())
        p=m.resolve(a,h.snapshot(),h)
        self.assertEqual((p['school'],p['primary'],p['additional']),('CHEM','chem',['chem-it','admin2']))
        self.assertFalse(any('school' in prompt.lower() for prompt in prompts));self.assertEqual(h.calls,[])

    def test_aalto_interactive_preserves_explicit_primary_selection(self):
        h=FakeHost();a=m.parser().parse_args(['--primary-user','alice','--plan'])
        with patch.object(m,'ask',side_effect=lambda prompt,default:'AALTO' if prompt.startswith('Profile GENERAL') else default):m.interactive(a,h.snapshot())
        p=m.resolve(a,h.snapshot(),h);self.assertEqual(p['primary'],'alice');self.assertEqual(p['additional'],['chem-it'])

    def test_aalto_missing_primary_recovery_and_password_guards_preserved(self):
        h=FakeHost();h.data['accounts'].pop('chem');h.data['accounts'].pop('chem-it')
        with patch.object(sys.stdin,'isatty',return_value=False),self.assertRaisesRegex(ValueError,'recovery'):
            self.resolve('--profile','AALTO',host=h)
        _,p=self.resolve('--profile','AALTO','--recovery','keep',host=h)
        self.assertEqual((p['primary'],p['additional']),('alice',['chem-it']))
        _,p=self.resolve('--profile','AALTO','--recovery','create',host=h)
        self.assertEqual((p['primary'],p['additional']),('chem',['chem-it']))
        a=m.parser().parse_args(['--profile','AALTO','--recovery','create','--yes'])
        with patch.object(sys.stdin,'isatty',return_value=False),self.assertRaisesRegex(ValueError,'password'):m.resolve(a,h.snapshot(),h)
        self.assertEqual(h.calls,[])

    def test_aalto_conflicts_fail_before_apply_and_host_commands(self):
        for extra in (['--school','custom'],['--no-additional-users'],['--primary-user','chem-it']):
            h=FakeHost()
            with self.subTest(extra=extra),patch.object(m,'apply',side_effect=AssertionError('must not apply')),contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError):
                m.main(['--profile','AALTO','--yes',*extra],h)
            self.assertEqual(h.calls,[])

    def test_general_home_account_selection_and_override_semantics_unchanged(self):
        for profile in ('GENERAL','HOME'):
            _,p=self.resolve('--profile',profile,'--additional-user','admin2')
            self.assertEqual((p['school'],p['primary'],p['additional']),('custom','alice',['admin2']))
            _,p=self.resolve('--profile',profile,'--no-additional-users')
            self.assertEqual(p['additional'],[])

    def test_missing_primary_recovery_create(self):
        _,p=self.resolve('--profile','GENERAL','--primary-user','correct','--recovery','create')
        self.assertEqual(p['primary'],'correct')

    def test_missing_primary_recovery_keep(self):
        _,p=self.resolve('--profile','GENERAL','--primary-user','correct','--recovery','keep')
        self.assertEqual(p['primary'],'alice')

    def test_missing_primary_cancels_safely(self):
        with patch.object(sys.stdin,'isatty',return_value=False),self.assertRaises(ValueError):
            self.resolve('--profile','GENERAL','--primary-user','correct')

    def test_missing_sudo_user_requires_explicit_primary(self):
        h=FakeHost(invoker=None)
        with self.assertRaises(ValueError):self.resolve('--profile','GENERAL',host=h)
        _,p=self.resolve('--profile','GENERAL','--primary-user','alice',host=h)
        self.assertEqual(p['primary'],'alice')

    def test_hostname_validation(self):
        for value in ('rpi-01','RPI5','x'*63):self.assertTrue(m.hostname(value))
        for value in ('-rpi','rpi-','rpi.test','bad name','x'*64,'rpi\nother'):
            with self.subTest(value=value),self.assertRaises(ValueError):m.hostname(value)

    def test_existing_hostname_preserved(self):
        _,p=self.resolve('--profile','GENERAL');self.assertEqual(p['hostname'],'rpi-test')

    def test_existing_hostname_case_preserved(self):
        host=FakeHost();host.data['hostname']='RPi-Test'
        _,p=self.resolve('--profile','GENERAL',host=host);self.assertEqual(p['hostname'],'RPi-Test')

    def test_hosts_alias_update_preserves_other_entries_and_comments(self):
        before='127.0.0.1 localhost\n127.0.1.1 rpi-test alias # rpi-test in comment\n10.0.0.1 other rpi-test\n'
        after=m.hosts_alias(before,'rpi-test','new-rpi')
        self.assertEqual(after,'127.0.0.1 localhost\n127.0.1.1 new-rpi alias # rpi-test in comment\n10.0.0.1 other rpi-test\n')

    def test_duplicate_accounts_rejected(self):
        with self.assertRaises(ValueError):self.resolve('--profile','GENERAL','--additional-user','alice')

    def test_offline_share_csv_and_default_group(self):
        _,p=self.resolve('--profile','HOME','--share-csv',str(BASE/'config/rpi-share.example.csv'),'--default-group','students')
        self.assertEqual(p['config']['defaults']['group'],'students');self.assertEqual(p['owners'],['alice'])

    def test_configure_later_never_installs_example(self):
        _,p=self.resolve('--profile','HOME','--share-later');self.assertIsNone(p['config'])

    def test_home_cannot_remove_share_component(self):
        with self.assertRaises(ValueError):self.resolve('--profile','HOME','--no-share')

    def test_existing_share_installation_prefix_preserved(self):
        h=FakeHost(existing=['/opt/lab/bin/rpi-share'])
        _,p=self.resolve('--profile','HOME',host=h)
        self.assertEqual(p['share_prefix'],Path('/opt/lab'))

    def test_plan_does_not_call_apply_or_commands(self):
        host=FakeHost()
        with patch.object(m,'apply',side_effect=AssertionError('no apply')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(['--profile','HOME','--plan'],host),0)
        self.assertEqual(host.calls,[])

    def test_no_tty_password_fails_before_any_change(self):
        host=FakeHost();a=m.parser().parse_args(['--profile','GENERAL','--primary-user','newuser','--recovery','create','--yes'])
        with patch.object(sys.stdin,'isatty',return_value=False),self.assertRaisesRegex(ValueError,'password'):
            m.resolve(a,host.snapshot(),host)
        self.assertEqual(host.calls,[])

    def test_existing_environment_actions_keep(self):
        h=FakeHost(existing=['/opt/conda','/opt/lab314','/opt/rpi'])
        a,p=self.resolve('--profile','GENERAL','--hardware',host=h);s=dict(m.stages(a,p))
        self.assertEqual(s['conda'],'KEEP');self.assertEqual(s['lab314'],'KEEP');self.assertEqual(s['hardware'],'KEEP')

    def test_component_order(self):
        a,p=self.resolve('--profile','AALTO','--school','CHEM','--ide-prefix','/opt/example-ide','--hardware')
        names=[name for name,_ in m.stages(a,p)]
        for x,y in [('accounts','profile'),('profile','system'),('system','conda'),('conda','spyder-ide'),('spyder-ide','lab314'),('lab314','hardware'),('hardware','wolfram'),('share','verification')]:self.assertLess(names.index(x),names.index(y))

    def test_spyder_targeted_kernel_after_selected_ide(self):
        h=FakeHost(existing=['/opt/conda','/opt/lab314'])
        a,p=self.resolve('--profile','GENERAL','--ide-prefix','/opt/example-ide',host=h)
        s=dict(m.stages(a,p));self.assertEqual(s['lab314'],'KEEP');self.assertIn('spyder-kernel',s)

    def test_lab314_python_series_and_components_remain_independent(self):
        self.assertIn("['3','14']",(BASE/'install/update_lab314.py').read_text())
        policy=json.loads((BASE/'config/lab314/requirements.json').read_text())
        self.assertEqual(policy['python'],'3.14.*');self.assertIn('python=3.14',policy['conda'])
        for script in ('create_lab314_env.sh','create_rpi_env.sh','install_optional_wolfram.sh','uninstall_optional_wolfram.sh','install_envrun.sh'):
            self.assertTrue((BASE/'install'/script).is_file())

    def test_environment_corruption_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'partial';p.mkdir()
            with self.assertRaises(ValueError):m.Host().environment(p)


class OrchestrationTests(unittest.TestCase):
    def execute(self,argv,host=None,wolfram_exists=False):
        host=host or FakeHost();host.data['wolfram']={'engine_installed':wolfram_exists,'cli':'/mock/wolframscript' if wolfram_exists else None}
        a=m.parser().parse_args(argv+['--yes']);plan=m.resolve(a,host.snapshot(),host)
        with patch.object(os,'geteuid',return_value=0),patch.object(accounts,'ensure_user') as ensure,patch.object(m,'install_config',return_value='DEFERRED: catalog later'),patch.object(m.shutil,'which',return_value='/mock/wolframscript' if wolfram_exists else None),patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')),contextlib.redirect_stdout(io.StringIO()):
            result=m.apply(a,plan,host.snapshot(),host)
        return result,host,ensure

    def test_standard_workflow_calls_existing_scripts(self):
        result,h,ensure=self.execute(['--profile','GENERAL','--hardware'])
        self.assertEqual(result,0)
        text='\n'.join(' '.join(x) for x in h.calls)
        for name in ('pre_profile.sh','install_rpi_base.sh','install_conda_base.sh','create_lab314_env.sh','create_rpi_env.sh','verify_rpi_lab314.sh','verify_rpi_env.sh'):self.assertIn(name,text)
        self.assertEqual(h.env['DO_APT_UPGRADE'],'0');ensure.assert_any_call('alice',admin=True,passwordless=True)

    def test_hostname_changes_only_on_explicit_difference(self):
        _,h,_=self.execute(['--profile','GENERAL']);self.assertFalse(any('set-hostname' in x for x in h.calls))
        _,h,_=self.execute(['--profile','GENERAL','--hostname','new-rpi']);self.assertTrue(any('set-hostname' in x for x in h.calls))

    def test_existing_environment_not_recreated(self):
        _,h,_=self.execute(['--profile','GENERAL','--hardware'],FakeHost(existing=['/opt/conda','/opt/lab314','/opt/rpi']))
        text='\n'.join(' '.join(x) for x in h.calls)
        for name in ('install_conda_base.sh','create_lab314_env.sh','create_rpi_env.sh'):self.assertNotIn(name,text)

    def test_wolfram_selected_and_deselected(self):
        _,h,_=self.execute(['--profile','AALTO','--school','CHEM'])
        self.assertTrue(any('install_optional_wolfram.sh' in ' '.join(x) for x in h.calls))
        _,h,_=self.execute(['--profile','AALTO','--school','CHEM','--no-wolfram'])
        self.assertFalse(any('install_optional_wolfram.sh' in ' '.join(x) for x in h.calls))

    def test_existing_wolfram_not_reinstalled(self):
        _,h,_=self.execute(['--profile','AALTO','--school','CHEM'],wolfram_exists=True)
        self.assertFalse(any('install_optional_wolfram.sh' in ' '.join(x) for x in h.calls))

    def test_unavailable_imaging_does_not_block_base(self):
        result,h,_=self.execute(['--profile','GENERAL','--imaging','--imaging-source','/does/not/exist'])
        self.assertEqual(result,0);self.assertTrue(any('verify_rpi_lab314.sh' in ' '.join(x) for x in h.calls))
        self.assertFalse(any('01-install.sh' in ' '.join(x) for x in h.calls))

    def test_imaging_uses_full_own_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp);(source/'scripts/install').mkdir(parents=True)
            (source/'scripts/install/01-install.sh').write_text('fixture')
            result,h,_=self.execute(['--profile','GENERAL','--imaging-source',str(source),'--imaging-app','vrecorder-full-rpi.py','--imaging-approved'])
        self.assertEqual(result,0);text='\n'.join(' '.join(x) for x in h.calls)
        self.assertIn('01-install.sh --app vrecorder-full-rpi.py',text);self.assertIn('02-diagnose.sh',text)
        self.assertNotIn('install_sci_apps.sh',text)

    def test_core_failure_reports_and_blocks_dependents(self):
        result,h,_=self.execute(['--profile','GENERAL'],FakeHost(fail='install_conda_base.sh'))
        self.assertEqual(result,1);self.assertFalse(any('create_lab314_env.sh' in ' '.join(x) for x in h.calls))

    def test_wrong_host_apply_refused(self):
        h=FakeHost();h.data['model']='development workstation';a=m.parser().parse_args(['--profile','GENERAL']);p=m.resolve(a,h.snapshot(),h)
        with patch.object(os,'geteuid',return_value=0),self.assertRaisesRegex(ValueError,'Raspberry Pi'):m.apply(a,p,h.snapshot(),h)
        self.assertEqual(h.calls,[])

    def test_public_ssh_and_home_defaults_reuse_shared_policy(self):
        self.assertIn('time.mikes.fi',(BASE/'install/pre_home.sh').read_text())
        self.assertNotIn('ntp.aalto.fi',(BASE/'install/pre_home.sh').read_text())
        self.assertIn('pre_profile.sh',(BASE/'install/pre_aalto.sh').read_text())
        self.assertIn('NOPASSWD: ALL',(BASE/'install/account-policy.sh').read_text())


class AccountTests(unittest.TestCase):
    def test_username_validation(self):
        for name in ('chem','chem-it','alice_1'):self.assertEqual(accounts.username(name),name)
        for name in ('root','Bad','a space','--option','a;command','../escape'):
            with self.subTest(name=name),self.assertRaises(ValueError):accounts.username(name)

    def test_invoker_uid_mismatch_refused(self):
        with patch.object(accounts,'uid_min',return_value=1000),self.assertRaises(ValueError):accounts.invoking_user(state()['accounts'],{'SUDO_USER':'alice','SUDO_UID':'9999'})

    def test_existing_account_never_passwd_reset(self):
        with patch.object(accounts,'local_accounts',return_value=state()['accounts']),patch.object(accounts,'uid_min',return_value=1000),patch.object(accounts,'run') as run:
            accounts.ensure_user('alice',admin=True,passwordless=True)
        self.assertFalse(any(call.args[0][0] in ('passwd','useradd','userdel') for call in run.call_args_list))
        self.assertTrue(any('account-policy.sh' in str(x) for call in run.call_args_list for x in call.args[0]))

    def test_password_failure_keeps_new_account_locked(self):
        calls=[]
        def run(argv,**kwargs):
            calls.append(argv)
            if argv[0]=='passwd':raise subprocess.CalledProcessError(1,argv)
        with patch.object(accounts,'local_accounts',return_value={}),patch.object(accounts.pwd,'getpwnam',side_effect=KeyError),patch.object(sys.stdin,'isatty',return_value=True),patch.object(sys.stdout,'isatty',return_value=True),patch.object(accounts,'run',side_effect=run),patch.object(accounts.subprocess,'run') as lock,self.assertRaises(subprocess.SubprocessError):accounts.ensure_user('newuser',True,True)
        self.assertIn('/usr/sbin/nologin',calls[0]);self.assertIn('--lock',lock.call_args.args[0]);self.assertFalse(any(argv[:2]==['usermod','--shell'] for argv in calls))

    def test_password_noninteractive_refused_before_useradd(self):
        with patch.object(accounts,'local_accounts',return_value={}),patch.object(accounts.pwd,'getpwnam',side_effect=KeyError),patch.object(sys.stdin,'isatty',return_value=False),patch.object(accounts,'run') as run,self.assertRaises(ValueError):accounts.ensure_user('newuser')
        run.assert_not_called()

    def test_successful_new_admin_checks_credentials_and_privileges_before_shell(self):
        created={'newuser':dict(uid=1000,gid=1000,home='/fixture/newuser',shell='/bin/bash')}
        with patch.object(accounts,'local_accounts',side_effect=[{},created]),patch.object(accounts.pwd,'getpwnam',side_effect=KeyError),patch.object(sys.stdin,'isatty',return_value=True),patch.object(sys.stdout,'isatty',return_value=True),patch.object(accounts,'run') as run:
            accounts.ensure_user('newuser',True,True)
        calls=[c.args[0] for c in run.call_args_list]
        self.assertIn('/usr/sbin/nologin',calls[0]);self.assertEqual(calls[1],['passwd','newuser'])
        self.assertIn(['sudo','-n','-u','newuser','sudo','-n','true'],calls)
        self.assertEqual(calls[-1],['usermod','--shell','/bin/bash','newuser'])

    def review(self,old='chem',replacement='alice',sessions='1 1000 alice seat0 tty1 active\n',process=1,cron=1,privilege=True):
        def query(argv,**kwargs):
            if argv[0]=='loginctl':return SimpleNamespace(returncode=0,stdout=sessions)
            if argv[0]=='pgrep':return SimpleNamespace(returncode=process,stdout='')
            if argv[0]=='crontab':return SimpleNamespace(returncode=cron,stdout='job' if cron==0 else '')
            raise AssertionError('unexpected account query: '+str(argv))
        with patch.object(accounts,'local_accounts',return_value=state()['accounts']),patch.object(accounts,'invoking_user',return_value='alice'),patch.object(accounts,'uid_min',return_value=1000),patch.object(os,'getuid',return_value=0),patch.object(accounts.subprocess,'run',side_effect=query),patch.object(accounts,'run',side_effect=None if privilege else subprocess.CalledProcessError(1,['sudo'])),patch.object(Path,'is_file',return_value=False),patch.object(Path,'exists',return_value=False):
            return accounts.removal_review(old,replacement)

    def test_current_account_removal_refused(self):
        with self.assertRaises(ValueError):self.review(old='alice',replacement='chem')

    def test_active_session_removal_refused(self):
        with self.assertRaises(ValueError):self.review(sessions='1 1001 chem seat0 tty1 active\n')

    def test_running_process_removal_refused(self):
        with self.assertRaises(ValueError):self.review(process=0)

    def test_last_usable_admin_protection(self):
        with self.assertRaises(subprocess.SubprocessError):self.review(privilege=False)

    def test_scheduled_tasks_require_review(self):
        with self.assertRaises(ValueError):self.review(cron=0)

    def test_removal_plan_preserves_home(self):
        review=self.review();self.assertTrue(review['home_preserved']);self.assertEqual(review['home'],'/home/chem')

    def test_account_removal_requires_separate_confirmation(self):
        review={'home_preserved':True}
        with patch.object(accounts,'removal_review',return_value=review),patch.object(os,'geteuid',return_value=0),patch.object(sys.stdin,'isatty',return_value=False),patch.object(accounts,'run') as run,self.assertRaises(ValueError):
            accounts.main(['--remove','chem','--replacement','alice','--apply','--login-verified','--files-reviewed'])
        run.assert_not_called()

    def test_confirmed_removal_never_deletes_home(self):
        with patch.object(accounts,'removal_review',return_value={'home_preserved':True}),patch.object(os,'geteuid',return_value=0),patch.object(accounts,'run') as run:
            accounts.main(['--remove','chem','--replacement','alice','--apply','--login-verified','--files-reviewed','--confirm-remove','chem'])
        run.assert_called_once_with(['userdel','--','chem'])


class ConfigurationOwnershipTests(unittest.TestCase):
    def test_user_home_not_root_home_and_no_unapproved_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)/'user';home.mkdir();local={'alice':dict(uid=1000,gid=1000,home=str(home),shell='/bin/bash')}
            plan=dict(config={'version':1},owners=['alice'])
            with patch.object(accounts,'local_accounts',return_value=local),patch.object(os,'chown') as chown:
                m.install_config(plan)
            path=home/'.config/rpi-share.json';self.assertEqual(path.stat().st_mode & 0o777,0o600)
            chown.assert_any_call(path,1000,1000)
            changed=dict(config={'version':2},owners=['alice'])
            with patch.object(accounts,'local_accounts',return_value=local),self.assertRaises(ValueError):m.install_config(changed)
            self.assertEqual(json.loads(path.read_text()),{'version':1})

    def test_configuration_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)/'user';home.mkdir();outside=Path(tmp)/'outside';outside.mkdir();(home/'.config').symlink_to(outside)
            with patch.object(accounts,'local_accounts',return_value={'alice':dict(uid=1000,gid=1000,home=str(home))}),self.assertRaises(ValueError):m.config_destination('alice')


if __name__=='__main__':unittest.main()
