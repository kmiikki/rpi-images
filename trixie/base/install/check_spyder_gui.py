"""Run a read-only Spyder desktop diagnostic as the logged-in graphical user."""

import argparse
import configparser
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from diagnostics import redact
from lab314_kernel import process_status
from spyder_runtime import (environment_summary, isolated_environment,
                            platform_plugins, select_platform)
from spyder_session_trace import LOADER_KEYS, trace_session

LAUNCHER = Path('/usr/local/bin/rpi-lab314-spyder')
DESKTOP_ID = 'rpi-lab314-spyder.desktop'
CONDA_DESKTOP_ID = 'conda-spyder_spyder-6-lab314.desktop'


def desktop_candidates(env, home):
    user_data = Path(env.get('XDG_DATA_HOME') or home/'.local/share')
    data_dirs = [user_data,*(Path(item) for item in
                 (env.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share').split(':') if item)]
    found = []
    for directory in dict.fromkeys(data_dirs):
        for name in (DESKTOP_ID,CONDA_DESKTOP_ID,'spyder.desktop','org.spyder_ide.spyder.desktop'):
            path = directory/'applications'/name
            if not path.is_file():
                continue
            config = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                config.read(path)
                command = config.get('Desktop Entry','Exec',fallback='')
                hidden = config.getboolean('Desktop Entry','Hidden',fallback=False)
                no_display = config.getboolean('Desktop Entry','NoDisplay',fallback=False)
                entry = command.strip().split()
                kind = 'official launcher' if entry and entry[0]==str(LAUNCHER) else 'different launcher'
                found.append(dict(id=name, user_entry=directory==user_data,
                                  hidden=hidden, no_display=no_display, kind=kind))
            except (OSError,ValueError,configparser.Error):
                found.append(dict(id=name,user_entry=directory==user_data,kind='unreadable entry'))
    return found


def qt_platform(offscreen=False):
    binding, version, directory, plugins = platform_plugins()
    platform = 'offscreen' if offscreen else select_platform(os.environ, plugins)
    if platform not in plugins:
        raise ValueError(f'Qt platform {platform} is missing from {directory}')
    os.environ['QT_QPA_PLATFORM'] = platform
    print(f'Qt: {binding} {version}; plugin: {plugins[platform]}', flush=True)
    return platform


def probe(kind, offscreen):
    expected = qt_platform(offscreen)
    if kind == 'webengine':
        from qtpy.QtWebEngineWidgets import QWebEngineView
    from qtpy.QtCore import QTimer
    from qtpy.QtWidgets import QApplication

    app = QApplication([])
    if app.platformName()!=expected:
        raise ValueError(f'Expected Qt platform {expected}, loaded {app.platformName()}')
    print(f'Qt platform loaded: {app.platformName()}', flush=True)
    if kind=='platform':
        return 0
    view = QWebEngineView()
    print(f'WebEngine user agent: {view.page().profile().httpUserAgent()}', flush=True)
    mappings=Path('/proc/self/maps').read_text().splitlines()
    qt_libraries={line.split(maxsplit=5)[-1] for line in mappings if '/libQt' in line}
    for library in sorted(qt_libraries):
        print('Loaded Qt library:',library,flush=True)

    def loaded(ok):
        if ok:
            view.page().runJavaScript('6 * 7', lambda value: app.exit(0 if value==42 else 3))
        else:
            print('WebEngine failed to load local HTML', flush=True)
            app.exit(2)

    def crashed(status, code):
        print(f'WebEngine renderer terminated: {status}; exit code {code}', flush=True)
        app.exit(4)

    view.loadFinished.connect(loaded)
    view.renderProcessTerminated.connect(crashed)
    view.setHtml('<p>Local Spyder WebEngine diagnostic</p>')
    view.show()
    QTimer.singleShot(45000, lambda: app.exit(5))
    return app.exec()


def run_check(command, env, log, timeout):
    with subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          start_new_session=True, text=True, errors='replace') as child:
        try:
            output, _ = child.communicate(timeout=timeout)
            status = process_status(child.returncode)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            output, _ = child.communicate()
            status = f'timed out after {timeout}s'
    log.write_text(redact(output)+f'\nProcess: {status}\n')
    allocator_error = 'FATAL:page_allocator_internals_posix.h' in output
    return child.returncode==0 and not allocator_error, status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--offscreen', action='store_true', help='run an emulated smoke test without a desktop display')
    modes.add_argument('--normal', action='store_true', help='trace the installed launcher with the current Spyder profile')
    modes.add_argument('--direct', action='store_true', help='trace lab314’s plain spyder entry point with the current profile')
    parser.add_argument('--trace-child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--probe', choices=('platform','webengine'), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.geteuid()==0:
        raise ValueError('Run this diagnostic as the desktop user without sudo.')
    if args.probe:
        return probe(args.probe, args.offscreen)
    candidates = desktop_candidates(os.environ,Path.home())
    if args.normal or args.direct:
        mode = 'normal' if args.normal else 'direct'
        if not args.trace_child:
            env = os.environ.copy()
            flags = '-B'
            if args.normal:
                flags = '-IB'
                env['RPI_SPYDER_REMOVED_LOADER_KEYS'] = ' '.join(key for key in LOADER_KEYS if key in env)
                for key in LOADER_KEYS:
                    env.pop(key,None)
            os.execve(sys.executable,[sys.executable,flags,str(Path(__file__).resolve()),'--'+mode,'--trace-child'],env)
        entry = shutil.which('spyder')
        local = Path(sys.prefix)/'bin/spyder'
        terminal_entry = ('lab314 raw entry point' if entry and Path(entry).resolve()==local.resolve()
                          else 'another entry point' if entry else 'not on PATH')
        print('Tracing the current profile from this terminal. Close this Spyder window to finish.',flush=True)
        return trace_session(mode,LAUNCHER,candidates,terminal_entry)
    print('Desktop entry candidates, in search order:',json.dumps(candidates),flush=True)
    print('Normal desktop startup and current profile: NOT TESTED by this isolated diagnostic.',flush=True)
    os.umask(0o077)
    out = Path(tempfile.mkdtemp(prefix='rpi-spyder-gui-'))
    prefix = Path(sys.prefix)
    print('Diagnostic directory:', out, flush=True)
    print('Architecture:', os.uname().machine, 'page size:', os.sysconf('SC_PAGE_SIZE'), flush=True)
    env = isolated_environment(os.environ, prefix)
    for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME','JUPYTER_CONFIG_DIR','JUPYTER_RUNTIME_DIR',
                'IPYTHONDIR','MPLCONFIGDIR'):
        env[key] = str(out/key.lower())
    (out/'environment.json').write_text(json.dumps(dict(profile='isolated',
        environment=environment_summary(os.environ,env),desktop_entries=candidates),indent=2))
    for package in ('spyder','spyder-kernels','qt-main','qt-webengine','qt6-webengine','pyqt','pyqt6','pyqtwebengine'):
        for path in sorted((prefix/'conda-meta').glob(f'{package}-[0-9]*.json')):
            record = json.loads(path.read_text())
            print(path.stem, redact(record.get('channel','')), flush=True)
    command = [sys.executable, '-IB', '-X', 'faulthandler', str(Path(__file__).resolve())]
    mode = ['--offscreen'] if args.offscreen else []
    platform_ok, status = run_check([*command,*mode,'--probe','platform'], dict(env,QT_DEBUG_PLUGINS='1'),
                                   out/'qt-platform.log', 30)
    print(f'Qt platform: {"PASS" if platform_ok else "FAIL"} ({status})', flush=True)
    if not platform_ok:
        return 1
    web_ok, status = run_check([*command,*mode,'--probe','webengine'],env,out/'webengine.log',65)
    print(f'QtWebEngine rendering: {"PASS" if web_ok else "FAIL"} ({status})', flush=True)
    env['QT_QPA_PLATFORM'] = next(line.split(': ',1)[1] for line in (out/'qt-platform.log').read_text().splitlines()
                                  if line.startswith('Qt platform loaded: '))
    result_path = out/'gui'
    completed, status = run_check([sys.executable,'-B','-X','faulthandler',HERE.parent/'tests/spyder_gui_acceptance.py',
                                   result_path,'--default-interpreter','--interpreter',prefix/'bin/python'],
                                  env,out/'spyder.log',360)
    result = result_path/'result.json'
    evidence = json.loads(result.read_text()) if result.is_file() else {}
    console_ok = evidence.get('result')=='PASS' and evidence.get('closed')
    print(f'Isolated Spyder GUI startup: {"PASS" if evidence.get("gui_started") else "FAIL"}')
    print(f'Isolated Spyder IPython console: {"PASS" if console_ok else "FAIL"} ({status})')
    accepted = completed and console_ok and web_ok
    print(f'Isolated graphical smoke test: {"PASS" if accepted else "FAIL"}')
    print('Normal desktop graphical acceptance: PENDING')
    print('Diagnostic directory:', out)
    return int(not accepted)


if __name__=='__main__':
    try:
        sys.exit(main())
    except (ImportError, OSError, ValueError) as error:
        sys.exit(f'Spyder diagnostics: {redact(error)}')
