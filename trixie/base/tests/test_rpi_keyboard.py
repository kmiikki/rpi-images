"""Keyboard tests use temporary XKB and OS files and never invoke sudo or raspi-config."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'bin/rpi-keyboard'
LOADER = importlib.machinery.SourceFileLoader('rpi_keyboard', str(SOURCE))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
keyboard = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(keyboard)

XKB = """<xkbConfigRegistry><layoutList>
<layout><configItem><name>fi</name><description>Finnish</description></configItem></layout>
<layout><configItem><name>us</name><description>English (US)</description></configItem></layout>
<layout><configItem><name>xyz-custom</name><description>Local language</description></configItem></layout>
</layoutList></xkbConfigRegistry>
"""
BACKEND = """#!/bin/sh
nonint() { "$@"; }
update_labwc_keyboard() {
    kill -HUP $(pgrep -x labwc)
}
do_configure_keyboard() {
    update_labwc_keyboard
}
case "$1" in
    nonint | batch)
        INTERACTIVE=False
        "$@"
        ;;
esac
"""


class KeyboardTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.rules = self.root / 'rules'
        self.rules.mkdir()
        self.xml = self.rules / 'evdev.xml'
        self.xml.write_text(XKB)
        self.system = self.root / 'keyboard'
        self.system.write_text('XKBLAYOUT="us"\nXKBMODEL=pc105\nXKBVARIANT=""\n')
        self.backend = self.root / 'raspi-config'
        self.backend.write_text(BACKEND)
        self.backend.chmod(0o755)
        self.sudo = self.root / 'sudo'
        self.sudo.touch(mode=0o755)
        self.labwc = self.root / 'labwc'
        self.greeter = self.root / 'greeter'
        self.desktop = {name: self.root / name / '.config/labwc/environment' for name in ('kim', 'chem')}
        for path in self.desktop.values():
            path.parent.mkdir(parents=True)
        stack.enter_context(patch.multiple(
            keyboard, RULES=self.rules, SYSTEM=self.system, RASPI_CONFIG=self.backend,
            SUDO=self.sudo, LABWC=self.labwc, GREETER=self.greeter,
            LABWC_DEFAULT=self.root / 'labwc-default',
        ))
        self.euid = stack.enter_context(patch.object(keyboard.os, 'geteuid', return_value=1000))
        self.pwuid = stack.enter_context(patch.object(
            keyboard.pwd, 'getpwuid', side_effect=lambda uid: SimpleNamespace(
                pw_dir=str(self.root / {1000: 'kim', 1001: 'chem'}[uid]),
            ),
        ))
        self.pwnam = stack.enter_context(patch.object(
            keyboard.pwd, 'getpwnam', side_effect=lambda name: SimpleNamespace(
                pw_dir=str(self.root / name), pw_uid={'kim':1000,'chem':1001}[name]),
        ))
        stack.enter_context(patch.dict(os.environ, {}, clear=True))
        self.run = stack.enter_context(patch.object(keyboard.subprocess, 'run'))

    def invoke(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(keyboard.main(list(args)), 0)
        return output.getvalue()

    def test_default_listing_and_explicit_list(self):
        result = self.invoke()
        self.assertEqual(self.invoke('--list'), result)
        for text in ('fi', 'Finnish', 'us', 'English (US)', 'xyz-custom', 'Local language'):
            self.assertIn(text, result)
        self.run.assert_not_called()

    def test_help_independent_of_xkb_or_sudo(self):
        self.xml.unlink()
        self.sudo.unlink()
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as exc:
            keyboard.main(['--help'])
        self.assertEqual(exc.exception.code, 0)
        self.assertIn('--current', output.getvalue())
        self.assertIn('--list', output.getvalue())
        self.run.assert_not_called()

    def test_current_distinguishes_storage_from_active_layout(self):
        self.desktop['kim'].write_text('XKB_DEFAULT_LAYOUT="fi"\n')
        self.greeter.write_text('XKB_DEFAULT_LAYOUT=us\n')
        self.xml.unlink()
        output = self.invoke('--current')
        self.assertIn("XKBLAYOUT='us'", output)
        self.assertIn("XKB_DEFAULT_LAYOUT='fi'", output)
        self.assertIn(str(self.desktop['kim']), output)
        self.assertIn(str(self.greeter), output)
        self.assertIn('Active session layout: unconfirmed', output)
        self.run.assert_not_called()

    def test_current_does_not_execute_assignments(self):
        self.system.write_text('XKBLAYOUT=$(touch /tmp/ignored)\nXKBMODEL=pc105 # comment\n')
        output = self.invoke('--current')
        self.assertIn('unreadable assignment', output)
        self.assertIn("XKBMODEL='pc105'", output)
        self.run.assert_not_called()

    def test_invalid_code_is_rejected_before_requesting_sudo(self):
        for code in ('unlisted', 'us,fi', 'fi;true'):
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, 'rpi-keyboard --list'):
                self.invoke(code)
        self.run.assert_not_called()

    def test_invalid_or_missing_database_and_base_list_fallback(self):
        self.xml.write_text('<invalid>')
        with self.assertRaisesRegex(ValueError, 'No readable XKB layout database'):
            self.invoke()
        (self.rules / 'base.lst').write_text(
            '! model\n pc105 Standard\n! layout\n se Swedish\n! variant\n svd se: Variant\n',
        )
        self.assertIn('Swedish', self.invoke('--list'))
        self.assertNotIn('svd', self.invoke('--list'))
        self.run.assert_not_called()

    def test_extras_xml_layouts_are_loaded(self):
        (self.rules / 'evdev.extras.xml').write_text(XKB.replace('xyz-custom', 'extra'))
        self.assertIn('extra', keyboard.layouts())
        self.assertIn('xyz-custom', keyboard.layouts())

    def test_missing_and_incompatible_backend_are_reported_before_execution(self):
        self.backend.unlink()
        with self.assertRaisesRegex(ValueError, 'raspi-config is missing'):
            self.invoke('fi')
        self.backend.write_text('#!/bin/sh\nwhiptail --menu "Settings"\n')
        self.backend.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'non-interactive'):
            self.invoke('fi')
        self.labwc.touch()
        self.backend.write_text(BACKEND.replace('-HUP', '-CONT'))
        with self.assertRaisesRegex(ValueError, 'live labwc reload'):
            self.invoke('fi')
        self.run.assert_not_called()

    def test_valid_selection_uses_exact_noninteractive_command_with_sudo(self):
        self.run.side_effect = lambda *args, **kwargs: self.system.write_text('XKBLAYOUT="xyz-custom"\n')
        output = self.invoke('xyz-custom')
        self.run.assert_called_once_with(
            [str(self.sudo), str(self.backend), 'nonint', 'do_configure_keyboard', 'xyz-custom'],
            stdin=subprocess.DEVNULL, check=True,
        )
        self.assertIn('layout xyz-custom stored', output)
        self.assertIn('No keyboard reboot needed', output)

    def test_user_independence_and_root_invocation_verify_the_target_desktop(self):
        self.labwc.touch()
        self.greeter.write_text('XKB_DEFAULT_LAYOUT=us\n')
        for user, uid in (('kim', 1000), ('chem', 1001)):
            for elevated in (False, True):
                with self.subTest(user=user, elevated=elevated):
                    self.run.reset_mock()
                    self.system.write_text('XKBLAYOUT=us\n')
                    self.greeter.write_text('XKB_DEFAULT_LAYOUT=us\n')
                    self.desktop[user].unlink(missing_ok=True)
                    self.euid.return_value = 0 if elevated else uid

                    def apply(*args, **kwargs):
                        self.system.write_text('XKBLAYOUT=fi\n')
                        self.desktop[user].write_text('XKB_DEFAULT_LAYOUT=fi\n')
                        self.greeter.write_text('XKB_DEFAULT_LAYOUT=fi\n')

                    self.run.side_effect = apply
                    with patch.dict(os.environ, {'SUDO_USER': user} if elevated else {}):
                        self.assertIn('layout fi stored', self.invoke('fi'))
                        self.assertIn(str(self.desktop[user]), self.invoke('--current'))
                    sudo_prefix = [] if elevated else [str(self.sudo)]
                    self.run.assert_called_once_with(
                        sudo_prefix + [str(self.backend), 'nonint', 'do_configure_keyboard', 'fi'],
                        stdin=subprocess.DEVNULL, check=True,
                    )

    def test_matching_layout_is_a_noop_without_privilege(self):
        self.backend.unlink()
        self.sudo.unlink()
        self.assertIn('already stored', self.invoke('us'))
        self.run.assert_not_called()

    def test_missing_sudo_denial_and_no_op_backend_report_errors(self):
        self.sudo.unlink()
        with self.assertRaisesRegex(ValueError, 'requires sudo'):
            self.invoke('fi')
        self.run.assert_not_called()
        self.sudo.touch(mode=0o755)
        self.run.side_effect = subprocess.CalledProcessError(1, ['sudo'])
        with self.assertRaisesRegex(ValueError, r'failed \(exit 1\)'):
            self.invoke('fi')
        self.run.side_effect = None
        with self.assertRaisesRegex(ValueError, 'did not store layout fi'):
            self.invoke('fi')

    def test_reporting_success_requires_persisted_desktop_layout(self):
        self.labwc.touch()
        self.run.side_effect = lambda *args, **kwargs: self.system.write_text('XKBLAYOUT=fi\n')
        with self.assertRaisesRegex(ValueError, 'labwc configuration'):
            self.invoke('fi')

    def test_status_and_selection_flags_cannot_be_combined(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            self.invoke('--current', 'fi')
        self.assertEqual(exc.exception.code, 2)
        self.run.assert_not_called()
