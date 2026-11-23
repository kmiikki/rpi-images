"""Select the installed Qt platform for the lab314 Spyder process."""

from functools import wraps
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import sys
import tempfile

TRACE_OPTION = '--rpi-desktop-diagnostics'
SESSION_KEYS = ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_SESSION_TYPE', 'XDG_CONFIG_HOME',
                'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'SPYDER_CONFDIR', 'SPYDER_SAFE_MODE',
                'JUPYTER_CONFIG_DIR', 'JUPYTER_RUNTIME_DIR', 'IPYTHONDIR', 'MPLCONFIGDIR',
                'CONDA_EXE', 'CONDA_PREFIX', 'QT_API', 'QT_QPA_PLATFORM', 'QT_PLUGIN_PATH',
                'QT_QPA_PLATFORM_PLUGIN_PATH', 'ARROW_DEFAULT_MEMORY_POOL')


def environment_summary(source, sanitized):
    return {key: ('launcher-changed' if source.get(key)!=sanitized.get(key) else
                  'inherited' if key in source else 'unset') for key in SESSION_KEYS}


def isolated_environment(source, prefix, conda=Path('/opt/conda/bin/conda')):
    env = source.copy()
    for key in ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'PYTHONHOME', 'PYTHONPATH', 'QT_API',
                'QT_QPA_PLATFORM', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH',
                'QTWEBENGINEPROCESS_PATH', 'QTWEBENGINE_RESOURCES_PATH', 'QTWEBENGINE_LOCALES_PATH',
                'QTWEBENGINE_DISABLE_SANDBOX', 'QTWEBENGINE_CHROMIUM_FLAGS'):
        env.pop(key, None)
    env['PATH'] = os.pathsep.join((str(prefix/'bin'), env.get('PATH') or os.defpath))
    env['PYTHONNOUSERSITE'] = '1'
    if os.access(conda, os.X_OK):
        # Spyder's console plugin launches Conda environments via conda run.
        env['CONDA_EXE'] = str(conda)
        env.pop('MAMBA_EXE', None)
    if (platform.machine() in ('aarch64', 'arm64') and os.sysconf('SC_PAGE_SIZE')>4096
            and env.get('ARROW_DEFAULT_MEMORY_POOL', '').lower()=='jemalloc'):
        env['ARROW_DEFAULT_MEMORY_POOL'] = 'system'
    return env


def platform_plugins():
    from qtpy import API_NAME
    from qtpy.QtCore import QLibraryInfo, qVersion

    path = getattr(QLibraryInfo, 'path', None) or QLibraryInfo.location
    directory = Path(path(QLibraryInfo.PluginsPath))/'platforms'
    plugins = {library.stem.removeprefix('libq'): library for library in directory.glob('libq*.so')}
    if 'wayland-generic' in plugins:
        plugins.setdefault('wayland', plugins['wayland-generic'])
    return API_NAME, qVersion(), directory, plugins


def select_platform(env, plugins):
    if env.get('WAYLAND_DISPLAY') and 'wayland' in plugins:
        return 'wayland'
    if env.get('DISPLAY') and 'xcb' in plugins:
        return 'xcb'
    if env.get('WAYLAND_DISPLAY'):
        raise ValueError('Spyder Qt has no Wayland plugin or usable XWayland display. Check desktop XWayland.')
    raise ValueError('Spyder needs a desktop display and a compatible Qt platform plugin.')


def preserve_arrow_warning(original):
    """Keep the native warning visible without treating it as a kernel failure."""
    # Spyder later redirects sys.stderr to its internal issue reporter.
    diagnostic_stream = sys.stderr

    @wraps(original)
    def is_benign_error(self, message):
        if message.strip()=='<jemalloc>: Unsupported system page size':
            print(message.rstrip(), file=diagnostic_stream, flush=True)
            return True
        return original(self,message)
    return is_benign_error


def enable_console_compatibility():
    # Spyder 6.1.8 shuts down a starting kernel on unrecognized stderr. Its
    # peers' normal error handling still applies to every other output line.
    if platform.machine() not in ('aarch64','arm64') or os.sysconf('SC_PAGE_SIZE')<=4096 or version('spyder')!='6.1.8':
        return False
    from spyder.plugins.ipythonconsole.widgets.client import ClientWidget
    ClientWidget.is_benign_error = preserve_arrow_warning(ClientWidget.is_benign_error)
    return True


def interpreter_state(configured, executable):
    if not isinstance(configured, str) or not configured:
        return 'unset'
    try:
        return 'lab314' if os.path.samefile(configured,executable) else 'different executable'
    except OSError:
        return 'missing or inaccessible'


