"""Preboot tests use only temporary host paths and mocked device/command probes."""

from contextlib import ExitStack, redirect_stdout
import gzip
import io
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'install'))
import preboot
import setup_rpi
from test_rpi_setup import FakeHost


# Representative Raspberry Pi OS image, including its end-of-file overlay scopes.
STOCK = """# Uncomment interfaces where needed
#dtparam=i2c_arm=on
#dtparam=i2s=on
#dtparam=spi=on

dtparam=audio=on
camera_auto_detect=1
dtoverlay=vc4-kms-v3d

[cm4]
otg_mode=1
[cm5]
dtoverlay=dwc2,dr_mode=host
[pi5]
dtoverlay=nospi10
[all]
"""
ENABLED = 'dtparam=i2c_arm=on\ndtparam=spi=on\n'


class KernelCompatibilityTests(unittest.TestCase):
    def setUp(self):
        work=tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        root=Path(work.name)
        self.firmware=root/'boot/firmware/config.txt'
        self.firmware.parent.mkdir(parents=True)
        self.original='auto_initramfs=1\n'+STOCK
        self.firmware.write_text(self.original)
        self.release='6.18.60+rpt-rpi-v8'
        self.modules=root/'modules'
        module=self.modules/self.release/'modules.dep'
        module.parent.mkdir(parents=True)
        module.write_text('kernel/test.ko:\n')
        self.image=self.firmware.parent/'kernel8.img'
        self.stock_image=self.firmware.parent.parent/f'vmlinuz-{self.release}'
        self.initrd=self.firmware.parent/'initramfs8'
        self.stock_initrd=self.firmware.parent.parent/f'initrd.img-{self.release}'
        for path in (self.initrd,self.stock_initrd):
            path.write_bytes(b'stock initramfs fixture')
        self.set_pages(1)

    def set_pages(self,flag):
        header=bytearray(64)
        header[56:60]=b'ARM\x64'
        struct.pack_into('<Q',header,24,flag<<1)
        image=gzip.compress(header)
        for path in (self.image,self.stock_image):
            path.write_bytes(image)

    def test_plan_is_idempotent_and_scoped_to_pi5(self):
        original=self.original+'[pi4]\nkernel=other.img\n'
        updated=preboot.kernel_plan(original)
        self.assertTrue(updated.startswith(original))
        self.assertIn('[pi5]\n# Use the stock 4 KiB kernel',updated)
        self.assertEqual(updated.count('\nkernel=kernel8.img\n'),1)
        self.assertEqual(preboot.kernel_plan(updated),updated)
        self.assertEqual(preboot.kernel_plan(self.original+'kernel=kernel8.img\n'),
                         self.original+'kernel=kernel8.img\n')

    def test_rejects_conflicting_kernel_filters_and_initramfs(self):
        for suffix in ('kernel=kernel_2712.img\n','kernel=kernel8.img\nkernel=kernel8.img\n',
                       '[tryboot]\nkernel=kernel8.img\n','initramfs other followkernel\n','include next.txt\n'):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                preboot.kernel_plan(self.original+suffix)

    def test_requires_matching_artifacts_and_actual_4k_image(self):
        listing=subprocess.CompletedProcess([],0,f'usr/lib/modules/{self.release}/kernel/test.ko\n','')
        with patch.object(preboot.subprocess,'run',return_value=listing):
            self.assertEqual(preboot.kernel_release(self.firmware,self.modules),self.release)
            self.stock_initrd.write_bytes(b'different initramfs')
            with self.assertRaisesRegex(ValueError,'matching initramfs'):
                preboot.kernel_release(self.firmware,self.modules)
            self.set_pages(2)
            with self.assertRaisesRegex(ValueError,'4 KiB'):
                preboot.kernel_release(self.firmware,self.modules)

    def test_confirmation_backup_same_boot_and_post_reboot_verification(self):
        with redirect_stdout(io.StringIO()), patch.object(preboot,'FIRMWARE',self.firmware), \
                patch.object(Path,'is_mount',return_value=True), \
                patch.object(preboot,'kernel_release',return_value=self.release), \
                patch.object(preboot.os,'sysconf',return_value=16384) as page_size, \
                patch.object(preboot.platform,'release',return_value='old-rpi-2712') as kernel:
            self.assertIn('change required',preboot.kernel_status(None,'one'))
            self.assertEqual(preboot.configure_kernel(approve=lambda:False,pending=None,boot_id='one'),'deferred')
            self.assertEqual(self.firmware.read_text(),self.original)
            self.assertEqual(preboot.configure_kernel(approve=lambda:True,pending=None,boot_id='one'),'changed')
            backups=list(self.firmware.parent.glob('config.txt.preboot.bak.*'))
            self.assertEqual([p.read_text() for p in backups],[self.original])
            self.assertIn('Reboot required',preboot.kernel_status('one','one'))
            self.assertIn('Unexpected',preboot.kernel_status('one','two'))
            approve=Mock(side_effect=AssertionError('already selected'))
            self.assertEqual(preboot.configure_kernel(approve=approve,pending='one',boot_id='one'),'reboot')
            with self.assertRaisesRegex(ValueError,'After reboot'):
                preboot.configure_kernel(approve=approve,pending='one',boot_id='two')
            page_size.return_value=4096
            kernel.return_value=self.release
            self.assertIn('Ready – stock v8',preboot.kernel_status('one','two'))
            self.assertEqual(preboot.configure_kernel(approve=approve,pending='one',boot_id='two'),'ready')
            self.assertEqual(list(self.firmware.parent.glob('config.txt.preboot.bak.*')),backups)


