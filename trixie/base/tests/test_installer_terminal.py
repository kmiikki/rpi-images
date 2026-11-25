"""Exercise the logger with shared terminal input/output and piped child output."""
import errno
import os
from pathlib import Path
import pty
import subprocess
import sys
import tempfile
import termios
import unittest

INSTALL = Path(__file__).resolve().parents[1]/'install'

DRIVER = """
from pathlib import Path
import os, sys
from diagnostics import CommandFailure, Log
log = Log(Path(sys.argv[1]))
try:
    log.run([sys.argv[2], sys.argv[3]], os.environ)
except CommandFailure as error:
    sys.exit(error.returncode)
except KeyboardInterrupt:
    sys.exit(130)
finally:
    log.close()
"""

CHILD = """#!/usr/bin/python3
import os, signal, sys, termios, time
assert sys.argv[1:5] == ['-o', 'Dpkg::Use-Pty=0', '-o', 'Dpkg::Progress-Fancy=0']
assert os.isatty(0) and not os.isatty(1) and not os.isatty(2)
attrs = termios.tcgetattr(0)
attrs[1] &= ~termios.OPOST
termios.tcsetattr(0, termios.TCSANOW, attrs)
os.write(1, b'Unpacking example\\r\\n')
os.write(2, b'Setting up example\\rprocessed trigger\\n')
if sys.argv[-1] == 'interrupt':
    time.sleep(.1)
    os.kill(os.getppid(), signal.SIGINT)
    time.sleep(10)
sys.exit(int(sys.argv[-1]))
"""


class TerminalTests(unittest.TestCase):
    def test_alignment_logging_exit_and_restoration(self):
        for mode,expected in [('0',0),('17',17),('interrupt',130)]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                apt=Path(tmp)/'apt-get'
                apt.write_text(CHILD)
                apt.chmod(0o700)
                master,slave=pty.openpty()
                try:
                    before=termios.tcgetattr(slave)
                    result=subprocess.run([sys.executable,'-B','-c',DRIVER,tmp,str(apt),mode],
                                          cwd=INSTALL,stdin=slave,stdout=slave,stderr=slave,timeout=8)
                    self.assertEqual(termios.tcgetattr(slave),before)
                    self.assertEqual(result.returncode,expected)
                    os.close(slave)
                    slave=None
                    output=bytearray()
                    try:
                        while chunk:=os.read(master,4096):
                            output.extend(chunk)
                    except OSError as error:
                        if error.errno!=errno.EIO:
                            raise
                finally:
                    os.close(master)
                    if slave is not None:
                        os.close(slave)
                lines=['Unpacking example','Setting up example','processed trigger']
                self.assertEqual(output, ('\r\n'.join(lines)+'\r\n').encode())
                log,=(Path(tmp)/'logs').glob('*.log')
                records=log.read_text().splitlines()
                for line in lines:
                    self.assertEqual(records.count(line),1)
                self.assertIn('interrupted' if mode=='interrupt' else f'exit {expected}', records[-1])
