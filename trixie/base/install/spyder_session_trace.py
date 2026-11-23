"""Trace local Spyder 6.1.8 console startup without recording private payloads."""

from functools import wraps
from importlib import metadata, util
import os
from pathlib import Path
import re
import signal
import sys
import time

import spyder_runtime as runtime


JEMALLOC_WARNING = '<jemalloc>: Unsupported system page size'
LOADER_KEYS = ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'PYTHONHOME', 'PYTHONPATH')
EXTRA_SESSION_KEYS = (*LOADER_KEYS, 'XDG_RUNTIME_DIR', 'JUPYTER_PATH', 'BASH_ENV', 'MPLBACKEND',
                      'QTWEBENGINEPROCESS_PATH', 'QTWEBENGINE_RESOURCES_PATH', 'QTWEBENGINE_LOCALES_PATH',
                      'QTWEBENGINE_CHROMIUM_FLAGS', 'QTWEBENGINE_DISABLE_SANDBOX')
KERNEL_MODULE = 'spyder_kernels.console'
RUNTIME = Path('/usr/local/lib/rpi-images/spyder_runtime.py')
DESKTOP = Path('/usr/local/share/applications/rpi-lab314-spyder.desktop')
HERE = Path(__file__).resolve().parent


def file_match(path, reference):
    try:
        return 'matches archive' if path.read_bytes() == reference.read_bytes() else 'differs from archive'
    except FileNotFoundError:
        return 'missing'
    except OSError:
        return 'unreadable'


def audit(launcher):
    return {
        'launcher': file_match(launcher, HERE.parent/'bin/rpi-lab314-spyder'),
        'runtime': file_match(RUNTIME, HERE/'spyder_runtime.py'),
        'desktop_file': file_match(DESKTOP, HERE.parent/'config/lab314/spyder.desktop'),
    }


def path_scope(path):
    path = Path(path).absolute()
    for name, root in (('scientific environment', Path(sys.prefix)), ('home', Path.home()),
                       ('temporary', Path('/tmp')), ('session runtime', Path('/run/user')/str(os.getuid()))):
        if path.is_relative_to(root.absolute()):
            return name
    return 'other'


def path_state(path):
    path = Path(path)
    try:
        info = path.stat()
        return dict(scope=path_scope(path), directory=path.is_dir(), owned=info.st_uid==os.getuid(),
                    mode=oct(info.st_mode & 0o777), writable=os.access(path,os.W_OK))
    except OSError as error:
        return dict(scope=path_scope(path), errno=error.errno)


def session_environment(before,after):
    return {**runtime.environment_summary(before,after), **{
        key: ('changed' if before.get(key)!=after.get(key) else 'present' if key in before else 'unset')
        for key in EXTRA_SESSION_KEYS}}


def output_categories(output):
    message = str(output)
    tests = {
        'jemalloc-page-size': JEMALLOC_WARNING in message,
        'chromium-page-allocator': 'page_allocator_internals_posix.h' in message,
        'qt-platform-plugin': 'Qt platform plugin' in message,
        'missing-module': 'ModuleNotFoundError' in message or isinstance(output, ModuleNotFoundError),
        'import-error': 'ImportError' in message or isinstance(output, ImportError),
        'permission-denied': 'Permission denied' in message or isinstance(output, PermissionError),
        'conda-error': 'CondaError' in message or 'conda executable' in message.lower(),
        'traceback': 'Traceback (most recent call last)' in message,
    }
    return [name for name, present in tests.items() if present] or ['other']


def error_details(error):
    if not isinstance(error, Exception):
        return {'categories': output_categories(error)}
    frames = []
    frame = error.__traceback__
    while frame:
        module = frame.tb_frame.f_globals.get('__name__','')
        if module.startswith(('spyder.','jupyter_client.','qtconsole.')):
            frames.append(f'{module}:{frame.tb_frame.f_code.co_name}:{frame.tb_lineno}')
        frame = frame.tb_next
    return dict(error_type=type(error).__name__, errno=getattr(error,'errno',None),
                categories=output_categories(error), frames=frames)


def process_info(process):
    code = process.poll()
    result = dict(pid=process.pid, returncode=code)
    if code is not None and code < 0:
        try:
            result['signal'] = signal.Signals(-code).name
        except ValueError:
            result['signal'] = -code
    return result