class FirmwarePlanTests(unittest.TestCase):
    def test_fresh_stock_image_preserves_original_entries(self):
        updated, settings, edits = preboot.firmware_plan(STOCK)
        self.assertEqual(updated, ENABLED + STOCK)
        self.assertEqual(settings, {'i2c_arm': [], 'spi': []})
        self.assertEqual(len(edits), 2)
        self.assertEqual(preboot.firmware_plan(updated)[2], [])

    def test_already_enabled_alias_and_boolean_values(self):
        original = 'device_tree_param=i2c,audio=on,spi=yes\n' + STOCK
        updated, settings, edits = preboot.firmware_plan(original)
        self.assertEqual(updated, original)
        self.assertEqual(settings, {'i2c_arm': [(1, True)], 'spi': [(1, True)]})
        self.assertFalse(edits)

    def test_sections_preserve_other_models_and_use_pi5_and_all(self):
        original = ('[pi4]\ndtparam=i2c_arm=off\n[none]\ndtparam=spi=off\n'
                    '[all]\n[pi4]\n[pi5]\ndtparam=i2c_arm=off\n'
                    '[cm5]\ndtparam=spi=off\n[all]\ndtparam=spi=on\n')
        updated, settings, edits = preboot.firmware_plan(original)
        self.assertEqual(updated, original.replace('[pi5]\ndtparam=i2c_arm=off',
                                                   '[pi5]\ndtparam=i2c_arm=on'))
        self.assertEqual(settings, {'i2c_arm': [(8, False)], 'spi': [(12, True)]})
        self.assertEqual(len(edits), 1)

    def test_conflicts_and_duplicates_preserve_comments_spacing_and_unrelated_parameters(self):
        original = ('dtparam=audio=on, i2c_arm = false ,i2s=off # keep\r\n'
                    'dtparam=i2c=1,spi=0,spi=on\r\n'
                    '[pi5]\r\ndtparam=spi=on')
        updated, settings, edits = preboot.firmware_plan(original)
        self.assertEqual(updated, original.replace('false', 'on').replace('spi=0', 'spi=on'))
        self.assertEqual(settings['i2c_arm'], [(1, False), (2, True)])
        self.assertEqual(settings['spi'], [(2, False), (2, True), (4, True)])
        self.assertEqual(len(edits), 2)
        self.assertEqual(preboot.firmware_plan(updated)[2], [])
        messages = io.StringIO()
        with redirect_stdout(messages):
            preboot.describe_firmware(settings)
        self.assertIn('conflicting on/off', messages.getvalue())
        self.assertIn('multiple active entries', messages.getvalue())

    def test_unambiguous_duplicate_settings_are_left_in_place(self):
        original = ENABLED + '[pi5]\ndtparam=spi=true\n'
        updated, _, edits = preboot.firmware_plan(original)
        self.assertEqual(updated, original)
        self.assertFalse(edits)

    def test_unrelated_conditionals_and_inactive_include_are_preserved(self):
        original = ('[gpio4=1]\n[pi4]\ninclude other-config.txt\n'
                    'dtparam=spi=off\n[all]\n' + ENABLED)
        self.assertEqual(preboot.firmware_plan(original)[0], original)

    def test_ambiguous_filters_overlay_scope_include_and_malformed_settings(self):
        cases = {
            '[EDID=test]\n[pi5]\ndtparam=spi=off\n': 'Ambiguous',
            'include custom.txt\n': 'include',
            'device_tree=custom.dtb\n': 'Custom Device Tree',
            'dtoverlay=custom\n[all]\ndtparam=spi=on\n': 'Ambiguous',
            '[pi5\ndtparam=spi=on\n': 'Malformed firmware filter',
            'dtparam=spi disabled\n': 'Malformed',
            'dtparam=spi=maybe\n': 'Unsupported',
            'dtparam=' + 'x' * 90 + ',spi=on\n': 'line limit',
        }
        for original, error in cases.items():
            with self.subTest(original=original), self.assertRaisesRegex(ValueError, error):
                preboot.firmware_plan(original)

    def test_empty_overlay_ends_overlay_parameter_scope(self):
        original = 'dtoverlay=custom\ndtoverlay=\n' + ENABLED
        self.assertEqual(preboot.firmware_plan(original)[0], original)


class PrebootTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.firmware = root / 'boot/config.txt'
        self.firmware.parent.mkdir()
        self.firmware.write_text(STOCK)
        self.firmware.chmod(0o640)
        self.model = root / 'model'
        self.model.write_bytes(b'Raspberry Pi 5 Model B Rev 1.0\0')
        self.image = root / 'rpi-issue'
        self.image.touch()
        self.keyboard = root / 'rpi-keyboard'
        self.modules = root / 'modules-load.d'
        self.modules.mkdir()
        self.module_file = self.modules / 'rpi-preboot-i2c.conf'
        self.legacy_modules = root / 'modules'
        self.dev = root / 'dev'
        self.dev.mkdir()
        self.lock = root / 'lock'
        self.reboot_marker = root / 'reboot-required'
        self.preference = root / 'state/keyboard.json'
        stack.enter_context(patch.multiple(
            preboot, FIRMWARE=self.firmware, MODEL=self.model, IMAGE_MARKER=self.image,
            KEYBOARD=self.keyboard, MODULE_FILE=self.module_file, MODULE_DIRS=(self.modules,),
            LEGACY_MODULES=self.legacy_modules, DEV=self.dev, LOCK=self.lock,
            REBOOT_MARKER=self.reboot_marker, KEYBOARD_PREFERENCE=self.preference,
            SYSTEM_OWNER=(os.getuid(), os.getgid()),
        ))
        self.release = {'ID': 'debian', 'VERSION_ID': '13', 'VERSION_CODENAME': 'trixie',
                        'PRETTY_NAME': 'Debian GNU/Linux 13 (trixie)'}
        stack.enter_context(patch.object(preboot.platform, 'freedesktop_os_release', return_value=self.release))
        stack.enter_context(patch.object(preboot.platform, 'machine', return_value='aarch64'))
        stack.enter_context(patch.object(preboot.os, 'geteuid', return_value=0))
        stack.enter_context(patch.object(Path, 'is_mount', return_value=True))
        self.char_device = stack.enter_context(patch.object(Path, 'is_char_device', return_value=False))
        self.layout_pending = Mock(return_value=True)
        self.backend = Mock()
        self.current_layout = 'us'
        stack.enter_context(patch.object(preboot.runpy, 'run_path', return_value={
            'layout_pending': self.layout_pending, 'keyboard_backend': self.backend,
            'layouts':lambda:{'fi':'Finnish','se':'Swedish','de':'German','us':'English (US)','gb':'English (UK)'},
            'settings':lambda *args:{'XKBLAYOUT':self.current_layout},
            'SYSTEM':None,'SYSTEM_KEYS':None,
        }))
        stack.enter_context(patch.object(setup_rpi,'locale_environment',side_effect=dict))
        self.run = stack.enter_context(patch.object(preboot.subprocess, 'run'))
        self.run.side_effect=lambda command, **kwargs:setattr(self,'current_layout',command[-1])
        stack.enter_context(patch('builtins.input',return_value=''))
        stack.enter_context(patch.object(setup_rpi.Host,'standalone_preboot',
            side_effect=lambda args:preboot.run(plan=args.plan,announce_host=True,layout=args.keyboard_layout)))
        self.host = FakeHost()
        self.host.run_preboot = setup_rpi.Host().run_preboot
        self.ensure_user = stack.enter_context(patch.object(setup_rpi.accounts, 'ensure_user'))

    def invoke(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(setup_rpi.main(['--preboot', *args]), 0)
        return output.getvalue()

    def test_fresh_apply_backup_metadata_and_repeated_execution(self):
        before = self.firmware.stat()
        first = self.invoke()
        self.assertIn('Reboot required', first)
        self.assertEqual(self.firmware.read_text(), ENABLED + STOCK)
        backups = list(self.firmware.parent.glob('config.txt.preboot.bak.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), STOCK)
        for path in (self.firmware, backups[0]):
            after = path.stat()
            self.assertEqual((stat.S_IMODE(after.st_mode), after.st_uid, after.st_gid),
                             (stat.S_IMODE(before.st_mode), before.st_uid, before.st_gid))
        self.assertEqual(self.module_file.read_text(), 'i2c-dev\n')
        self.assertEqual(self.keyboard.read_bytes(), preboot.SOURCE.read_bytes())
        self.assertEqual(stat.S_IMODE(self.keyboard.stat().st_mode), 0o755)
        self.run.assert_called_once_with([str(self.keyboard), 'fi'], check=True)

        self.layout_pending.return_value = False
        after = {path: path.stat().st_mtime_ns for path in (self.firmware, self.keyboard, self.module_file)}
        second = self.invoke()
        self.assertIn('No changes needed.', second)
        self.assertIn('Reboot required', second)
        self.assertEqual(list(self.firmware.parent.glob('config.txt.preboot.bak.*')), backups)
        self.assertEqual({path: path.stat().st_mtime_ns for path in after}, after)

        (self.dev / 'spidev0.0').touch()
        self.char_device.return_value = True
        self.assertIn('Reboot required', self.invoke())
        self.reboot_marker.unlink()  # Simulate the next boot clearing /run.
        self.assertIn('No reboot required', self.invoke())

    def test_already_enabled_with_current_device_nodes_needs_no_reboot(self):
        self.firmware.write_text(ENABLED + STOCK)
        self.legacy_modules.write_text('# existing boot driver\ni2c_dev\n')
        self.layout_pending.return_value = False
        (self.dev / 'spidev0.0').touch()
        self.char_device.return_value = True
        self.assertIn('No reboot required', self.invoke())
        self.assertFalse(self.module_file.exists())
        self.assertEqual(list(self.firmware.parent.glob('*.bak.*')), [])

    def test_both_preview_flags_are_unprivileged_and_non_mutating(self):
        before = self.firmware.stat()
        with patch.object(preboot.os, 'geteuid', return_value=1000), \
                patch.object(setup_rpi, 'Host', side_effect=AssertionError('normal setup called')):
            for option in ('--plan', '--dry-run'):
                message = self.invoke(option)
                for expected in ('Debian GNU/Linux 13', 'Raspberry Pi 5', 'I²C firmware setting',
                                 'SPI firmware setting', 'Keyboard utility', 'Finnish', 'Reboot expected: yes'):
                    self.assertIn(expected, message)
        for path in (self.lock, self.keyboard, self.module_file, self.reboot_marker):
            self.assertFalse(path.exists())
        self.assertEqual(self.firmware.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(list(self.firmware.parent.iterdir()), [self.firmware])
        self.run.assert_not_called()

    def test_unsupported_os_hardware_and_wrong_privilege(self):
        with redirect_stdout(io.StringIO()):
            self.release['VERSION_CODENAME'] = 'bookworm'
            with self.assertRaisesRegex(ValueError, 'Trixie'):
                setup_rpi.main(['--preboot', '--plan'])
            self.release['VERSION_CODENAME'] = 'trixie'
            self.image.unlink()
            with self.assertRaisesRegex(ValueError, 'Trixie'):
                setup_rpi.main(['--preboot'])
            self.image.touch()
            self.model.write_text('Raspberry Pi 4 Model B')
            with self.assertRaisesRegex(ValueError, 'Pi 5 Model B'):
                setup_rpi.main(['--preboot', '--dry-run'])
            self.model.write_text('Raspberry Pi 5 Model B')
            with patch.object(preboot.os, 'geteuid', return_value=1000), \
                    self.assertRaisesRegex(ValueError, 'through sudo'):
                setup_rpi.main(['--preboot'])
        self.assertFalse(self.lock.exists())
        self.run.assert_not_called()

    def test_preboot_rejects_profile_and_software_arguments(self):
        with patch('sys.stderr', new=io.StringIO()), self.assertRaises(SystemExit) as exc:
            setup_rpi.main(['--preboot', '--profile', 'HOME', '--apt-upgrade'])
        self.assertEqual(exc.exception.code, 2)
        self.run.assert_not_called()

    def test_normal_plan_and_dry_run_preview_both_parts_without_writes(self):
        before = self.firmware.stat()
        for args, profile in ((['--plan'], 'GENERAL'), (['--dry-run', '--profile', 'HOME'], 'HOME')):
            output = io.StringIO()
            with self.subTest(args=args), redirect_stdout(output), \
                    patch.object(sys.stdin, 'isatty', return_value=False), \
                    patch.object(os, 'geteuid', return_value=1000):
                self.assertEqual(setup_rpi.main(args, self.host), 0)
                for expected in (f'profile: {profile}', 'I²C firmware setting:', 'SPI firmware setting:',
                                 'schedule i2c-dev at boot', 'Finnish', 'Reboot required before software installation',
                                 'Primary administrator', 'Scientific Python 3.14', 'PLAN ONLY:'):
                    self.assertIn(expected, output.getvalue())
        for path in (self.lock, self.keyboard, self.module_file, self.reboot_marker):
            self.assertFalse(path.exists())
        self.assertEqual(list(self.firmware.parent.iterdir()), [self.firmware])
        self.assertEqual(self.firmware.stat().st_mtime_ns, before.st_mtime_ns)
        self.run.assert_not_called()
        self.ensure_user.assert_not_called()
        self.assertEqual(self.host.calls, [])

    def test_two_stage_install_applies_keyboard_after_approval_and_resumes_after_reboot(self):
        def answer(prompt,default):
            if prompt.startswith('Reboot now'):
                self.assertEqual(self.firmware.read_text(), ENABLED + STOCK)
                self.assertEqual(self.module_file.read_text(), 'i2c-dev\n')
                self.assertTrue(self.keyboard.exists())
                self.run.assert_called_once_with([str(self.keyboard), 'fi'], check=True)
                return 'n'
            if prompt.startswith('Profile GENERAL'):
                return 'HOME'
            if prompt.startswith('Apply this installation plan?'):
                return 'y'
            self.fail(f'unexpected question: {prompt}')
        output = io.StringIO()
        def initial_answer(prompt, default):
            if not prompt.startswith('Reboot now'):
                self.assertEqual(self.firmware.read_text(), STOCK)
                self.assertFalse(self.module_file.exists())
                self.assertFalse(self.keyboard.exists())
                self.run.assert_not_called()
            return answer(prompt, default)
        with redirect_stdout(output), patch.object(sys.stdin, 'isatty', return_value=True), \
                patch.object(setup_rpi,'ask',side_effect=initial_answer) as prompt:
            self.assertEqual(setup_rpi.main([], self.host), 0)
            self.assertEqual([entry.args[0] for entry in prompt.call_args_list],
                             ['Profile GENERAL / HOME / AALTO','Apply this installation plan? y/N/customize/share','Reboot now? y/N'])
        self.assertIn('Software installation is paused',output.getvalue())
        self.assertIn('INSTALLATION PLAN',output.getvalue())
        self.ensure_user.assert_not_called()
        self.assertEqual(self.host.calls,[])

        self.reboot_marker.unlink()
        (self.dev/'spidev0.0').touch()
        self.char_device.return_value = True
        self.layout_pending.return_value = False
        output = io.StringIO()
        with redirect_stdout(output), patch.object(sys.stdin, 'isatty', return_value=True), \
                patch.object(setup_rpi,'ask',side_effect=answer) as prompt:
            self.assertEqual(setup_rpi.main([], self.host), 0)
            self.assertEqual(prompt.call_count,2)
        self.ensure_user.assert_called_once_with('alice', admin=True, passwordless=True)
        self.assertIn(['bash', str(setup_rpi.HERE / 'pre_home.sh')], self.host.calls)
        self.assertIn(['hostnamectl', '--static'], self.host.calls)
        self.assertFalse(any('reboot' in command for command in self.host.calls))
        report = output.getvalue()
        self.assertIn('PASS preboot', report)
        self.assertIn('Both interface device nodes are present', report)

    def test_declining_combined_plan_leaves_preboot_and_profile_untouched(self):
        with redirect_stdout(io.StringIO()), patch.object(sys.stdin, 'isatty', return_value=True), \
                patch('builtins.input', return_value='n'):
            self.assertEqual(setup_rpi.main(['--profile', 'GENERAL'], self.host), 0)
        self.assertEqual(self.firmware.read_text(), STOCK)
        for path in (self.lock, self.keyboard, self.module_file, self.reboot_marker):
            self.assertFalse(path.exists())
        self.run.assert_not_called()
        self.ensure_user.assert_not_called()
        self.assertEqual(self.host.calls, [])

    def test_configured_pi5_continues_with_aalto_without_reboot(self):
        self.firmware.write_text(ENABLED + STOCK)
        self.legacy_modules.write_text('i2c-dev\n')
        self.layout_pending.return_value = False
        self.keyboard.write_bytes(preboot.SOURCE.read_bytes())
        self.keyboard.chmod(0o755)
        self.preference.parent.mkdir(mode=0o700)
        self.preference.write_text('{"version":1,"layout":"us"}')
        self.preference.chmod(0o600)
        (self.dev / 'spidev0.0').touch()
        self.char_device.return_value = True
        before = self.firmware.stat()
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(setup_rpi.main(['--profile', 'AALTO', '--yes'], self.host), 0)
        self.assertIn(['bash', str(setup_rpi.HERE / 'pre_aalto.sh')], self.host.calls)
        self.assertIn('No changes needed.', output.getvalue())
        self.assertIn('No reboot required', output.getvalue())
        self.assertEqual(self.firmware.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(list(self.firmware.parent.iterdir()), [self.firmware])

    def test_pending_boot_blocks_even_yes_and_requires_explicit_reboot_confirmation(self):
        args=['--profile','GENERAL','--yes']
        with redirect_stdout(io.StringIO()), patch.object(sys.stdin,'isatty',return_value=False), \
                patch.object(setup_rpi,'ask') as prompt:
            self.assertEqual(setup_rpi.main(args,self.host),0)
            prompt.assert_not_called()
        (self.dev/'spidev0.0').touch()
        self.char_device.return_value=True
        with redirect_stdout(io.StringIO()), patch.object(sys.stdin,'isatty',return_value=True), \
                patch.object(setup_rpi,'ask',return_value='yes') as prompt:
            self.assertEqual(setup_rpi.main(args,self.host),0)
            prompt.assert_called_once_with('Reboot now? y/N','n')
        self.assertEqual(self.host.calls,[['systemctl','reboot']])
        self.ensure_user.assert_not_called()
        self.assertEqual(len(list(self.firmware.parent.glob('*.bak.*'))),1)

    def test_missing_devices_after_reboot_stop_without_another_reboot_prompt(self):
        self.firmware.write_text(ENABLED+STOCK)
        self.legacy_modules.write_text('i2c-dev\n')
        output=io.StringIO()
        with redirect_stdout(output), patch.object(sys.stdin,'isatty',return_value=True), \
                patch.object(setup_rpi,'ask') as prompt:
            self.assertEqual(setup_rpi.main([], self.host),1)
            prompt.assert_not_called()
        self.assertIn('device nodes are missing',output.getvalue())
        self.assertEqual(self.host.calls,[])

    def test_pi4_profile_installation_prepares_keyboard_without_editing_firmware(self):
        self.host.data['model'] = 'Raspberry Pi 4 Model B'
        with redirect_stdout(io.StringIO()), patch.object(self.host, 'run_preboot',return_value=(preboot.BootStatus.READY,'fi')) as run_preboot:
            self.assertEqual(setup_rpi.main(['--profile', 'GENERAL', '--yes'], self.host), 0)
        run_preboot.assert_called_once_with(preview=False,layout=None,interactive=sys.stdin.isatty(),firmware=False)
        self.assertIn(['bash', str(setup_rpi.HERE / 'pre_profile.sh'), 'GENERAL'], self.host.calls)

    def test_bad_firmware_and_incompatible_keyboard_fail_before_modifying_persistent_files(self):
        with redirect_stdout(io.StringIO()):
            self.firmware.write_text('include usercfg.txt\n')
            with self.assertRaisesRegex(ValueError, 'include'):
                setup_rpi.main(['--preboot'])
            self.firmware.write_text(STOCK)
            self.backend.side_effect = ValueError('incompatible keyboard')
            with self.assertRaisesRegex(ValueError, 'incompatible keyboard'):
                setup_rpi.main(['--preboot'])
        self.assertEqual(list(self.firmware.parent.iterdir()), [self.firmware])
        self.assertFalse(self.module_file.exists())
        self.assertFalse(self.keyboard.exists())
        self.run.assert_not_called()

    def test_german_selection_persists_and_later_manual_swedish_choice_is_kept(self):
        with redirect_stdout(io.StringIO()), patch('builtins.input',return_value='3') as choose:
            _,layout=preboot.run(plan=False,interactive=True)
        self.assertEqual(layout,'de')
        choose.assert_called_once()
        self.assertIn('"layout": "de"',self.preference.read_text())
        self.current_layout='se'
        with redirect_stdout(io.StringIO()), patch('builtins.input',side_effect=AssertionError('rerun must not prompt')):
            _,layout=preboot.run(plan=False,interactive=True)
        self.assertEqual(layout,'se')
        self.assertIn('"layout": "se"',self.preference.read_text())
        self.run.assert_called_once_with([str(self.keyboard),'de'],check=True)

    def test_keyboard_execution_failure_leaves_boot_configuration_intact(self):
        self.run.side_effect = subprocess.CalledProcessError(1, ['rpi-keyboard', 'fi'])
        with redirect_stdout(io.StringIO()), self.assertRaises(subprocess.CalledProcessError):
            setup_rpi.main(['--preboot'])
        self.assertEqual(self.firmware.read_text(), STOCK)
        self.assertFalse(self.module_file.exists())

    def test_firmware_replace_failure_preserves_original_and_backup(self):
        real_replace = os.replace

        def replace(source, destination):
            if destination == self.firmware:
                raise OSError('simulated firmware rename failure')
            return real_replace(source, destination)

        with patch.object(preboot.os, 'replace', side_effect=replace), redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(OSError, 'simulated firmware rename failure'):
            setup_rpi.main(['--preboot'])
        self.assertEqual(self.firmware.read_text(), STOCK)
        backups = list(self.firmware.parent.glob('*.bak.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), STOCK)
        self.assertEqual(list(self.firmware.parent.glob('.config.txt.*')), [])

    def test_concurrent_config_edit_is_preserved(self):
        before = preboot.file_state(self.firmware)
        self.firmware.write_text('# external edit\n' + STOCK)
        with self.assertRaisesRegex(ValueError, 'changed during preboot'):
            preboot.replace_file(self.firmware, before, ENABLED.encode(), 0o640,
                                 os.getuid(), os.getgid(), backup=True)
        self.assertEqual(self.firmware.read_text(), '# external edit\n' + STOCK)
        self.assertEqual(list(self.firmware.parent.iterdir()), [self.firmware])

    def test_unmounted_firmware_and_symlink_are_refused(self):
        with patch.object(Path, 'is_mount', return_value=False), redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(ValueError, 'mounted Raspberry Pi boot partition'):
            setup_rpi.main(['--preboot', '--plan'])
        other = self.firmware.with_name('other.txt')
        self.firmware.rename(other)
        self.firmware.symlink_to(other)
        with redirect_stdout(io.StringIO()), self.assertRaises(OSError):
            setup_rpi.main(['--preboot'])
        self.assertEqual(other.read_text(), STOCK)
        self.run.assert_not_called()
