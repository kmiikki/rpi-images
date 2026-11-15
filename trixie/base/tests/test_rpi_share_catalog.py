"""Entirely offline catalog, interchange, hierarchy and existing-client tests."""
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'bin'))
import rpi_share_catalog as c


def equal_typed(test,a,b):
    test.assertIs(type(a),type(b))
    if isinstance(a,dict):
        test.assertEqual(set(a),set(b))
        for key in a:equal_typed(test,a[key],b[key])
    elif isinstance(a,list):
        test.assertEqual(len(a),len(b))
        for x,y in zip(a,b):equal_typed(test,x,y)
    else:test.assertEqual(a,b)


def example():return c.loads((BASE/'config/rpi-share.example.json').read_text())


class RoundTripTests(unittest.TestCase):
    def test_home_roundtrip_and_source_unchanged(self):
        self.original('home',str)

    def test_aalto_roundtrip_and_source_unchanged(self):
        self.original('aalto',int)

    def original(self,name,version_type):
        source=BASE/('config/rpi-share.'+name+'.json');before=source.read_bytes()
        original=c.validate(c.loads(before.decode()));self.assertIs(type(original['version']),version_type)
        with tempfile.TemporaryDirectory() as tmp:
            csv_path=Path(tmp)/(name+'.csv');json_path=Path(tmp)/(name+'.roundtrip.json')
            c.atomic_write(csv_path,c.export_csv(original))
            restored=c.validate(c.import_csv(csv_path.read_text()))
            c.atomic_write(json_path,json.dumps(restored,ensure_ascii=False))
            equal_typed(self,original,c.loads(json_path.read_text()))
        self.assertEqual(before,source.read_bytes())

    def test_all_json_types_optional_fields_and_pointer_escaping(self):
        cfg=example();cfg['unknown optional']={'a/b~c':[None,True,False,0,1,-2,1.0,1.125,'','00123','=SUM(A1)','Åä漢字; "quote",\nline',{},[]], 'absent-distinct':{'empty':''}}
        equal_typed(self,cfg,c.import_csv(c.export_csv(cfg)))

    def test_csv_json_csv_deterministic(self):
        text=(BASE/'config/rpi-share.example.csv').read_text()
        config=c.validate(c.import_csv(text))
        self.assertEqual(text,c.export_csv(config))

    def test_repeated_roundtrips_no_drift(self):
        original=example();current=original
        for _ in range(10):current=c.validate(c.import_csv(c.export_csv(c.loads(json.dumps(current)))))
        equal_typed(self,original,current)

    def test_calc_semicolon_bom_crlf_and_all_fields_quoted(self):
        original=example();original['unknown']={'quote':'comma, semi; "quoted" Å','number-looking':'000001','empty':'','float':1.0}
        source=csv.reader(io.StringIO(c.export_csv(original)))
        stream=io.StringIO(newline='');writer=csv.writer(stream,delimiter=';',quoting=csv.QUOTE_ALL,lineterminator='\r\n')
        writer.writerows(source)
        equal_typed(self,original,c.import_csv('\ufeff'+stream.getvalue()))

    def test_no_network_or_subprocess_during_conversion(self):
        with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')),patch.object(subprocess,'run',side_effect=AssertionError('subprocess forbidden')):
            c.validate(c.import_csv(c.export_csv(example())))

    def test_empty_vs_absent(self):
        cfg=example();cfg['shares']['browse']['empty']=''
        restored=c.import_csv(c.export_csv(cfg))
        self.assertEqual(restored['shares']['browse']['empty'],'')
        self.assertNotIn('absent',restored['shares']['browse'])

    def test_array_order_and_numeric_types(self):
        cfg=example();cfg['values']=[float(i) if i%2 else i for i in range(14)]
        equal_typed(self,cfg,c.import_csv(c.export_csv(cfg)))

    def test_unknown_fields_are_preserved(self):
        cfg=example();cfg['gateways']['staff-gw']['vendor-options']={'mode':None,'weight':1.5}
        equal_typed(self,cfg,c.validate(c.import_csv(c.export_csv(cfg))))

    def test_nullable_optional_fields_preserved_without_default_insertion(self):
        cfg=example();share=cfg['shares']['browse']
        share.update(description=None,name='',explicit_only=None,allowed_groups=None,groups=None,remote_path=None,paths=None)
        cfg['gateways']['staff-gw']['default_user']=None
        equal_typed(self,cfg,c.validate(c.import_csv(c.export_csv(cfg))))


