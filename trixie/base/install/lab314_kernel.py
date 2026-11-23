"""Run and diagnose the integrated Spyder kernel with its local process manager."""

import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys

from diagnostics import redact


class KernelProbeError(RuntimeError):
    """The kernel failed during startup or execution of the scientific check."""


def process_status(code):
    if code is None:
        return 'still running when the check failed'
    if code < 0:
        try:
            name = signal.Signals(-code).name
        except ValueError:
            name = str(-code)
        return f'terminated by {name} (return code {code})'
    return f'exited with status {code}'


def output_tail(path):
    try:
        with path.open('rb') as output:
            output.seek(max(os.fstat(output.fileno()).st_size - 12000, 0))
            return redact(output.read().decode('utf-8', errors='replace').strip()) or '(empty)'
    except OSError as error:
        return f'(could not read captured output: {redact(error)})'


def large_arm64_pages():
    return platform.machine() in ('aarch64', 'arm64') and os.sysconf('SC_PAGE_SIZE') > 4096


def kernel_environment(root):
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', MPLBACKEND='Agg',
               IPYTHONDIR=str(root/'ipython'), JUPYTER_CONFIG_DIR=str(root/'jupyter'),
               JUPYTER_RUNTIME_DIR=str(root/'runtime'), SPYDER_CONFDIR=str(root/'spyder'))
    for key in ('QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'QT_API'):
        env.pop(key, None)
    return env


def probe_spyder_kernel(root, env, *, timeout=45):
    from jupyter_client import KernelManager
    from jupyter_client.kernelspec import KernelSpecManager

    # A client attached only by a connection file guesses process liveness from
    # heartbeat packets. The local manager checks the actual child process.
    specs = root/'specs'
    spec = specs/'lab314-spyder'
    spec.mkdir(parents=True)
    spec.joinpath('kernel.json').write_text(json.dumps({
        'argv': [sys.executable, '-IB', '-X', 'faulthandler', '-m', 'spyder_kernels.console',
                 '-f', '{connection_file}'],
        'display_name': 'lab314 Spyder acceptance probe', 'language': 'python',
    }))
    manager = KernelManager(kernel_name=spec.name, ip='127.0.0.1', connection_file=str(root/'spyder-kernel.json'),
                            kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(specs)], ensure_native_kernel=False))
    stdout, stderr = root/'kernel.stdout', root/'kernel.stderr'
    client = None
    process = None
    phase = 'launch'
    with stdout.open('wb') as out, stderr.open('wb') as err:
        try:
            manager.start_kernel(env=env, cwd=root, stdout=out, stderr=err)
            process = manager.provisioner.process
            phase = 'kernel_info'
            client = manager.client()
            client.start_channels()
            client.wait_for_ready(timeout=timeout)
            phase = 'scientific imports and execution'
            reply = client.execute_interactive(
                'import os,sys,numpy,scipy,cv2,IPython; '
                f'assert sys.prefix == {sys.prefix!r}; '
                f'assert os.sysconf("SC_PAGE_SIZE") == {os.sysconf("SC_PAGE_SIZE")}; '
                'assert numpy.linalg.norm([3,4]) == 5; '
                'assert "/usr/lib/python3/dist-packages" not in sys.path', timeout=30)
            if reply['content']['status'] != 'ok':
                raise ValueError(reply['content'].get('evalue') or reply['content']['status'])
        except Exception as error:
            status = process_status(process.poll()) if process is not None else 'process did not start'
            raise KernelProbeError(
                f'Spyder kernel failed during {phase} on {platform.machine()}, '
                f'page size {os.sysconf("SC_PAGE_SIZE")} bytes: {status}.\n'
                f'{redact(error)}\nKernel stderr:\n{output_tail(stderr)}\nKernel stdout:\n{output_tail(stdout)}'
            ) from error
        finally:
            failure = sys.exception()
            try:
                try:
                    if client is not None:
                        client.stop_channels()
                finally:
                    if manager.has_kernel:
                        manager.shutdown_kernel(now=True)
            except Exception as error:
                if failure is None:
                    raise
                failure.add_note(f'Kernel cleanup failed: {redact(error)}')


def run_native_check(command, env, label, *, timeout=30):
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise KernelProbeError(f'{label} timed out after {timeout}s') from error
    if result.returncode:
        raise KernelProbeError(f'{label}: {process_status(result.returncode)}\n'
                               f'stderr:\n{redact(result.stderr)}\nstdout:\n{redact(result.stdout)}')
    return result


def diagnose_dependencies(prefix, env):
    print(f'Architecture: {platform.machine()}; page size: {os.sysconf("SC_PAGE_SIZE")} bytes', flush=True)
    for name in ('python','libarrow','pyarrow','ruff','zeromq','pyzmq','ipykernel','jupyter_client','spyder-kernels'):
        for record in sorted((prefix/'conda-meta').glob(f'{name}-[0-9]*.json')):
            print(record.stem)
    arrow = [sys.executable,'-IB','-X','faulthandler','-c',
             'import pyarrow as a; '
             'print(a.__version__, a.default_memory_pool().backend_name, a.array([1,2]).to_pylist()); '
             'from pathlib import Path; print(*sorted({x.split()[-1] for x in '
             'Path("/proc/self/maps").read_text().splitlines() if "/libarrow.so" in x}), sep="\\n")']
    probes = [
        ('PyArrow / libarrow', arrow, env),
        ('PyZMQ / libzmq', [sys.executable,'-IB','-X','faulthandler','-c',
          'import zmq; print(zmq.__version__, zmq.zmq_version())'], env),
    ]
    if large_arm64_pages():
        probes.append(('PyArrow system pool', arrow, dict(env, ARROW_DEFAULT_MEMORY_POOL='system')))
    if (prefix/'bin/ruff').is_file():
        probes.append(('Ruff', [prefix/'bin/ruff','--version'], env))
    for name, command, probe_env in probes:
        try:
            result = run_native_check(command, probe_env, name)
        except (OSError, KernelProbeError) as error:
            print(f'Native dependency diagnostic: {redact(error)}', flush=True)
        else:
            print(f'{name}: {process_status(result.returncode)}\n{redact(result.stdout).rstrip()}', flush=True)
            if result.stderr.strip():
                print(f'{name} stderr:\n{redact(result.stderr).rstrip()}', flush=True)
