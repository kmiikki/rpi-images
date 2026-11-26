"""A09 provisioning on a temporary host, without changing the system archive."""

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_rpi_setup import FakeHost, m as setup
from installation_state import Store
import lifecycle
import locale_setup as locales


SUPPORTED = '\n'.join(f'{name} UTF-8' for name in (*locales.DEFAULTS,'de_DE.UTF-8','fr_FR.UTF-8'))+'\n'
ORIGINAL = '# keep this comment\n# fi_FI.UTF-8 UTF-8\nen_GB.UTF-8 UTF-8\nen_US.UTF-8 UTF-8\n'


class LocaleHost(FakeHost):
    def __init__(self, root):
        super().__init__()
        self.root = root
        self.locale_requests = {'LANG':'en_GB.UTF-8', 'LC_NUMERIC':'en_GB.UTF-8', 'LC_TIME':'fi_FI.UTF-8'}
        self.installed = {'C', 'POSIX', 'C.utf8', 'en_GB.utf8', 'en_US.utf8'}
        self.generate = True

    def probe(self, argv):
        if argv[-2:]==['/usr/bin/locale','-a']:
            return subprocess.CompletedProcess(argv,0,'\n'.join(self.installed),'')
        return super().probe(argv)

    def run(self, argv, **kwargs):
        result = super().run(argv,**kwargs)
        if argv[-2:]==[locales.GEN_COMMAND,'--keep-existing'] and self.generate:
            content=(self.root/'etc/locale.gen').read_text()
            self.installed.update(row.split()[0].replace('UTF-8','utf8') for row in locales.entries(content).values())
        return result


class LocaleTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)/'host'
        root.mkdir(mode=0o755)
        self.store=Store(Path(temp.name)/'state',root)
        self.host=LocaleHost(root)
        with self.store.locked():
            self.store.start(self.host.snapshot(),{})
            self.store.data['os_upgrade']={'status':'completed'}
            self.store.save()
        self.host.records=self.store
        self.conf=self.file('/etc/locale.conf','LANG=en_GB.UTF-8\nLC_NUMERIC=en_GB.UTF-8\n')
        self.file(locales.SUPPORTED,SUPPORTED)
        self.file(locales.GEN_COMMAND,'# fixture\n')
        self.config=self.file(locales.GEN_CONFIG,ORIGINAL)

    def file(self, logical, content):
        output=self.store.ensure_parents(logical)
        output.write_text(content)
        output.chmod(0o644)
        return output

    def test_profiles_preview_and_apply_locale_stage_before_preboot(self):
        for profile in ('GENERAL','HOME','AALTO'):
            with self.subTest(profile=profile), redirect_stdout(io.StringIO()) as out:
                self.config.write_text(ORIGINAL)
                self.host.installed={'C','C.utf8','en_GB.utf8'}
                self.host.calls.clear()
                self.store.data['locales']=[]
                self.store.save()
                flags=['--profile',profile,'--share-later','--no-wolfram']
                with patch.object(setup,'apply',return_value=0) as apply:
                    self.assertEqual(setup.main([*flags,'--plan'],self.host),0)
                    self.assertEqual(setup.main([*flags,'--dry-run'],self.host),0)
                    self.assertEqual(self.config.read_text(),ORIGINAL)
                    self.assertFalse(self.host.calls)
                    apply.assert_not_called()
                    original_preboot=self.host.run_preboot
                    def checked(*,preview,**kwargs):
                        if not preview:
                            self.assertIn('fi_FI.utf8',self.host.installed)
                        return original_preboot(preview=preview,**kwargs)
                    with patch.object(self.host,'run_preboot',side_effect=checked):
                        self.assertEqual(setup.main([*flags,'--yes'],self.host),0)
                self.assertEqual(set(self.store.data['locales']),set(locales.DEFAULTS))
                self.assertEqual(self.conf.read_text(),'LANG=en_GB.UTF-8\nLC_NUMERIC=en_GB.UTF-8\n')
                self.assertIn('fi_FI.UTF-8',apply.call_args.args[1]['locale_summary'])
                self.assertIn('Locales to generate',out.getvalue())
                self.assertNotIn(locales.GEN_CONFIG,self.store.data['paths'])

    def test_repair_and_update_are_idempotent_and_remove_preserves_system_data(self):
        self.host.locale_requests.update(LC_TIME='fi_FI.utf8',LC_MESSAGES='de_DE.UTF-8',LANGUAGE='fr_FR:en')
        with redirect_stdout(io.StringIO()) as out:
            argv=['--manage','--action','repair','--component','locales']
            before=self.store.file.read_bytes()
            self.assertEqual(lifecycle.main([*argv,'--dry-run'],self.host,store=self.store),0)
            self.assertEqual(lifecycle.verify(self.store,self.host,'locales'),1)
            self.assertEqual(self.store.file.read_bytes(),before)
            self.assertFalse(self.host.calls)
            approved=lifecycle.software_action(self.store,self.host,'repair','locales',[],True)
            lifecycle.software_action(self.store,self.host,'repair','locales',[],False,approved)
            self.assertEqual(lifecycle.verify(self.store,self.host,'locales'),0)
            enabled=self.config.read_text()
            self.assertTrue(enabled.startswith(ORIGINAL))
            self.assertIn('de_DE.UTF-8 UTF-8',enabled)
            self.assertIn('fr_FR.UTF-8 UTF-8',enabled)
            self.assertEqual(len(self.host.calls),1)
            self.assertEqual(self.host.calls[0],[*locales.CLEAN_ENV,locales.GEN_COMMAND,'--keep-existing'])
            self.host.locale_requests.pop('LC_MESSAGES')
            self.host.locale_requests.pop('LANGUAGE')
            self.host.installed.remove('de_DE.utf8')
            repair=lifecycle.software_action(self.store,self.host,'update','locales',[],True)
            self.assertEqual(repair.generate,('de_DE.UTF-8',))
            self.assertFalse(repair.enable)
            lifecycle.software_action(self.store,self.host,'update','locales',[],False,repair)
            self.assertEqual(len(self.host.calls),2)
            self.assertEqual(self.config.read_text(),enabled)
            already=lifecycle.software_action(self.store,self.host,'repair','locales',[],True)
            lifecycle.software_action(self.store,self.host,'repair','locales',[],False,already)
            self.assertEqual(len(self.host.calls),2)
            args=['--manage','--action','remove','--component','locales']
            self.assertEqual(lifecycle.main(args,self.host,store=self.store),0)
            self.assertEqual(lifecycle.main([*args,'--plan'],self.host,store=self.store),0)
        self.assertEqual(self.config.read_text(),enabled)
        self.assertIn('PASS locale selections',out.getvalue())
        self.assertIn('Preserve /etc/locale.gen',out.getvalue())

    def test_invalid_input_falls_back_and_generation_failure_requires_readback(self):
        self.host.locale_requests.update(LC_TIME='xx_XX.UTF-8',LC_ALL='')
        self.host.generate=False
        with redirect_stdout(io.StringIO()) as out:
            approved=locales.plan(self.host,self.store)
            self.assertEqual(approved.fallback,(('LC_TIME','xx_XX.UTF-8'),))
            self.assertNotIn('xx_XX.UTF-8',approved.locales)
            with self.assertRaisesRegex(ValueError,'did not generate'):
                lifecycle.apply_locales(self.store,self.host,approved)
            self.assertEqual(self.store.data['components']['locales']['status'],'failed')
            self.assertNotIn('xx_XX',self.config.read_text())
            self.host.generate=True
            self.assertIn('LIMITED',lifecycle.apply_locales(self.store,self.host,locales.plan(self.host,self.store)))
            self.assertEqual(lifecycle.verify(self.store,self.host,'locales'),1)
        self.assertIn('local fallback',out.getvalue())

    def test_generator_missing_preserves_existing_configuration(self):
        self.store.path(locales.GEN_COMMAND).unlink()
        proposal=locales.plan(self.host,self.store)
        with self.assertRaisesRegex(ValueError,'locale-gen is unavailable'):
            locales.apply(self.host,self.store,proposal)
        self.assertEqual(self.config.read_text(),ORIGINAL)
        self.assertFalse(self.host.calls)

    def test_child_environment_recovers_forwarded_time_and_keeps_numeric(self):
        env={'LANG':'en_GB.UTF-8','LC_TIME':'fi_FI.UTF-8','LC_NUMERIC':'en_GB.UTF-8','LC_ALL':''}
        with (patch.dict(os.environ,env,clear=True), redirect_stderr(io.StringIO()) as err,
              patch.object(subprocess,'check_output',side_effect=[
                  'C\nC.utf8\nen_GB.utf8\n','C\nC.utf8\nen_GB.utf8\nfi_FI.utf8\n']),
              patch.dict(locales.keyboard['locale_environment'].__globals__,
                         {'locale_alias_available':lambda name:False})):
            host=setup.Host()
            self.assertNotIn('LC_TIME',host.env)
            host.refresh_locale_environment()
            self.assertEqual(host.env['LC_TIME'],env['LC_TIME'])
            self.assertEqual(host.env['LANG'],env['LANG'])
            self.assertEqual(host.env['LC_NUMERIC'],env['LC_NUMERIC'])
            self.assertEqual(host.env['LC_ALL'],'')
            self.assertEqual(dict(os.environ),env)
            self.assertFalse(err.getvalue())

    def test_additional_admin_username_needs_no_suffix_on_general_or_home(self):
        for profile in ('GENERAL','HOME'):
            args=setup.parser().parse_args(['--profile',profile,'--additional-user','technician','--plan'])
            self.assertEqual(setup.resolve(args,self.host.snapshot(),self.host)['additional'],['technician'])
