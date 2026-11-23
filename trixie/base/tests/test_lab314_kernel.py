"""Kernel diagnostics and an opt-in native 16 KiB ARM64 regression."""

import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

INSTALL = Path(__file__).resolve().parents[1]/'install'
sys.path.insert(0,str(INSTALL))
import lab314_kernel as kernel


class KernelDiagnosticsTests(unittest.TestCase):
    def test_started_process_and_fatal_signal_are_distinguished_with_output(self):
        for code, status in ((None,'still running'),(-11,'SIGSEGV (return code -11)'),(3,'status 3')):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                manager=Mock()
                manager.provisioner.process.poll.return_value=code

                def start(*, env, cwd, stdout, stderr):
                    self.assertEqual(cwd,root)
                    stdout.write(b'before initialization\n')
                    stdout.flush()
                    stderr.write(b'underlying error token=hidden\n')
                    stderr.flush()

                manager.start_kernel.side_effect=start
                manager.client.return_value.wait_for_ready.side_effect=RuntimeError('kernel_info failed')
                modules={'jupyter_client':SimpleNamespace(KernelManager=Mock(return_value=manager)),
                         'jupyter_client.kernelspec':SimpleNamespace(KernelSpecManager=Mock())}
                with patch.dict(sys.modules,modules),self.assertRaises(kernel.KernelProbeError) as failure:
                    kernel.probe_spyder_kernel(root,kernel.kernel_environment(root))
                message=str(failure.exception)
                for expected in ('kernel_info','page size',status,'Kernel stderr','underlying error',
                                 'Kernel stdout','before initialization','[redacted]'):
                    self.assertIn(expected,message)
                self.assertNotIn('hidden',message)
                manager.shutdown_kernel.assert_called_once_with(now=True)


@unittest.skipUnless(os.environ.get('LAB314_ARM64_16K_PREFIX'),'set LAB314_ARM64_16K_PREFIX on a native 16 KiB ARM64 kernel')
class Arm64PageSizeTests(unittest.TestCase):
    def test_spyder_kernel_starts_with_native_libraries_on_16k_pages(self):
        self.assertIn(platform.machine(),('aarch64','arm64'))
        self.assertEqual(os.sysconf('SC_PAGE_SIZE'),16384)
        prefix=Path(os.environ['LAB314_ARM64_16K_PREFIX']).resolve()
        result=subprocess.run([prefix/'bin/python','-IB',INSTALL/'check_lab314.py','--prefix',prefix,'--kernel-only'],
                              capture_output=True,text=True,timeout=150)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('page size: 16384 bytes',result.stdout)
        self.assertIn('PyArrow system pool: exited with status 0',result.stdout)
        self.assertIn('PyZMQ / libzmq: exited with status 0',result.stdout)
        self.assertIn('PASS Spyder kernel startup and scientific imports',result.stdout)