class ValidationTests(unittest.TestCase):
    def test_cycles(self):
        cfg=example();cfg['nodes']['research']['parent']='measurements'
        with self.assertRaisesRegex(c.Invalid,'cycle'):c.validate(cfg)

    def test_bad_parent(self):
        cfg=example();cfg['shares']['measurements']['parent']='missing'
        with self.assertRaisesRegex(c.Invalid,'parent'):c.validate(cfg)
        cfg=example();cfg['nodes']={'early':{'parent':'later'},'later':{'parent':'missing'}}
        with self.assertRaisesRegex(c.Invalid,'parent'):c.validate(cfg)

    def test_duplicate_node_and_share_id(self):
        cfg=example();cfg['nodes']['browse']={}
        with self.assertRaisesRegex(c.Invalid,'distinct'):c.validate(cfg)

    def test_unknown_gateway_path(self):
        cfg=example();cfg['shares']['measurements']['paths']['missing']='/x'
        with self.assertRaisesRegex(c.Invalid,'gateway'):c.validate(cfg)

    def test_invalid_fields(self):
        changes=[('version',True),('version',3),('shares',[]),('gateways',{})]
        for key,value in changes:
            cfg=example();cfg[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(c.Invalid):c.validate(cfg)

    def test_default_references(self):
        for key in ('gateway','share','group'):
            cfg=example();cfg['defaults'][key]='missing'
            with self.subTest(key=key),self.assertRaises(c.Invalid):c.validate(cfg)

    def test_unsupported_mount_type_and_bad_identifier(self):
        cfg=example();cfg['shares']['browse']['mount_type']='ftp'
        with self.assertRaises(c.Invalid):c.validate(cfg)
        cfg=example();cfg['shares']['../escape']=cfg['shares'].pop('browse')
        with self.assertRaises(c.Invalid):c.validate(cfg)

    def test_credentials_rejected_without_silent_loss(self):
        for field in ('password','password_hash','token','credentials','private_key'):
            cfg=example();cfg['optional']={field:'example-for-rejection'}
            with self.subTest(field=field),self.assertRaisesRegex(c.Invalid,'credential'):c.validate(cfg)

    def test_credential_options_and_urls_rejected(self):
        for option in ('password=bad','iocharset=utf8,credentials=/tmp/credential','user=someone','prefixpath=escape'):
            cfg=example();cfg['shares']['smb-measurements']['cifs_options']=option
            with self.subTest(option=option),self.assertRaises(c.Invalid):c.validate(cfg)
        cfg=example();cfg['shares']['browse']['browse_url']='smb://user:password@example.invalid/share'
        with self.assertRaises(c.Invalid):c.validate(cfg)

    def test_non_finite_rejected(self):
        with self.assertRaises(c.Invalid):c.loads('{"x":NaN}')
        cfg=example();cfg['x']=float('inf')
        with self.assertRaises(c.Invalid):c.validate(cfg)

    def test_duplicate_json_keys(self):
        with self.assertRaisesRegex(c.Invalid,'duplicate'):c.loads('{"x":1,"x":2}')

    def test_malformed_csv(self):
        samples=['','other,value\n,x\n','path,json_value\n,{}\n/x,1\n/x,2\n','path,json_value\n,{}\n/x/y,1\n','path,json_value\n,{}\n/x,1\n/x/y,2\n','path,json_value\n,[]\n/2,1\n','path,json_value\n,{}\n/bad~2,1\n','path,json_value\n,{}\n/x,"unterminated']
        for text in samples:
            with self.subTest(text=text),self.assertRaises((c.Invalid,json.JSONDecodeError,csv.Error)):c.import_csv(text)

    def test_malformed_json_cell(self):
        with self.assertRaises(ValueError):c.import_csv('path,json_value\n,{}\n/x,not-json\n')

    def test_arbitrary_row_order(self):
        lines=list(csv.reader(io.StringIO(c.export_csv(example()))));s=io.StringIO();writer=csv.writer(s);writer.writerow(lines[0]);writer.writerows(reversed(lines[1:]))
        equal_typed(self,example(),c.import_csv(s.getvalue()))


class NavigationTests(unittest.TestCase):
    def test_full_tree_displays_explicit_and_all_groups(self):
        cfg=example();lines=c.tree_lines(cfg,{'students'},full=True)
        self.assertTrue(any('maintenance' in line for line in lines))
        self.assertTrue(any('smb-measurements' in line for line in lines))

    def test_visible_child_under_filtered_parent(self):
        cfg=example();cfg['nodes']['project']['groups']=['staff']
        lines=c.tree_lines(cfg,{'students'})
        self.assertTrue(any('project' in line for line in lines));self.assertTrue(any('measurements' in line for line in lines))
        self.assertFalse(any('maintenance' in line for line in lines))

    def test_primary_and_additional_groups(self):
        cfg=example();self.assertEqual(c.selected_groups(cfg,[]),{'staff','research-a'})
        self.assertEqual(c.selected_groups(cfg,['students','project-x']),{'students','project-x'})

    def test_unknown_group(self):
        with self.assertRaises(c.Invalid):c.selected_groups(example(),['unknown'])

    def test_gateway_groups_not_authorization(self):
        cfg=example()
        # A students navigation selection never pretends to enforce gateway ACLs.
        self.assertEqual(c.mapping(cfg,'staff-gw','measurements')['type'],'sshfs')
        c.validate(cfg)

    def test_sshfs_gateway_specific_deep_path(self):
        cfg=example()
        self.assertIn('/srv/student/',c.mapping(cfg,'student-gw','measurements')['remote'])
        self.assertIn('Project X/Measurements',c.mapping(cfg,'staff-gw','measurements')['path'])

    def test_cifs_share_root_and_prefixpath(self):
        m=c.mapping(example(),'staff-gw','smb-measurements')
        self.assertEqual(m['remote'],'//staff-gateway.example.invalid/Research')
        self.assertIn('prefixpath=Project X/Measurements',m['options'])

    def test_explicit_cifs_fields(self):
        cfg=example();cfg['shares']['smb-measurements'].pop('remote_path')
        cfg['shares']['smb-measurements'].update(share_root='Research',subdir='Project X/Measurements')
        self.assertIn('prefixpath=Project X/Measurements',c.mapping(c.validate(cfg),'staff-gw','smb-measurements')['options'])

    def test_legacy_cifs_prefixpath_option_is_preserved(self):
        cfg=c.loads((BASE/'config/rpi-share.home.json').read_text())
        cfg['shares']['code']['cifs_options']+=',prefixpath=Project X'
        equal_typed(self,cfg,c.validate(c.import_csv(c.export_csv(cfg))))
        self.assertIn('prefixpath=Project X',c.mapping(cfg,'nasse','code')['options'])

    def test_conflicting_cifs_definitions_rejected(self):
        cfg=example();cfg['shares']['smb-measurements']['share_root']='Other'
        with self.assertRaisesRegex(c.Invalid,'conflicting'):c.validate(cfg)

    def test_browse_url_and_derived_url_escaping(self):
        cfg=example();self.assertEqual(c.mapping(cfg,'staff-gw','browse')['remote'],cfg['shares']['browse']['browse_url'])
        cfg['shares']['browse'].pop('browse_url');cfg['shares']['browse']['remote_path']='/Research/Project X'
        self.assertIn('Project%20X',c.mapping(cfg,'staff-gw','browse')['remote'])

    def test_missing_gateway_destination_is_not_invented(self):
        cfg=example();del cfg['shares']['measurements']['paths']['student-gw']
        with self.assertRaises(c.Invalid):c.mapping(cfg,'student-gw','measurements')


class FileAndClientTests(unittest.TestCase):
    def test_safe_overwrite_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config.json';c.atomic_write(path,'old')
            with self.assertRaises(c.Invalid):c.atomic_write(path,'new')
            self.assertEqual(path.read_text(),'old');c.atomic_write(path,'new',True)
            self.assertEqual(path.read_text(),'new');self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_replacement_failure_retains_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config.json';path.write_text('old')
            with patch.object(os,'replace',side_effect=OSError('injected failure')),self.assertRaises(OSError):c.atomic_write(path,'new',True)
            self.assertEqual(path.read_text(),'old');self.assertEqual(list(Path(tmp).iterdir()),[path])

    def test_symlink_output_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            original=Path(tmp)/'original';original.write_text('keep');link=Path(tmp)/'link';link.symlink_to(original)
            with self.assertRaises(c.Invalid):c.atomic_write(link,'replace',True)
            self.assertEqual(original.read_text(),'keep')

    def test_builder_cli_both_directions_and_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=BASE/'config/rpi-share.home.json';csv_path=Path(tmp)/'catalog.csv';destination=Path(tmp)/'catalog.json'
            command=[sys.executable,'-B',str(BASE/'bin/rpi-share-builder.py')]
            subprocess.run(command+['--json',str(source),'--output',str(csv_path)],check=True,capture_output=True)
            subprocess.run(command+['--csv',str(csv_path),'--output',str(destination)],check=True,capture_output=True)
            equal_typed(self,c.loads(source.read_text()),c.loads(destination.read_text()))
            before=destination.read_bytes()
            subprocess.run(command+['--csv',str(csv_path),'--output',str(destination),'--plan'],check=True,capture_output=True)
            self.assertEqual(before,destination.read_bytes())
            result=subprocess.run(command+['--csv',str(csv_path),'--output',str(destination)],capture_output=True)
            self.assertNotEqual(result.returncode,0);self.assertEqual(before,destination.read_bytes())

    def test_generation_failure_keeps_valid_configuration_even_with_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config.json';before=json.dumps(example());path.write_text(before)
            bad=Path(tmp)/'bad.csv';bad.write_text('path,json_value\n,{}\n/version,not-json\n')
            result=subprocess.run([sys.executable,'-B',str(BASE/'bin/rpi-share-builder.py'),'--csv',str(bad),'--output',str(path),'--force'],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertEqual(path.read_text(),before)
            self.assertNotIn('Traceback',result.stderr)

    def test_configuration_precedence_with_temporary_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);scriptdir=root/'bin';scriptdir.mkdir();user=root/'user';user.mkdir();system=root/'system';system.mkdir();current=root/'current';current.mkdir()
            text=(BASE/'bin/rpi-share').read_text().replace('$HOME/.config',str(user)).replace('/etc/rpi-share',str(system))
            source=scriptdir/'rpi-share';source.write_text(text)
            files=[current/'rpi-share.json',user/'rpi-share.json',system/'rpi-share.json',scriptdir/'rpi-share.json']
            for f in files:f.write_text('{}')
            def resolve(explicit=''):
                r=subprocess.run(['bash','-c','source "$1"; CONFIG_FILE=$2; resolve_config','test',str(source),explicit],cwd=current,check=True,capture_output=True,text=True)
                return r.stdout.strip()
            self.assertEqual(resolve(str(files[-1])),str(files[-1]))
            for f in files:
                self.assertEqual(resolve(),str(f));f.unlink()

    def client(self,*args,input_text=None):
        return subprocess.run(['bash',str(BASE/'bin/rpi-share'),*args],input=input_text,capture_output=True,text=True,check=True)

    def test_existing_v1_list_all_admin_semantics(self):
        path=str(BASE/'config/rpi-share.aalto.json')
        normal=self.client('--config',path,'--list').stdout
        all_entries=self.client('--config',path,'--list','--all').stdout
        admin=self.client('--config',path,'--list','--admin').stdout
        self.assertNotIn('teamwork-chem-scratch',normal)
        self.assertIn('teamwork-chem-scratch',all_entries);self.assertEqual(all_entries,admin)

    def test_existing_home_v1_list(self):
        self.assertIn('Code',self.client('--config',str(BASE/'config/rpi-share.home.json'),'--list').stdout)

    def test_tree_runs_without_mount_or_network_tools(self):
        result=self.client('--config',str(BASE/'config/rpi-share.example.json'),'--tree','--group','students')
        self.assertIn('measurements',result.stdout);self.assertNotIn('maintenance —',result.stdout)
        self.assertIn('maintenance',self.client('--config',str(BASE/'config/rpi-share.example.json'),'--tree-all').stdout)

    def test_software_install_to_temporary_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix=Path(tmp)/'local'
            subprocess.run(['bash',str(BASE/'install/install_rpi_share.sh'),'--prefix',str(prefix)],check=True,capture_output=True)
            result=subprocess.run(['bash',str(prefix/'bin/rpi-share'),'--config',str(BASE/'config/rpi-share.example.json'),'--tree-all'],check=True,capture_output=True,text=True)
            self.assertIn('measurements',result.stdout)
            self.assertTrue((prefix/'bin/rpi-share-builder.py').exists())
            self.assertFalse((prefix/'share/rpi-share/rpi-share.json').exists())

    def test_software_install_plan_has_no_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix=Path(tmp)/'local'
            subprocess.run(['bash',str(BASE/'install/install_rpi_share.sh'),'--prefix',str(prefix),'--plan'],check=True,capture_output=True)
            self.assertFalse(prefix.exists())


if __name__=='__main__':unittest.main()