def kernel_process(manager):
    return getattr(getattr(manager,'provisioner',None),'process',None)


def kernel_pid(manager):
    return getattr(kernel_process(manager),'pid',None)


def is_kernel_command(args):
    for index, pair in enumerate(zip(args,args[1:])):
        if pair == (b'-m',KERNEL_MODULE.encode()):
            # A Conda or shell wrapper can carry the same arguments, but its
            # own command or script appears before Python's module flag.
            return index>0 and all(arg.startswith(b'-') for arg in args[1:index])
    return False


def kernel_children(root):
    """Find the real Python under conda run. Never return cmdlines or file names."""
    remaining = [root]
    for _ in range(32):
        if not remaining:
            return
        pid = remaining.pop()
        location = Path('/proc')/str(pid)
        try:
            args = (location/'cmdline').read_bytes().split(b'\0')
            if is_kernel_command(args):
                executable = runtime.interpreter_state(str(location/'exe'),sys.executable)
                if executable != 'unset':
                    yield pid, executable
            remaining.extend(int(child) for child in (location/'task'/str(pid)/'children').read_text().split())
        except OSError:
            continue


def wrap(owner, method, before, after=None):
    original = getattr(owner,method)

    @wraps(original)
    def wrapped(obj,*args,**kwargs):
        before(obj,*args,**kwargs)
        result = original(obj,*args,**kwargs)
        if after is not None:
            after(obj,result,*args,**kwargs)
        return result

    setattr(owner,method,wrapped)


