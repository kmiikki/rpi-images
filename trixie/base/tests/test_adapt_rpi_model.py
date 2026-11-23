"""Model changes on test fixtures. Physical Pi 4 acceptance is separate."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_rpi_preboot import STOCK
import adapt_rpi_model as adapt
import preboot


STOCK_BOOT = 'auto_initramfs=1\narm_64bit=1\n'+STOCK


class ModelAdaptationTests(unittest.TestCase):
    def setUp(self):
        work=tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.boot=Path(work.name)
        self.config=self.boot/'config.txt'
        self.config.write_text(STOCK_BOOT)
        self.model=self.boot/'model'
        self.model.write_bytes(b'Raspberry Pi 4 Model B Rev 1.5\0')
        for _,dtb,compatible in adapt.BOARD.values():
            (self.boot/dtb).write_bytes(b'\xd0\x0d\xfe\xed'+b'\0'+compatible+b'\0')
        for filename in ('cmdline.txt','start4.elf','fixup4.dat'):
            (self.boot/filename).write_bytes(b'fixture')
        patchers=(
            patch.object(preboot,'MODEL',self.model), patch.object(preboot,'FIRMWARE',self.config),
            patch.object(preboot,'LOCK',self.boot/'lock'),
            patch.object(preboot,'check_host'), patch.object(preboot,'kernel_release',return_value='6.18.60+rpt-rpi-v8'),
            patch.object(Path,'is_mount',return_value=True), patch.object(adapt.platform,'release',return_value='6.18.60+rpt-rpi-v8'),
            patch.object(adapt.os,'sysconf',return_value=4096), patch.object(adapt.os,'geteuid',return_value=0),
        )
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def invoke(self,*args):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(adapt.main(args),0)
        return output.getvalue()

    def test_model_detection(self):
        self.assertEqual(adapt.model_id('Raspberry Pi 4 Model B Rev 1.5'),'pi4')
        self.assertEqual(adapt.model_id('Raspberry Pi 5 Model B Rev 1.0'),'pi5')
        for unsupported in ('Raspberry Pi 500','Raspberry Pi Compute Module 4','Generic PC'):
            with self.assertRaises(ValueError):
                adapt.model_id(unsupported)

    def test_prepare_pi4_to_pi5_and_back_without_reinstall(self):
        view=self.invoke('--target','pi5','--plan')
        self.assertIn('Boot change',view)
        self.assertFalse((self.boot/'lock').exists())
        self.assertEqual(self.config.read_text(),STOCK_BOOT)
        self.invoke('--target','pi5','--prepare','--yes')
        changed=self.config.read_text()
        self.assertEqual(changed.count('\nkernel=kernel8.img\n'),1)
        self.assertEqual(preboot.boot_settings(changed,'pi4').get('kernel'),None)
        self.assertTrue(changed.startswith(STOCK_BOOT))
        self.model.write_bytes(b'Raspberry Pi 5 Model B Rev 1.0\0')
        self.assertIn('Live kernel verified',self.invoke('--plan'))
        self.assertIn('No boot configuration edits',self.invoke('--target','pi4','--prepare','--yes'))
        self.model.write_bytes(b'Raspberry Pi 4 Model B Rev 1.5\0')
        self.assertIn('Live kernel verified',self.invoke('--plan'))
        self.assertEqual(self.config.read_text(),changed)
        self.assertEqual(len(list(self.boot.glob('*.adapt-model.bak.*'))),1)

    def test_pi5_to_pi4_preserves_an_unmodified_stock_config(self):
        self.model.write_bytes(b'Raspberry Pi 5 Model B\0')
        self.assertIn('No boot configuration edits',self.invoke('--target','pi4','--prepare','--yes'))
        self.assertEqual(self.config.read_text(),STOCK_BOOT)
        self.assertFalse(list(self.boot.glob('*.adapt-model.bak.*')))

    def test_rollback_requires_exact_current_file_and_keeps_an_undo_copy(self):
        self.invoke('--target','pi5','--prepare','--yes')
        backup,=self.boot.glob('*.adapt-model.bak.*')
        self.assertEqual(backup.read_text(),STOCK_BOOT)
        selected=self.config.read_bytes()
        self.invoke('--rollback',backup.name,'--plan')
        self.assertEqual(self.config.read_bytes(),selected)
        self.config.write_bytes(selected+b'# local camera setting\n')
        with self.assertRaisesRegex(ValueError,'changed since'):
            adapt.main(['--rollback',backup.name,'--yes'])
        self.config.write_bytes(selected)
        self.invoke('--rollback',backup.name,'--yes')
        self.assertEqual(self.config.read_text(),STOCK_BOOT)
        self.assertEqual({path.read_bytes() for path in self.boot.glob('*.adapt-model.bak.*')},
                         {STOCK_BOOT.encode(),selected})

    def test_missing_firmware_and_ambiguous_settings_stop_without_changes(self):
        (self.boot/'start4.elf').unlink()
        with self.assertRaisesRegex(ValueError,'start4.elf'):
            adapt.main(['--target','pi4','--plan'])
        for text in ('[pi5]\n[tryboot]\nkernel=kernel_2712.img\n',
                     '[pi5]\ndevice_tree=custom.dtb\n','[pi5]\ninclude firmware-local.txt\n'):
            with self.subTest(text=text),self.assertRaises(ValueError):
                adapt.adaptation(STOCK_BOOT+text,'pi5')
        self.assertEqual(self.config.read_text(),STOCK_BOOT)
