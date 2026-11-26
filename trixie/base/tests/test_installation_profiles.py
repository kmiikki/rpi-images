"""Offline preference validation and effective-plan reproduction."""
import copy
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_rpi_setup import FakeHost, m as setup, accounts
import installation_profiles as profiles
spec=importlib.util.spec_from_file_location('profile_builder',setup.HERE/'profile-builder.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
FIXTURES=Path(__file__).parent/'fixtures/installation-plans-v1.json'


def norm(value):
    if isinstance(value,Path):return str(value)
    if isinstance(value,dict):return {k:norm(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [norm(v) for v in value]
    return value


class ReproductionTests(unittest.TestCase):
    def test_effective_plans_and_exported_profiles(self):
        for key,original in json.loads(FIXTURES.read_text()).items():
            with self.subTest(context=key),tempfile.TemporaryDirectory() as tmp:
                h=FakeHost(original['invoker'],existing=['/opt/conda','/opt/lab314','/opt/rpi','/opt/lab/bin/rpi-share'] if original['existing'] else [])
                path=Path(tmp)/'profile.json';base=original['argv'][1]
                with contextlib.redirect_stdout(io.StringIO()):builder.main(['--export',base,'--output',str(path)]);builder.main(['--validate',str(path)])
                direct=setup.parser().parse_args(original['argv'])
                argv=['--profile-file',str(path),'--plan']+original['argv'][3:]
                reloaded=profiles.parse_arguments(setup.parser(),argv)
                for a in (direct,reloaded):
                    plan=setup.resolve(a,h.snapshot(),h)
                    self.assertEqual(norm(plan),original['plan'])
                    self.assertEqual(norm(setup.stages(a,plan)),original['stages'])
                    self.assertEqual({k:norm(getattr(a,k)) for k in original['runtime']},original['runtime'])
                    with patch.object(os,'geteuid',return_value=0),patch.object(accounts,'ensure_user') as ensure,patch.object(setup,'install_config'),patch.object(setup.lifecycle,'install_wolfram',return_value='Fixture Wolfram'),contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(setup.apply(a,plan,h.snapshot(),h),0)
                    ensure.assert_any_call(plan['primary'],admin=True,passwordless=True)
                    for user in plan['additional']:ensure.assert_any_call(user,admin=True)
                    self.assertEqual(h.env['NTP_PRIMARY'],original['plan']['ntp'])
                    self.assertEqual(h.env['SSH_POLICY'],original['plan']['ssh'])

    def test_original_policy_files_untouched_by_export(self):
        paths=[setup.HERE/name for name in ('account-policy.sh','rpi_accounts.py','pre_aalto.sh','pre_home.sh','pre_profile.sh')]
        before={p:p.read_bytes() for p in paths}
        for base in ('GENERAL','HOME','AALTO'):profiles.builtin(base)
        self.assertEqual(before,{p:p.read_bytes() for p in paths})


class ValidationTests(unittest.TestCase):
    def setUp(self):self.data=profiles.builtin('GENERAL')
    def invalid(self,data):
        with self.assertRaises((ValueError,TypeError)):profiles.validate(data)
    def test_unknown_fields_and_credentials_rejected_at_all_levels(self):
        for location in ((),('settings',),('settings','components'),('settings','share'),('settings','imaging')):
            for key in ('unexpected','password','token','private_key','password_hash','yes','recovery','imaging_approved','replace_share_config','apt_upgrade','update_existing'):
                d=copy.deepcopy(self.data);target=d
                for step in location:target=target[step]
                target[key]='secret';self.invalid(d)
    def test_missing_fields_rejected_at_all_levels(self):
        for path,_ in builder.leaves(self.data):
            d=copy.deepcopy(self.data);target=d
            for step in path[:-1]:target=target[step]
            del target[path[-1]];self.invalid(d)
    def test_invalid_types_and_values(self):
        cases=[('version',True),('version','1'),('version',2),('base','OTHER'),('name',''),('settings.primary_user','root'),('settings.additional_users',['alice','alice']),('settings.hostname','bad host'),('settings.ssh','yes'),('settings.ntp_servers',[]),('settings.ntp_servers',['-x']),('settings.ntp_servers',['time.example.invalid..']),('settings.ntp_servers',['a;touch']),('settings.ntp_servers',['2001:db8::1%eth0']),('settings.components.hardware',1),('settings.lab_prefix','relative'),('settings.ide_prefix','/opt/lab314/sub'),('settings.share.source','remote'),('settings.share.path','/tmp/example'),('settings.share.users','alice'),('settings.imaging.apps',[False])]
        for path,value in cases:
            with self.subTest(path=path,value=value):
                d=copy.deepcopy(self.data);steps=path.split('.');target=d
                for step in steps[:-1]:target=target[step]
                target[steps[-1]]=value;self.invalid(d)
    def test_ntp_hostnames_ipv4_ipv6(self):
        for value in ('time.example.invalid','192.0.2.1','2001:db8::1'):
            self.assertEqual(profiles.ntp_server(value),value)
    def test_disallowed_component_combinations(self):
        d=profiles.builtin('HOME');d['settings']['components']['share']=False;self.invalid(d)
        d=copy.deepcopy(self.data);d['settings']['share']['source']='json';self.invalid(d)
        d=copy.deepcopy(self.data);d['settings']['share']['default_group']='staff';self.invalid(d)
    def test_malformed_json_duplicate_keys_nonfinite_and_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json'
            for text in ('{','{"version":1,"version":1}',json.dumps(self.data).replace('"version": 1','"version": NaN')):
                p.write_text(text)
                with self.assertRaises(ValueError):profiles.load(p)
            p.write_text('\ufeff'+json.dumps(self.data));self.assertEqual(profiles.load(p),self.data)
    def test_repeated_roundtrips_stable_and_no_credential_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            for base in ('GENERAL','HOME','AALTO'):
                data=profiles.builtin(base);original=copy.deepcopy(data);bytes_before=None
                for i in range(5):
                    p=Path(tmp)/f'{base}-{i}.json';profiles.save(p,data);data=profiles.load(p)
                    self.assertEqual(original,data)
                    if bytes_before:self.assertEqual(p.read_bytes(),bytes_before)
                    bytes_before=p.read_bytes()
                self.assertNotIn('password',json.dumps(data));self.assertNotIn('token',json.dumps(data))
    def test_safe_existing_output_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'profile.json';profiles.save(p,self.data);original=p.read_bytes()
            with self.assertRaises(FileExistsError):profiles.save(p,profiles.builtin('HOME'))
            self.assertEqual(p.read_bytes(),original);self.assertEqual(p.stat().st_mode & 0o777,0o600)
            profiles.save(p,profiles.builtin('HOME'),True);self.assertEqual(profiles.load(p)['base'],'HOME')
            link=Path(tmp)/'link';link.symlink_to(p)
            with self.assertRaises(ValueError):profiles.save(link,self.data,True)
    def test_invalid_profile_fails_before_host_probe(self):
        h=FakeHost()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad';p.write_text('{}')
            with patch.object(h,'snapshot',side_effect=AssertionError('no probe')),self.assertRaises(ValueError):setup.main(['--profile-file',str(p),'--plan'],h)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'profile.json';self.data=profiles.builtin('GENERAL')
    def parse(self,*argv):
        profiles.save(self.path,self.data,replace=self.path.exists())
        return profiles.parse_arguments(setup.parser(),['--profile-file',str(self.path),*argv])
    def test_aalto_profile_file_matches_cli_for_every_invoker(self):
        self.data=profiles.builtin('AALTO')
        for invoker in ('chem','alice',None):
            with self.subTest(invoker=invoker):
                h=FakeHost(invoker);a=self.parse('--plan');p=setup.resolve(a,h.snapshot(),h)
                direct=setup.parser().parse_args(['--profile','AALTO','--plan']);expected=setup.resolve(direct,h.snapshot(),h)
                self.assertEqual(norm(p),norm(expected));self.assertEqual(p['school'],'CHEM');self.assertEqual(p['primary'],'chem');self.assertEqual(p['additional'],['chem-it'])
                self.assertEqual(h.calls,[])

    def test_aalto_builder_preview_includes_required_account_without_mutation(self):
        self.data=profiles.builtin('AALTO')
        self.data['settings']['additional_users']=['admin2'];before=copy.deepcopy(self.data)
        for invoker in ('chem','alice',None):
            h=FakeHost(invoker)
            with contextlib.redirect_stdout(io.StringIO()):p=builder.preview(self.data,h)
            self.assertEqual(p['additional'],['chem-it','admin2']);self.assertEqual(p['primary'],'chem');self.assertEqual(p['school'],'CHEM');self.assertEqual(h.calls,[])
        self.assertEqual(self.data,before)

    def test_aalto_profile_file_empty_accounts_rejected_by_shared_policy(self):
        self.data=profiles.builtin('AALTO');self.data['settings']['additional_users']=[]
        with self.assertRaisesRegex(ValueError,'maintenance'):profiles.validate(self.data)
        # An existing administrator-edited file must also fail before host probing.
        self.path.write_text(json.dumps(self.data));h=FakeHost()
        with patch.object(h,'snapshot',side_effect=AssertionError('invalid file must fail before snapshot')),self.assertRaisesRegex(ValueError,'maintenance'):
            setup.main(['--profile-file',str(self.path),'--yes'],h)

    def test_aalto_file_optional_accounts_and_primary_override_preserved(self):
        self.data=profiles.builtin('AALTO');s=self.data['settings'];s['primary_user']='alice';s['additional_users']=['admin2','chem-it']
        a=self.parse('--plan');h=FakeHost();p=setup.resolve(a,h.snapshot(),h)
        self.assertEqual((p['primary'],p['additional']),('alice',['chem-it','admin2']))
        for extra in (['--school','custom'],['--no-additional-users']):
            a=self.parse('--plan',*extra)
            with self.assertRaises(ValueError):setup.resolve(a,h.snapshot(),h)
        self.assertEqual(h.calls,[])

    def test_all_supported_settings_flow_into_effective_plan(self):
        s=self.data['settings'];s.update(primary_user='alice',additional_users=['admin2'],hostname='rpi-custom',ssh='disable',ntp_servers=['192.0.2.1','time.example.invalid'],lab_prefix='/opt/research-python',ide_prefix='/opt/example-ide')
        s['components'].update(hardware=True,wolfram=True,share=True,imaging=True)
        s['share'].update(source='example',users=['alice','admin2'],prefix='/opt/share-tools',default_group='students')
        s['imaging'].update(source='/opt/reviewed/imaging',apps=['cam-preview'])
        a=self.parse('--plan','--recovery','create');h=FakeHost();p=setup.resolve(a,h.snapshot(),h)
        self.assertEqual((p['primary'],p['additional'],p['hostname'],p['ssh']),('alice',['admin2'],'rpi-custom','disable'))
        self.assertEqual(p['ntp'],'192.0.2.1 time.example.invalid');self.assertTrue(all(p['components'].values()))
        self.assertEqual(p['owners'],['alice','admin2']);self.assertEqual(p['share_prefix'],Path('/opt/share-tools'));self.assertEqual(p['config']['defaults']['group'],'students')
        self.assertEqual((a.lab_prefix,a.ide_prefix),(Path('/opt/research-python'),Path('/opt/example-ide')))
        self.assertEqual((a.imaging_source,a.imaging_app),(Path('/opt/reviewed/imaging'),['cam-preview']))
        self.assertFalse(a.imaging_approved);self.assertFalse(a.yes);self.assertFalse(a.replace_share_config);self.assertFalse(a.update_existing);self.assertFalse(a.apt_upgrade)
    def test_json_and_csv_catalogs_selected_locally(self):
        for kind in ('json','csv'):
            self.data['settings']['components']['share']=True
            self.data['settings']['share'].update(source=kind,path=str(setup.BASE/f'config/rpi-share.example.{kind}'))
            a=self.parse('--plan');h=FakeHost();p=setup.resolve(a,h.snapshot(),h)
            self.assertIsNotNone(p['config']);self.assertEqual(h.calls,[])

    def test_profile_file_discovers_by_default_and_explicit_cli_json_overrides_it(self):
        self.data = profiles.builtin('HOME')
        root = self.path.parent
        discovered = root/'rpi-share.home.json'
        explicit = root/'reviewed.json'
        for path in (discovered, explicit):
            path.write_bytes((setup.BASE/'config/rpi-share.example.json').read_bytes())
        host = FakeHost()
        with contextlib.chdir(root):
            plan = setup.resolve(self.parse('--plan'), host.snapshot(), host)
        self.assertEqual(plan['config_path'], discovered)
        self.data['settings']['share'].update(source='json', path=str(discovered))
        with patch.object(setup, 'discover_share_catalogs', side_effect=AssertionError('explicit source')):
            plan = setup.resolve(self.parse('--plan', '--share-json', str(explicit)), host.snapshot(), host)
        self.assertEqual(plan['config_path'], explicit)
    def test_cli_overrides_scalars_booleans_repeats_and_share_group(self):
        s=self.data['settings'];s.update(additional_users=['fileadmin'],ssh='disable',ntp_servers=['file.example.invalid'])
        s['components'].update(hardware=True,share=True);s['share'].update(source='json',path='/nonexistent/catalog.json',users=['fileadmin']);s['imaging']['apps']=['file-app']
        a=self.parse('--profile=HOME','--ssh','enable','--ntp-server','cli.example.invalid','--additional-user','cliadmin','--no-hardware','--share-later','--share-user','alice','--imaging-app','cli-app','--plan')
        self.assertEqual(a.profile,'HOME');self.assertEqual(a.ssh,'enable');self.assertEqual(a.ntp_server,['cli.example.invalid']);self.assertEqual(a.additional_user,['cliadmin']);self.assertFalse(a.no_additional_users);self.assertFalse(a.hardware)
        self.assertIsNone(a.share_json);self.assertTrue(a.share_later);self.assertEqual(a.share_user,['alice']);self.assertEqual(a.imaging_app,['cli-app'])
        self.assertEqual(self.parse('--no-additional-users').additional_user,None)
    def test_exact_component_cli_keeps_file_source_and_application_options(self):
        self.data['settings']['components']['share']=True
        self.data['settings']['share'].update(source='example',default_group='students')
        self.data['settings']['imaging'].update(source='/opt/reviewed/imaging',apps=['cam-preview'])
        a=self.parse('--share','--imaging','--plan')
        self.assertTrue(a.share_example);self.assertEqual(a.default_group,'students')
        self.assertEqual(a.imaging_source,Path('/opt/reviewed/imaging'));self.assertEqual(a.imaging_app,['cam-preview'])
        h=FakeHost();self.assertIsNotNone(setup.resolve(a,h.snapshot(),h)['config'])
        a=self.parse('--share-later','--plan')
        self.assertIsNone(a.default_group);self.assertIsNone(setup.resolve(a,h.snapshot(),h)['config'])
    def test_legacy_cli_abbreviations_and_literal_option_like_values(self):
        self.data['settings']['hostname']='file-host'
        self.data['settings']['imaging']['apps']=['--yes']
        a=self.parse('--host=cli-host')
        self.assertEqual(a.hostname,'cli-host');self.assertEqual(a.imaging_app,['--yes']);self.assertFalse(a.yes)
    def test_explicit_cli_additional_replaces_file_none_choice(self):
        self.data['settings']['additional_users']=[]
        a=self.parse('--additional-user','admin2');self.assertFalse(a.no_additional_users);self.assertEqual(a.additional_user,['admin2'])
    def test_missing_account_keeps_existing_recovery_safeguards(self):
        self.data['settings']['primary_user']='newuser';h=FakeHost()
        a=self.parse('--yes')
        with patch.object(sys.stdin,'isatty',return_value=False),self.assertRaisesRegex(ValueError,'recovery'):setup.resolve(a,h.snapshot(),h)
        a=self.parse('--yes','--recovery','create')
        with patch.object(sys.stdin,'isatty',return_value=False),self.assertRaisesRegex(ValueError,'password'):setup.resolve(a,h.snapshot(),h)
        self.assertEqual(h.calls,[])
    def test_preview_and_plan_never_apply_or_run_commands(self):
        self.data['settings']['primary_user']='newuser';h=FakeHost()
        with patch.object(setup,'apply',side_effect=AssertionError('no apply')),contextlib.redirect_stdout(io.StringIO()):
            builder.preview(self.data,h)
            profiles.save(self.path,self.data)
            self.assertEqual(setup.main(['--profile-file',str(self.path),'--plan','--recovery','create'],h),0)
        self.assertEqual(h.calls,[]);self.assertIsNone(profiles.load(self.path)['settings']['additional_users'])
    def test_menu_create_edit_validate_preview_save_load(self):
        # First edit is the display name; preview stays inside the mocked boundary.
        answers=['1','GENERAL','3','1','Research workstation','4','5','6',str(self.path),'2',str(self.path),'0']
        with patch('builtins.input',side_effect=answers),patch.object(builder.setup,'Host',return_value=FakeHost()),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(builder.menu(),0)
        self.assertEqual(profiles.load(self.path)['name'],'Research workstation')
    def test_menu_can_select_json_csv_and_clear_source_path(self):
        self.data['settings']['components']['share']=True
        rows=[(('name',),self.data['name']),(('base',),self.data['base'])]+list(builder.leaves(self.data['settings'],('settings',)))
        index=next(i for i,(path,_) in enumerate(rows,1) if path==('settings','share','source'))
        for kind in ('json','csv','later','example'):
            answers=[str(index),kind]+(['/tmp/catalog.'+kind] if kind in ('json','csv') else [])
            with patch('builtins.input',side_effect=answers),contextlib.redirect_stdout(io.StringIO()):self.data=builder.edit(self.data)
            self.assertEqual(self.data['settings']['share']['source'],kind)
            self.assertEqual(self.data['settings']['share']['path'],'/tmp/catalog.'+kind if kind in ('json','csv') else None)
    def test_custom_ntp_reaches_existing_profile_policy(self):
        self.data['settings']['ntp_servers']=['192.0.2.1','2001:db8::1','time.example.invalid']
        a=self.parse('--plan');h=FakeHost();plan=setup.resolve(a,h.snapshot(),h)
        with patch.object(os,'geteuid',return_value=0),patch.object(accounts,'ensure_user'),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(setup.apply(a,plan,h.snapshot(),h),0)
        self.assertEqual(h.env['NTP_PRIMARY'],'192.0.2.1 2001:db8::1 time.example.invalid')
        self.assertTrue(any('pre_profile.sh' in ' '.join(call) for call in h.calls))
    def test_cli_export_validate_and_setup_plan_offline(self):
        result=subprocess.run([sys.executable,'-B',str(setup.HERE/'profile-builder.py'),'--export','GENERAL','--output',str(self.path)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run([sys.executable,'-B',str(setup.HERE/'profile-builder.py'),'--validate',str(self.path)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('VALID',result.stdout)
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(setup.main(['--profile-file',str(self.path),'--plan'],FakeHost()),0)


if __name__=='__main__':unittest.main()