class SessionTrace(runtime.DesktopTrace):
    def __init__(self):
        self.started = time.monotonic()
        super().__init__()
        self.processes = {}
        self.children = set()

    def record(self,event,**data):
        if event=='normal-console':
            data['gui_webengine_imported'] = any(f'{package}.QtWebEngineWidgets' in sys.modules
                                                 for package in ('qtpy','PyQt5','PyQt6'))
        super().record(event,seconds=round(time.monotonic()-self.started,3),**data)
        if event in ('normal-console','launcher-returned'):
            self.poll_processes()

    def poll_processes(self):
        for pid, process in list(self.processes.items()):
            state = process_info(process)
            if state['returncode'] is not None:
                self.record('kernel-process-exited',**state)
                del self.processes[pid]
                continue
            for child, executable in kernel_children(pid):
                if child not in self.children:
                    self.record('kernel-python-observed',pid=child,launcher_pid=pid,executable=executable)
                    self.children.add(child)

    def observe_application(self):
        from spyder.config.base import get_conf_path, get_safe_mode
        from spyder.widgets.reporterror import SpyderErrorDialog

        profile_dir = Path(get_conf_path())
        self.record('configuration', kind=('safe-mode' if get_safe_mode() else
                    'configured override' if os.environ.get('SPYDER_CONFDIR') else 'normal XDG profile'),
                    location=path_state(profile_dir),
                    existing_preferences=(profile_dir/'config/spyder.ini').is_file())
        self.install_kernel_hooks()
        wrap(SpyderErrorDialog,'append_traceback',lambda _dialog,text:self.internal_error(text))
        super().observe_application()
        from qtpy.QtCore import QCoreApplication, QTimer, qVersion
        from spyder.app import utils

        # create_application is a module function and is also wrapped by DesktopTrace.
        original = utils.create_application
        @wraps(original)
        def create_application(*args,**kwargs):
            app = original(*args,**kwargs)
            self.record('qt-library-paths', version=qVersion(),
                        paths=[path_scope(p) for p in QCoreApplication.libraryPaths()])
            timer = QTimer(app)
            timer.timeout.connect(self.poll_processes)
            timer.start(250)
            app.aboutToQuit.connect(timer.stop)
            return app
        utils.create_application = create_application

    def install_kernel_hooks(self):
        from jupyter_client.provisioning.local_provisioner import LocalProvisioner
        from jupyter_core.paths import jupyter_config_dir, jupyter_runtime_dir
        from spyder.plugins.ipythonconsole.plugin import IPythonConsole
        from spyder.plugins.ipythonconsole.utils.client import SpyderKernelClient
        from spyder.plugins.ipythonconsole.utils.kernel_handler import KernelHandler
        from spyder.plugins.ipythonconsole.widgets.client import ClientWidget
        from spyder.plugins.ipythonconsole.widgets.main_widget import IPythonConsoleWidget
        from spyder.plugins.ipythonconsole.widgets.shell import ShellWidget

        self.record('jupyter-paths',config=path_state(jupyter_config_dir()),
                    runtime=path_state(jupyter_runtime_dir()))
        wrap(IPythonConsole,'on_mainwindow_visible',lambda *_:self.record('console-plugin-visible'))
        wrap(IPythonConsoleWidget,'create_new_client',lambda *a,**kw:self.record('console-requested'))
        wrap(IPythonConsoleWidget,'_connect_new_client_to_kernel',
             lambda *a,**kw:self.record('kernel-requested'))
        wrap(IPythonConsoleWidget,'close_client',lambda *a,**kw:self.record('console-tab-closing'))
        wrap(IPythonConsoleWidget,'_create_info_widget',lambda *_:None,self.observe_console_renderer)
        wrap(ClientWidget,'show_kernel_error',lambda _,error:self.record('spyder-kernel-error',**error_details(error)))
        wrap(ClientWidget,'is_benign_error',lambda *_:None,self.warning_checked)
        wrap(SpyderKernelClient,'start_channels',
             lambda client,*a,**kw:self.record('jupyter-channels-starting',pid=kernel_pid(client.parent)),
             lambda client,*a,**kw:self.record('jupyter-channels-started',pid=kernel_pid(client.parent),
                                               running=client.channels_running))
        wrap(SpyderKernelClient,'_handle_kernel_info_reply',
             lambda client,*a,**kw:self.record('jupyter-kernel-info-reply',pid=kernel_pid(client.parent)))
        wrap(KernelHandler,'check_spyder_kernel_info',lambda *_:None,self.kernel_info)
        wrap(KernelHandler,'handle_comm_ready',
             lambda handler:self.record('spyder-comm-ready',pid=kernel_pid(handler.kernel_manager)))
        wrap(KernelHandler,'close',self.kernel_close)
        wrap(ShellWidget,'connect_kernel',
             lambda _,handler,*a,**kw:self.record('console-widget-connecting',pid=kernel_pid(handler.kernel_manager)),
             lambda _,result,handler,*a,**kw:self.record('console-widget-attached',pid=kernel_pid(handler.kernel_manager)))

        new_connection_file = KernelHandler.new_connection_file
        @wraps(new_connection_file)
        def connection_file():
            path = new_connection_file()
            self.record('connection-file-allocation', allocated=path is not None,
                        runtime=path_state(jupyter_runtime_dir()))
            return path
        KernelHandler.new_connection_file = staticmethod(connection_file)

        launch_kernel = LocalProvisioner.launch_kernel
        @wraps(launch_kernel)
        async def launch(provisioner,cmd,**kwargs):
            if KERNEL_MODULE not in cmd:
                return await launch_kernel(provisioner,cmd,**kwargs)
            index = cmd.index(KERNEL_MODULE)
            # The spec can include a Conda wrapper and Python flags before -m.
            python = next((arg for arg in reversed(cmd[:index-1])
                           if Path(arg).name.startswith('python')),None)
            wrapper = Path(cmd[0]).name
            file = cmd[index+2] if cmd[index+1:index+2]==['-f'] and len(cmd)>index+2 else None
            self.record('kernel-spawning',python=runtime.interpreter_state(python,sys.executable),wrapper=wrapper if wrapper in
                        ('conda','mamba','micromamba') else 'other or direct Python',
                        cwd=path_scope(kwargs.get('cwd') or os.getcwd()),
                        connection_file=path_state(file) if file else None,
                        environment=session_environment(os.environ,kwargs.get('env') or os.environ))
            try:
                result = await launch_kernel(provisioner,cmd,**kwargs)
            except Exception as error:
                self.record('kernel-spawn-error',**error_details(error))
                raise
            self.processes[provisioner.process.pid] = provisioner.process
            self.record('kernel-process-created',pid=provisioner.process.pid)
            return result
        LocalProvisioner.launch_kernel = launch

    def observe_console_renderer(self,_widget,view):
        page = getattr(view,'page',None)
        renderer_exit = getattr(page(),'renderProcessTerminated',None) if page else None
        if renderer_exit is not None:
            renderer_exit.connect(lambda status,code:self.record(
                'console-webengine-renderer-exited',status=int(getattr(status,'value',status)),returncode=code))

    def internal_error(self,text):
        frames = re.findall(r'File "[^"\n]*/((?:spyder|spyder_kernels|qtconsole|jupyter_client)/'
                            r'[a-zA-Z0-9_/]+\.py)", line ([0-9]+)',text)
        exception = re.search(r'^([A-Za-z]+(?:Error|Exception|Warning)):',text,re.MULTILINE)
        self.record('spyder-internal-error',categories=output_categories(text), frames=frames[-20:],
                    exception=exception[1] if exception else None)

    def warning_checked(self,widget,accepted,message):
        handler = getattr(widget,'kernel_handler',None)
        self.record('kernel-stderr-decision',accepted=bool(accepted),
                    only_known_warning=message.strip()==JEMALLOC_WARNING,categories=output_categories(message),
                    pid=kernel_pid(getattr(handler,'kernel_manager',None)))

    def kernel_info(self,handler,_result,info):
        version, executable = info or (None,None)
        self.record('spyder-kernels-info',executable=runtime.interpreter_state(executable,sys.executable),
                    version=version if isinstance(version,str) and re.fullmatch(r'[0-9][0-9.a-z+!-]{0,30}',version) else None,
                    state=str(handler.connection_state),pid=kernel_pid(handler.kernel_manager))

    def kernel_close(self,handler,*args,**kwargs):
        process = kernel_process(handler.kernel_manager)
        self.record('kernel-close-requested',process=process_info(process) if process is not None else None,
                    shutdown=kwargs.get('shutdown_kernel',args[0] if args else True))


