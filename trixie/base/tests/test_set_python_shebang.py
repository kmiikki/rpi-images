"""Offline standard-library tests. Every mutable fixture is a private /tmp copy."""
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
import venv

TOOL = Path(__file__).resolve().parents[1]/'tools/set-python-shebang.py'
spec = importlib.util.spec_from_file_location('set_python_shebang', TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
PORT = tool.PORTABLE
SYSTEM = '#!/usr/bin/python3'
BODY = b'# coding: latin-1\nprint("caf\xe9")\n'


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir='/tmp')
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.target = self.base/'installed'
        self.target.mkdir()
        self.target.chmod(0o755)
        self.path = self.target/'sample.py'
        self.write()
        self.envs = {}
        for env in tool.ENVS:
            if env in ('system','portable'):
                binary = Path('/usr/bin/python3')
            else:
                binary = self.base/env/'bin/python'
                binary.parent.mkdir(parents=True)
                binary.symlink_to('/usr/bin/python3')
            self.envs[env] = dict(path=str(binary), version='3.12', modules={},
                                  prefix=str(binary.parent.parent))
        self.scan = patch.object(tool, 'discover', side_effect=self.inventory).start()
        self.addCleanup(patch.stopall)

    def inventory(self, names):
        return self.envs, {}, {}, []

    def write(self, line=PORT, body=BODY, sep=b'\n'):
        self.path.write_bytes(line.encode()+sep+body)
        self.path.chmod(0o751)

    def run_cli(self, *args):
        self.out = io.StringIO()
        with contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.out):
            try:
                return tool.main(list(map(str,args)))
            except SystemExit as exc:
                return exc.code

    def edit(self, env, answer='y', *more):
        with patch('sys.stdin.isatty', return_value=True), patch('builtins.input', return_value=answer):
            return self.run_cli('--target',self.target,'--apply','--env',env,self.path,*more)

    def test_portable_hardware(self):
        self.write(body=b'import picamera2\n')
        self.envs['rpi']['modules']['picamera2'] = True
        self.assertEqual(self.run_cli('--analyze',self.path),0)
        self.assertIn('CHANGE rpi', self.out.getvalue())
        # Use real ordinary entry point after approving the plan.
        self.write(body=b'print(42)\n')
        self.assertEqual(self.edit('rpi'),0)
        self.assertEqual(subprocess.check_output([self.path]), b'42\n')

    def test_portable_system(self):
        self.assertEqual(self.edit('system'),0)
        self.assertEqual(self.path.read_bytes(),SYSTEM.encode()+b'\n'+BODY)

    def test_portable_lab314(self):
        self.assertEqual(self.edit('lab314'),0)
        self.assertIn(b'/lab314/bin/python\n',self.path.read_bytes())

    def test_rpi_portable(self):
        self.write('#!'+self.envs['rpi']['path'])
        self.assertEqual(self.edit('portable'),0)
        self.assertEqual(self.path.read_bytes(),PORT.encode()+b'\n'+BODY)

    def test_system_portable(self):
        self.write(SYSTEM)
        self.assertEqual(self.edit('portable'),0)
        self.assertTrue(self.path.read_bytes().startswith(PORT.encode()))

    def test_portable_analysis_keep(self):
        self.write(body=b'import numpy\n')
        self.envs['portable']['modules']['numpy'] = True
        before=self.path.stat()
        self.assertEqual(self.run_cli('--check',self.path),0)
        self.assertIn('KEEP portable',self.out.getvalue())
        self.assertEqual(tool.identity(before),tool.identity(self.path.stat()))

    def test_latin1_metadata_and_mode(self):
        before=self.path.stat()
        os.setxattr(self.path,'user.note',b'test')
        self.assertEqual(self.edit('system'),0)
        after=self.path.stat()
        self.assertEqual(before.st_mode,after.st_mode)
        self.assertEqual((before.st_uid,before.st_gid),(after.st_uid,after.st_gid))
        self.assertEqual(before.st_mtime_ns,after.st_mtime_ns)
        self.assertEqual(os.getxattr(self.path,'user.note'),b'test')
        self.assertEqual(self.path.read_bytes().split(b'\n',1)[1],BODY)

    def test_crlf(self):
        self.write(body=b'pass\r\n# end',sep=b'\r\n')
        self.assertEqual(self.edit('system'),0)
        self.assertEqual(self.path.read_bytes(), SYSTEM.encode()+b'\r\npass\r\n# end')

    def test_no_final_newline(self):
        self.write(body=b'',sep=b'')
        self.assertEqual(self.edit('system'),0)
        self.assertEqual(self.path.read_bytes(),SYSTEM.encode())

    def reject(self):
        before=self.path.read_bytes()
        self.assertEqual(self.edit('system'),2,self.out.getvalue())
        self.assertEqual(self.path.read_bytes(),before)

    def test_unknown(self):
        self.write('#!/usr/bin/env -S python3 -O')
        self.reject()

    def test_missing(self):
        self.path.write_bytes(b'print(42)')
        self.reject()

    def test_empty(self):
        self.path.write_bytes(b'')
        self.reject()

    def test_non_python(self):
        self.write('#!/bin/bash',b'echo hello')
        self.reject()

    def test_non_executable(self):
        self.path.chmod(0o644)
        self.reject()

    def test_link(self):
        orig=self.path.rename(self.base/'source')
        self.path.symlink_to(orig)
        self.reject()

    def test_hardlink(self):
        os.link(self.path,self.base/'second')
        self.reject()

    def test_readonly(self):
        self.path.chmod(0o555)
        self.reject()

    def test_insecure_directory(self):
        self.target.chmod(0o777)
        self.reject()

    def test_checkout_target(self):
        (self.base/'.git').touch()
        self.reject()

    def test_no_recursion(self):
        sub=self.target/'helpers';sub.mkdir(mode=0o755)
        self.path=self.path.rename(sub/self.path.name)
        before=self.path.read_bytes()
        self.assertEqual(self.edit('system','y',sub),2)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.edit('system'),0)

    def test_refusal(self):
        before=self.path.stat()
        self.assertEqual(self.edit('system','N'),1)
        self.assertEqual(tool.identity(before),tool.identity(self.path.stat()))

    def test_default_no(self):
        self.assertEqual(self.edit('system',''),1)
        self.assertTrue(self.path.read_bytes().startswith(PORT.encode()))

    def test_interrupt(self):
        with patch('sys.stdin.isatty',return_value=True), patch('builtins.input',side_effect=KeyboardInterrupt):
            self.assertEqual(self.run_cli('--apply','--target',self.target,'--env','system',self.path),130)
        self.assertTrue(self.path.read_bytes().startswith(PORT.encode()))

    def test_piped_approval_rejected(self):
        with patch('sys.stdin',io.StringIO('y\n')):
            self.assertEqual(self.run_cli('--apply','--env','system','--target',self.target,self.path),2)

    def test_batch_approval(self):
        other=self.target/'other';other.write_bytes(self.path.read_bytes());other.chmod(0o755)
        with patch('sys.stdin.isatty',return_value=True),patch('builtins.input',return_value='y') as ask:
            self.assertEqual(self.run_cli('--apply','--env','system','--target',self.target,self.path,other),0)
        ask.assert_called_once()
        self.assertEqual(other.read_bytes(),self.path.read_bytes())

    def test_dry_run_analysis_check(self):
        before=tool.digest(self.path.read_bytes())
        for mode,expected in [('--analyze',0),('--dry-run',0),('--check',1)]:
            self.assertEqual(self.run_cli(mode,'--env','system',self.path),expected)
            self.assertEqual(tool.digest(self.path.read_bytes()),before)

    def test_partial_write_failure(self):
        with patch.object(tool.os,'fsync',side_effect=OSError('disk full')):
            self.reject()
        self.assertEqual(list(self.target.iterdir()),[self.path])

    def test_rollback_between_files(self):
        other=self.target/'second';other.write_bytes(self.path.read_bytes());other.chmod(0o755)
        before=self.path.read_bytes()
        replace=os.replace
        def fail(src,dst,**kw):
            if dst==other.name:
                raise KeyboardInterrupt()
            replace(src,dst,**kw)
        with patch.object(tool.os,'replace',side_effect=fail):
            self.assertEqual(self.edit('system','y',other),130)
        self.assertEqual(other.read_bytes(),before)
        self.assertEqual(self.path.read_bytes(),before)

    def test_changed_after_approval(self):
        def change(_):
            self.path.write_bytes(b'#!/bin/sh\nexit\n')
            return 'y'
        with patch('sys.stdin.isatty',return_value=True),patch('builtins.input',side_effect=change):
            self.assertEqual(self.run_cli('--apply','--target',self.target,'--env','system',self.path),2)
        self.assertEqual(self.path.read_bytes(),b'#!/bin/sh\nexit\n')

    def rule(self):
        return dict(version=1,profile='fixture',target=str(self.target), files=[
            dict(path=self.path.name,env='system',**{'from':PORT,'to':SYSTEM},
                 sha256=tool.digest(self.path.read_bytes()))])

    def unattended(self, data, approved='fixture'):
        f=self.base/'plan.json'; f.write_text(json.dumps(data))
        args=['--non-interactive','--apply','--manifest',f,'--target',self.target]
        if approved:
            args+=['--approved-profile',approved]
        return self.run_cli(*args)

    def test_manifest_idempotent(self):
        rule=self.rule()
        self.assertEqual(self.unattended(rule),0)
        before=self.path.stat()
        self.assertEqual(self.unattended(rule),0)
        self.assertEqual(tool.identity(self.path.stat()),tool.identity(before))

    def test_manifest_mandatory(self):
        self.assertEqual(self.run_cli('--non-interactive','--apply','--env','system','--target',self.target,self.path),2)

    def test_manifest_requires_named_approval(self):
        for name in ('','other'):
            self.assertEqual(self.unattended(self.rule(),name),2)
        self.assertTrue(self.path.read_bytes().startswith(PORT.encode()))

    def test_manifest_exact_fields(self):
        for key in ('env','from','to','sha256'):
            r=self.rule();del r['files'][0][key]
            self.assertEqual(self.unattended(r),2)

    def test_manifest_stale(self):
        r=self.rule()
        self.write(body=b'print("changed")')
        self.assertEqual(self.unattended(r),2)

    def test_manifest_wrong_interpreter(self):
        r=self.rule()
        r['files'][0]['to']=PORT
        self.assertEqual(self.unattended(r),2)

    def test_manifest_escape(self):
        for path in ('../sample.py','/etc/hello.py'):
            r=self.rule();r['files'][0]['path']=path
            self.assertEqual(self.unattended(r),2)

    def test_symlink_directory_escape(self):
        folder=self.base/'escape';folder.mkdir()
        self.path.rename(folder/'sample.py')
        (self.target/'helpers').symlink_to(folder)
        self.path=self.target/'helpers/sample.py'
        self.reject()

    def test_missing_modules(self):
        self.write(body=b'import numpy, picamera2')
        self.envs['rpi']['modules']['picamera2']=True
        self.envs['system']['modules']['numpy']=True
        self.assertEqual(self.run_cli('--analyze',self.path),2)
        self.assertIn('AMBIGUOUS',self.out.getvalue())
        self.assertEqual(self.edit('rpi'),2)
        self.envs['rpi']['modules']['numpy']=True
        self.assertEqual(self.run_cli('--analyze',self.path),0)
        self.assertIn('CHANGE rpi',self.out.getvalue())

    def test_system_only_module(self):
        self.write(body=b'import apt_pkg')
        self.envs['system']['modules']['apt_pkg']=True
        self.assertEqual(self.run_cli('--analyze',self.path),0)
        self.assertIn('CHANGE system',self.out.getvalue())

    def test_ambiguous(self):
        self.write(body=b'import unknown')
        for env in ('lab314','rpi'):
            self.envs[env]['modules']['unknown']=True
        self.assertEqual(self.run_cli('--analyze',self.path),2)

    def test_dynamic(self):
        self.write(body=b'__import__(input())')
        self.assertEqual(self.run_cli('--analyze',self.path),2)

    def test_does_not_execute_selected_code(self):
        marker=self.base/'executed'
        self.write(body=f'open({str(marker)!r},"w").close()'.encode())
        self.assertEqual(self.run_cli('--analyze',self.path),0)
        self.assertFalse(marker.exists())


