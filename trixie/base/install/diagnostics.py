"""Persistent installer diagnostics without logging the process environment."""

from collections import deque
from datetime import datetime
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from installation_state import secure_directory

SECRET = re.compile(r"""(?i)(\b(?:password|passwd|token|api[_-]?key|secret|authorization)["']?\s*[=:]\s*)(?:bearer\s+)?(?:"[^"]*"|'[^']*'|[^\s&;,]+)""")
URL_AUTH = re.compile(r'(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+@')
URL_CONDA_TOKEN = re.compile(r'(?i)(https?://[^\s/]+/t/)[^/\s]+')


def redact(value):
    return SECRET.sub(r'\1[redacted]', URL_CONDA_TOKEN.sub(r'\1[redacted]', URL_AUTH.sub(r'\1[redacted]@', str(value))))


class CommandFailure(subprocess.CalledProcessError):
    def __init__(self, code, command, tail, log):
        super().__init__(code, command)
        self.tail = tail
        self.log = log

    def __str__(self):
        output = '\n'.join(self.tail) or '(No output was received.)'
        return f'Command failed ({self.returncode}): {shlex.join(self.cmd)}\n{output}\nDiagnostic log: {self.log}'


class Log:
    def __init__(self, state_directory):
        directory = state_directory/'logs'
        secure_directory(directory, create=True)
        fd, path = tempfile.mkstemp(prefix='install-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-', suffix='.log', dir=directory)
        self.path = Path(path)
        self.stream = os.fdopen(fd,'w',encoding='utf-8',buffering=1)
        self.stage = 'startup'

    def close(self):
        try:
            self.flush()
        finally:
            self.stream.close()

    def flush(self):
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def note(self, text):
        self.stream.write(redact(text)+'\n')

    def run(self, command, env, capture=False, **kwargs):
        command = [str(item) for item in command]
        safe = [redact(item) for item in command]
        self.note(f'[{self.stage}] $ {shlex.join(safe)}')
        tail = deque(maxlen=28)
        captured=[]
        log_error=None

        def record(line):
            nonlocal log_error
            if log_error is None:
                try:
                    self.note(line)
                except OSError as error:
                    log_error=error

        try:
            with subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, errors='replace', **kwargs) as proc:
                try:
                    for line in proc.stdout:
                        clean=redact(line.rstrip('\r\n'))
                        if clean.strip():
                            tail.append(clean[:2000])
                        record(clean)
                        if capture:
                            captured.append(clean+'\n')
                        else:
                            print(clean,flush=True)
                except BaseException:
                    if proc.poll() is None:
                        proc.terminate()
                    raise
                code=proc.wait()
        except OSError as error:
            code=1
            tail.append(redact(error))
            record(f'Unable to run command: {error}')
        record(f'[{self.stage}] exit {code}')
        if log_error is None:
            try:
                self.flush()
            except OSError as error:
                log_error=error
        if log_error is not None:
            tail.append(f'Diagnostic log could not be completed: {redact(log_error)}')
        if code:
            raise CommandFailure(code,safe,list(tail),self.path)
        if log_error is not None:
            raise log_error
        return subprocess.CompletedProcess(command,code,''.join(captured) if capture else None,'')