def trace_session(mode, launcher, desktop_entries, terminal_entry):
    trace = SessionTrace()
    try:
        files = audit(launcher)
        requested_qt = os.environ.get('QT_QPA_PLATFORM')
        trace.record('entry-points', launch=mode, installed=files, desktop_entries=desktop_entries,
                     terminal_spyder=terminal_entry, terminal_input=sys.stdin.isatty(), cwd=path_scope(os.getcwd()),
                     architecture=os.uname().machine, page_size=os.sysconf('SC_PAGE_SIZE'),
                     qt_requested=requested_qt if requested_qt in ('xcb','wayland','wayland-egl','offscreen')
                     else 'other' if requested_qt else 'unset',
                     loader_variables=[key for key in LOADER_KEYS if key in os.environ or
                                       key in os.environ.get('RPI_SPYDER_REMOVED_LOADER_KEYS','').split()],
                     installed_spyder_kernels=distribution_version('spyder-kernels'),
                     environment=session_environment(os.environ,os.environ))
        if metadata.version('spyder')!='6.1.8':
            raise ValueError('Detailed lifecycle tracing supports Spyder 6.1.8.')
        if mode == 'direct':
            sys.argv = [str(Path(sys.prefix)/'bin/spyder')]
            # Spyder parses its command line while importing its configuration.
            from spyder.app.start import main

            trace.record('direct-launcher', warning_compatibility=False)
            trace.observe_application()
            return main()

        if files['launcher'] != 'matches archive':
            raise ValueError('The installed launcher differs or is missing; collect the direct trace with --direct.')
        # The trace child was started with the verified shell launcher's loader environment.
        spec = util.spec_from_file_location('installed_spyder_runtime',RUNTIME)
        helper = util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        if not hasattr(helper,'DesktopTrace') or not hasattr(helper,'TRACE_OPTION'):
            raise ValueError('The installed helper lacks trace support; collect the direct trace with --direct.')
        helper.DesktopTrace = lambda:trace
        sys.argv = [str(RUNTIME),helper.TRACE_OPTION]
        return helper.main()
    except Exception as error:
        trace.record('diagnostic-stopped', **error_details(error))
        raise
    finally:
        if not trace.log.closed:
            trace.record('launcher-returned',window_seen=trace.window_seen)
            trace.log.close()


def distribution_version(package):
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None