class Probes(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(dir='/tmp')
        self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name)
        self.opt=self.base/'opt';self.opt.mkdir()
        self.registry=self.base/'environments.txt'
        env=patch.dict(os.environ,{'PATH':'/usr/bin','CONDA_PREFIX':''})
        env.start(); self.addCleanup(env.stop)

    def scan(self,names=()):
        return tool.discover(names,self.opt,Path('/usr/bin'),self.registry)

    def env(self,name):
        p=self.opt/name
        venv.EnvBuilder(with_pip=False,symlinks=True).create(p)
        (p/'conda-meta').mkdir()
        return p

    def test_no_conda(self):
        envs,paths,registered,conflicts=self.scan()
        self.assertEqual(registered,{})
        self.assertFalse(conflicts)
        self.assertNotIn('error',envs['system'])
        self.assertIn('error',envs['rpi'])

    def test_python_only_fallback(self):
        p=self.env('rpi')
        (p/'bin/python3').unlink()
        (p/'bin/python').unlink()
        (p/'bin/python').symlink_to(sys.executable)
        envs,*_=self.scan()
        self.assertEqual(envs['rpi']['prefix'],str(p))
        self.assertEqual(envs['rpi']['path'],str(p/'bin/python'))

    def test_both_discovered(self):
        for name in ('lab314','rpi'):
            self.env(name)
        envs,_,registered,_=self.scan()
        self.assertEqual(set(registered),{str(self.opt/n) for n in ('rpi','lab314')})
        self.assertTrue(envs['lab314']['version'].startswith('3.'))

    def test_missing_binary(self):
        (self.opt/'lab314/bin').mkdir(parents=True)
        self.assertIn('error',self.scan()[0]['lab314'])

    def test_path_mismatch(self):
        path=self.env('lab314')
        with patch.dict(os.environ,{'CONDA_PREFIX':str(path)}):
            self.assertTrue(self.scan()[3])

    def test_distinct_versions(self):
        self.env('rpi')
        real=tool.probe
        def versions(exe,names):
            d=real(exe,names)
            if d.get('prefix')==str(self.opt/'rpi'):
                d['version']='3.13.13'
            return d
        with patch.object(tool,'probe',side_effect=versions):
            envs,*_=self.scan()
        self.assertNotEqual(envs['system']['version'],envs['rpi']['version'])

    def test_wrong_native_abi_and_no_parent_import(self):
        p=self.env('rpi')
        site=next((p/'lib').glob('python*/site-packages'))
        (site/'sensor.cpython-39-aarch64-linux-gnu.so').touch()
        pkg=site/'hardware';pkg.mkdir()
        (pkg/'__init__.py').write_text('raise RuntimeError("must never import")')
        (pkg/'chip.py').touch()
        info=self.scan({'sensor','hardware.chip'})[0]['rpi']
        self.assertEqual(info['modules'],{'sensor':False,'hardware.chip':True})

    def test_registered_nonstandard_prefix(self):
        root=self.base/'conda-envs/rpi'
        venv.EnvBuilder(with_pip=False,symlinks=True).create(root)
        (root/'conda-meta').mkdir()
        self.registry.write_text(str(root)+'\n')
        self.assertEqual(self.scan()[0]['rpi']['prefix'],str(root))

    def test_invalid_python3_falls_back_to_verified_python(self):
        root=self.env('rpi')
        for name in ('python3','python'):
            (root/'bin'/name).unlink()
        (root/'bin/python').symlink_to(sys.executable)
        (root/'bin/python3').write_text('#!/bin/false\n')
        (root/'bin/python3').chmod(0o755)
        self.assertEqual(self.scan()[0]['rpi']['path'],str(root/'bin/python'))

    def test_end_to_end_installer(self):
        root=self.base/'installed';root.mkdir(mode=0o755)
        source=self.base/'input.py'
        source.write_bytes((PORT+'\nimport sys\nprint(sys.executable)\n').encode())
        entry=root/'hello';entry.write_bytes(source.read_bytes());entry.chmod(0o755)
        expected=tool.digest(source.read_bytes())
        plan=self.base/'manifest.json'
        plan.write_text(json.dumps(dict(version=1,profile='test',target=str(root),files=[
            dict(path=entry.name,env='system',**{'from':PORT,'to':SYSTEM},sha256=expected)])))
        command=[sys.executable,'-B',str(TOOL),'--target',str(root),'--manifest',str(plan)]
        env=dict(os.environ,HOME=str(self.base),PATH='/usr/bin',CONDA_PREFIX='')
        for args,status in [(['--dry-run'],0),(['--check'],1),
                            (['--apply','--non-interactive','--approved-profile','test'],0),
                            (['--check'],0)]:
            run=subprocess.run(command+args,env=env,capture_output=True,text=True)
            self.assertEqual(run.returncode,status,run.stdout+run.stderr)
        self.assertEqual(subprocess.check_output([entry]),b'/usr/bin/python3\n')
        self.assertEqual(tool.digest(source.read_bytes()),expected)

    def test_python_wrapper_never_executed(self):
        bin_dir=self.base/'bin';bin_dir.mkdir()
        exe=bin_dir/'python3'; marker=self.base/'ran'
        exe.write_text(f'#!/bin/sh\ntouch {marker}\n');exe.chmod(0o755)
        with patch.dict(os.environ,{'PATH':str(bin_dir)}):
            self.assertIn('error',self.scan()[0]['portable'])
        self.assertFalse(marker.exists())


if __name__=='__main__':
    unittest.main()
