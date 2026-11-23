"""Regression tests for private tracing of Spyder's normal session."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import signal
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'install'))
import spyder_session_trace as trace


class SessionTraceTests(unittest.TestCase):
    def test_installed_helper_is_compared_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as work:
            helper = Path(work)/'spyder_runtime.py'
            source = trace.HERE/'spyder_runtime.py'
            helper.write_bytes(source.read_bytes())
            self.assertEqual(trace.file_match(helper,source),'matches archive')
            helper.write_bytes(b'changed')
            self.assertEqual(trace.file_match(helper,source),'differs from archive')
            self.assertEqual(trace.file_match(helper/'missing',source),'unreadable')
            self.assertEqual(trace.file_match(helper.with_suffix('.absent'),source),'missing')

    def test_reports_existing_runtime_obstruction_without_disclosing_path(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work)/'private project'
            self.assertEqual(trace.path_state(path),{'scope':'temporary','errno':2})
            path.touch(mode=0o600)
            state = trace.path_state(path)
            self.assertFalse(state['directory'])
            self.assertEqual(state['mode'],'0o600')
            self.assertNotIn(path.name,str(state))

    def test_mixed_stderr_does_not_look_like_an_accepted_standalone_warning(self):
        message = trace.JEMALLOC_WARNING+'\nModuleNotFoundError: credential=in-test'
        with redirect_stdout(io.StringIO()):
            session = trace.SessionTrace()
        path = Path(session.path)
        try:
            session.warning_checked(None,False,message)
            session.warning_checked(None,True,trace.JEMALLOC_WARNING+'\n')
            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertEqual(records[0]['categories'],['jemalloc-page-size','missing-module'])
            self.assertFalse(records[0]['only_known_warning'])
            self.assertFalse(records[0]['accepted'])
            self.assertTrue(records[1]['only_known_warning'])
            self.assertTrue(records[1]['accepted'])
            self.assertNotIn('credential=in-test',path.read_text())
        finally:
            session.log.close()
            path.unlink()

    def test_retains_real_exit_signal_after_spyder_drops_the_process_handle(self):
        with redirect_stdout(io.StringIO()):
            session = trace.SessionTrace()
        path = Path(session.path)
        try:
            session.processes[12] = SimpleNamespace(pid=12,poll=lambda:-signal.SIGSEGV)
            session.poll_processes()
            session.poll_processes()
            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(records),1)
            self.assertEqual(records[0]['event'],'kernel-process-exited')
            self.assertEqual(records[0]['returncode'],-signal.SIGSEGV)
            self.assertEqual(records[0]['signal'],'SIGSEGV')
        finally:
            session.log.close()
            path.unlink()

    def test_kernel_child_is_distinguished_from_conda_process(self):
        kernel = [b'/opt/lab314/bin/python',b'-Xfrozen_modules=off',b'-m',b'spyder_kernels.console']
        conda = [b'/opt/conda/bin/python',b'/opt/conda/bin/conda',b'run',*kernel]
        self.assertTrue(trace.is_kernel_command(kernel))
        self.assertFalse(trace.is_kernel_command(conda))

    def test_internal_dialog_preserves_safe_error_evidence(self):
        with redirect_stdout(io.StringIO()):
            session = trace.SessionTrace()
        path = Path(session.path)
        try:
            session.internal_error('Traceback (most recent call last):\n'
                                   '  File "/home/private/spyder/app/start.py", line 5, in main\n'
                                   'RuntimeError: token=sample-secret\n')
            entry = json.loads(path.read_text())
            self.assertEqual(entry['exception'],'RuntimeError')
            self.assertEqual(entry['frames'],[['spyder/app/start.py','5']])
            self.assertNotIn('sample-secret',path.read_text())
            self.assertNotIn('/home/private',path.read_text())
        finally:
            session.log.close()
            path.unlink()

    def test_installed_trace_runs_the_installed_helper_with_existing_profile(self):
        with tempfile.TemporaryDirectory() as work, redirect_stdout(io.StringIO()) as stdout:
            profile = str(Path(work)/'user-existing-profile')
            helper = Path(work)/'installed.py'
            helper.write_text("""
import os
DesktopTrace = object
TRACE_OPTION = '--diagnose'
def main():
    DesktopTrace().record('installed-helper-ran', has_profile=bool(os.environ.get('SPYDER_CONFDIR')))
""")
            with (patch.object(trace,'RUNTIME',helper),
                  patch.object(trace,'audit',return_value={'launcher':'matches archive','runtime':'differs from archive'}),
                  patch.object(trace.metadata,'version',return_value='6.1.8'),
                  patch.object(sys,'argv',[]),
                  patch.dict(os.environ,{'SPYDER_CONFDIR':profile})):
                trace.trace_session('normal',Path('/unused'),[],'not on PATH')
                self.assertEqual(os.environ['SPYDER_CONFDIR'],profile)
            path = Path(stdout.getvalue().strip().split(': ',1)[1])
            try:
                report = path.read_text()
                self.assertIn('"event": "installed-helper-ran"',report)
                self.assertIn('"has_profile": true',report)
                self.assertNotIn(profile,report)
                self.assertIn('"runtime": "differs from archive"',report)
            finally:
                path.unlink()


if __name__=='__main__':
    unittest.main()
