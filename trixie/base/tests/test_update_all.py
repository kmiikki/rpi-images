"""Whole-installation lifecycle tests using only temporary state and mocked commands."""

from contextlib import redirect_stdout, nullcontext
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'install'))
from installation_state import Store, ABSENT, tree_fingerprint
import lifecycle
import os_upgrade
import update_all as update


class UpdateAllTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/'host'
        self.root.mkdir(mode=0o755)
        self.store=Store(Path(tmp.name)/'state',self.root)
        with self.store.locked():
            self.store.start({}, {})
            self.store.data['selected']={'lab314':True,'spyder':True,'hardware':True,'wolfram':False,'imaging':False}
            self.store.save()
        self.host=SimpleNamespace(env={'TMPDIR':tmp.name},log=None)

    def test_update_all_cli_dispatches_without_a_component(self):
        argv=['--manage','--action','update','--all','--plan']
        with patch.object(lifecycle,'require_root'),patch.object(update,'run',return_value=0) as run:
            self.assertEqual(lifecycle.main(argv,self.host,self.store),0)
        self.assertTrue(run.call_args.args[-1].plan)
        self.assertIsNone(run.call_args.args[-1].component)

    def test_noninteractive_update_requires_the_previously_reviewed_plan_id(self):
        args=['--manage','--action','update','--all','--yes']
        with self.assertRaises(SystemExit),patch('sys.stderr',new=io.StringIO()):
            lifecycle.main(args,self.host,self.store)

    def test_managed_update_leaves_a_locally_changed_file_intact(self):
        name='/etc/test.conf'
        path=self.store.path(name)
        path.parent.mkdir(mode=0o755)
        with self.store.stage('system',[(name,False)]):
            path.write_text('old installed')
        path.write_text('user settings')
        changes=[]
        with redirect_stdout(io.StringIO()) as output:
            update.add_file(self.store,changes,'system',name,b'new default')
        self.assertEqual(changes,[])
        self.assertIn('PRESERVE',output.getvalue())
        self.assertEqual(path.read_text(),'user settings')

    def test_missing_launcher_and_managed_asset_update_without_touching_other_files(self):
        name='/etc/launcher'
        path=self.store.path(name)
        path.parent.mkdir(mode=0o755)
        (path.parent/'user-preferences').write_text('custom')
        changes=[]
        with redirect_stdout(io.StringIO()):
            update.add_file(self.store,changes,'spyder-desktop',name,b'new',0o755)
            self.assertEqual(changes[0].current,ABSENT)
            with self.store.stage('spyder-desktop',[(name,False)]):
                update.install_file(self.store,changes[0])
        self.assertEqual(path.read_bytes(),b'new')
        self.assertTrue(os.access(path,os.X_OK))
        self.assertEqual((path.parent/'user-preferences').read_text(),'custom')
        self.assertEqual(self.store.snapshot(name),self.store.data['paths'][name]['installed'])

    def test_apt_dependencies_follow_the_saved_selection(self):
        required=update.required_apt({'system':True,'hardware':False})
        self.assertNotIn('spyder',required)
        self.assertNotIn('python3-picamera2',required)
        self.assertNotIn('wolfram-engine',required)

    def test_update_all_requests_reporting_for_the_existing_native_prefix(self):
        self.host.native_lab314=lambda path: True
        self.host.exists=lambda path: True
        with patch.object(update,'conda_plan') as plan:
            update.conda_plans(self.host,self.store,{'lab314':True,'spyder':True})
        self.assertEqual(plan.call_args.args[2:4],('lab314','/opt/lab314'))
        self.assertLessEqual({'reportlab','pypdf','jinja2','spyder==6.1.8'},set(plan.call_args.args[-1]))
        self.assertIn('python3-picamera2',update.required_apt({'hardware':True}))

    def test_apt_update_disables_system_hooks_and_keeps_lists_private(self):
        work=self.root/'apt'
        self.host.run=lambda *a,**k:subprocess.CompletedProcess([],0,'','')
        with patch.object(os_upgrade,'repository_release') as check,patch.object(self.host,'run',wraps=self.host.run) as run:
            options=os_upgrade.isolated_lists(self.host,work)
        argv=run.call_args.args[0]
        self.assertIn(f'Dir::State::lists={work}/lists',argv)
        self.assertIn(f'Dir::Cache::archives={work}/archives',argv)
        self.assertIn('#clear APT::Update::Post-Invoke-Success;', (work/'update.conf').read_text())
        check.assert_called_once_with(self.host,options)

    def test_recheck_rejects_an_unapproved_conda_transaction(self):
        path=self.store.path('/opt/lab314')
        path.mkdir(parents=True)
        plan={'UNLINK':{},'LINK':{'opencv':('5.1.0','qt6_build')}}
        step=update.CondaChange('lab314','/opt/lab314',{},plan,{})
        self.host.run=lambda *a,**k:None
        different={'success':True,'actions':{'LINK':[{'name':'opencv','version':'5.1.0','build':'other'}]}}
        with patch.object(update,'tree_fingerprint',return_value={}),patch.object(update,'conda_command',return_value=different), \
                patch.object(self.host,'run',wraps=self.host.run) as run,self.assertRaisesRegex(ValueError,'differs'):
            update.verify_conda_transaction(self.host,self.store,step)
        self.assertIn('--download-only',run.call_args.args[0])

    def test_package_cache_exception_does_not_authorize_writable_installed_files(self):
        prefix=self.root/'prefix'
        prefix.mkdir(mode=0o755)
        cache=prefix/'pkgs'
        cache.mkdir(mode=0o755)
        recipe=cache/'recipe'
        recipe.write_text('cache only')
        recipe.chmod(0o666)
        with self.assertRaises(ValueError):
            tree_fingerprint(prefix)
        tree_fingerprint(prefix,ignore_package_cache=True)
        other=prefix/'installed'
        other.write_text('installed')
        other.chmod(0o666)
        with self.assertRaisesRegex(ValueError,'installed'):
            tree_fingerprint(prefix,ignore_package_cache=True)

    def test_update_all_plan_and_cancel_never_apply_or_write_receipt(self):
        args=SimpleNamespace(plan=True,expect_plan=None,yes=False)
        audit=self.store.file.read_bytes()
        apt=({},(),[],(),set(),'arm64')
        with (patch.object(lifecycle,'inspection',return_value=nullcontext()),
              patch.object(update,'apt_plan',return_value=apt),patch.object(update,'conda_plans',return_value=[]),
              patch.object(update,'file_plan',return_value=[]),patch.object(update,'terminal_plan',return_value=None),
              patch.object(update.preboot,'active_layout',return_value='fi'),
              patch.object(lifecycle,'confirm',return_value=False) as confirm,
              patch.object(update,'apply_apt') as apply,redirect_stdout(io.StringIO())):
            self.assertEqual(update.run(self.host,self.store,args),0)
            confirm.assert_not_called()
            args.plan=False
            self.assertEqual(update.run(self.host,self.store,args),1)
            apply.assert_not_called()
        self.assertEqual(self.store.file.read_bytes(),audit)

    def test_spyder_activation_preserves_paths_added_by_the_user(self):
        config=update.BASE/'config/lab314'
        activate=config/'spyder-activate.sh'
        deactivate=config/'spyder-deactivate.sh'
        shim='/usr/local/lib/rpi-images/lab314-bin'
        shell='''
set -eu
PATH=/opt/lab314/bin:/usr/bin
. "$1"
. "$1"
[[ $PATH == "$3:/opt/lab314/bin:/usr/bin" ]]
PATH="/home/user/custom:$PATH"
. "$2"
[[ $PATH == /home/user/custom:/opt/lab314/bin:/usr/bin ]]
PATH="/home/user/custom:$3:/usr/bin"
. "$1"
. "$2"
[[ $PATH == "/home/user/custom:$3:/usr/bin" ]]
'''
        subprocess.run(['bash','-c',shell,'bash',activate,deactivate,shim],check=True)


if __name__=='__main__':
    unittest.main()