def console_preferences(config, executable):
    def get(section, option):
        return config.get(section,option,default=None)
    return dict(
        single_instance=bool(get('main','single_instance')),
        default_interpreter=bool(get('main_interpreter','default')),
        custom_interpreter=bool(get('main_interpreter','custom')),
        saved_interpreter=interpreter_state(get('main_interpreter','custom_interpreter'),executable),
        effective_interpreter=interpreter_state(get('main_interpreter','executable'),executable),
        custom_conda=bool(get('main_interpreter','custom_conda')),
        startup_commands=bool(get('ipython_console','startup/run_lines')),
        startup_file=bool(get('ipython_console','startup/use_run_file')),
    )


def console_snapshot(window, plugins):
    console = window.get_plugin(plugins.IPythonConsole,error=False)
    projects = window.get_plugin(plugins.Projects,error=False)
    snapshot = {'saved_project_open': bool(projects and projects.get_active_project()),
                'console_plugin': console is not None}
    if console is None:
        return snapshot
    client = console.get_current_client()
    shell = getattr(client,'shellwidget',None)
    handler = getattr(shell,'kernel_handler',None)
    manager = getattr(handler,'kernel_manager',None)
    process = getattr(getattr(manager,'provisioner',None),'process',None)
    snapshot.update(tabs=len(console.get_widget().clients), active_tab=client is not None,
                    startup_error=bool(getattr(client,'error_text',None)),
                    state=str(getattr(handler,'connection_state','none')),
                    kernel_ready=bool(getattr(shell,'spyder_kernel_ready',False)),
                    prompt_present=bool(getattr(shell,'_prompt_html',None)),
                    process_pid=process.pid if process is not None else None,
                    process_status=process.poll() if process is not None else None)
    return snapshot


class DesktopTrace:
    def __init__(self):
        fd, path = tempfile.mkstemp(prefix=f'rpi-spyder-desktop-{os.getuid()}-',suffix='.jsonl',dir='/tmp')
        self.log = os.fdopen(fd,'w',encoding='utf-8',buffering=1)
        self.path = path
        self.window_seen = False
        print(f'Normal desktop trace: {path}',flush=True)

    def record(self, event, **data):
        self.log.write(json.dumps(dict(event=event,**data), sort_keys=True)+'\n')

    def observe_application(self):
        from qtpy.QtCore import QTimer
        from spyder.api.plugins import Plugins
        from spyder.app import utils
        from spyder.config.manager import CONF

        self.record('normal-profile',**console_preferences(CONF,sys.executable))
        original = utils.create_application

        @wraps(original)
        def create_application(*args,**kwargs):
            app = original(*args,**kwargs)
            self.record('application',platform=app.platformName())
            timer = QTimer(app)
            previous = None

            def sample():
                nonlocal previous
                window = getattr(app,'_main_window',None)
                if window is None:
                    return
                self.window_seen = True
                try:
                    state = console_snapshot(window,Plugins)
                except (AttributeError, RuntimeError, TypeError) as error:
                    self.record('observation-unavailable', error_type=type(error).__name__)
                    timer.stop()
                    return
                if state!=previous:
                    self.record('normal-console',**state)
                    previous = state

            timer.timeout.connect(sample)
            timer.start(350)
            app.aboutToQuit.connect(timer.stop)
            return app

        utils.create_application = create_application


def main():
    if os.geteuid()==0:
        sys.exit('Launch Spyder from the desktop as your normal user.')
    tracing = TRACE_OPTION in sys.argv[1:]
    if tracing:
        sys.argv.remove(TRACE_OPTION)
    inherited = dict(os.environ)
    loader_keys = os.environ.pop('RPI_SPYDER_REMOVED_LOADER_KEYS','').split()
    trace = DesktopTrace() if tracing else None
    try:
        env = isolated_environment(os.environ, Path(sys.prefix))
        os.environ.update(env)
        for key in os.environ.keys()-env.keys():
            del os.environ[key]
        _, _, _, plugins = platform_plugins()
        os.environ['QT_QPA_PLATFORM'] = select_platform(env, plugins)
        from spyder.app.start import main as start_spyder
        compatibility = enable_console_compatibility()
        if trace:
            trace.record('launcher', profile='normal', pid=os.getpid(), spyder=version('spyder'),
                         executable=sys.executable, platform=os.environ['QT_QPA_PLATFORM'],
                         environment=environment_summary(inherited,os.environ),
                         loader_overrides=[key for key in loader_keys if key in
                                           ('LD_LIBRARY_PATH','LD_PRELOAD','PYTHONHOME','PYTHONPATH')],
                         warning_compatibility=compatibility)
            trace.observe_application()
        return start_spyder()
    except (ImportError, OSError, ValueError) as error:
        sys.exit(f'Spyder launcher: {error}')
    finally:
        if trace:
            trace.record('launcher-returned', window_seen=trace.window_seen)
            trace.log.close()


if __name__=='__main__':
    sys.exit(main())
