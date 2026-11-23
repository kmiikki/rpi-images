"""Explicit real-display Spyder 6 acceptance; not run by unittest discovery.

Run with the Python that supplies Spyder and Qt. Select its default interpreter
or an explicit kernel separately. Uses an isolated SPYDER_CONFDIR under a NEW output dir.
No packages, production configuration or interpreter files are modified.
"""
import argparse
import importlib.metadata as md
import json
import os
from pathlib import Path
import sys
import time
import traceback
import uuid

from spyder_acceptance_state import evaluate
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'install'))
from diagnostics import redact
from spyder_runtime import console_preferences, enable_console_compatibility

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--interpreter', default='/opt/lab314/bin/python')
parser.add_argument('--default-interpreter', action='store_true', help='test Spyder’s default selection against --interpreter')
parser.add_argument('--reference-without-shapely', action='store_true')
parser.add_argument('--negative-missing-variable', action='store_true')
args = parser.parse_args()
out = args.output
out.mkdir(parents=True, exist_ok=False)
os.environ['SPYDER_CONFDIR'] = str(out / 'config')
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
from spyder.config.manager import CONF
if not args.default_interpreter:
    for key, value in [('default', False), ('custom', True),
                       ('custom_interpreter', args.interpreter),
                       ('executable', args.interpreter)]:
        CONF.set('main_interpreter', key, value)
CONF.set('main', 'prompt_on_exit', False)
CONF.set('main', 'check_updates_on_startup', False)
enable_console_compatibility()
from spyder.app.utils import create_application, create_splash_screen, create_window
from spyder.app.mainwindow import MainWindow
from spyder.app.cli_options import get_options
from spyder.api.plugins import Plugins
from qtpy.QtCore import QTimer

real_exit = sys.exit  # Spyder patches sys.exit during application creation.
app = create_application()
state = dict(phase='startup', stage='first', started=time.monotonic(),
             deadline=time.monotonic() + 90, kernel=None, passed=[], result='FAIL')
events = []
observed_models = {}
observed_handlers = set()
children = {}
previous_console = None


def record(kind, **values):
    events.append(dict(kind=kind, t=round(time.monotonic() - state['started'], 3),
                       **values))
    (out / 'events.json').write_text(json.dumps(events, default=str, indent=2))


def observe_console(console, shell):
    global previous_console
    for client in console.get_widget().clients:
        handler = getattr(client.shellwidget, 'kernel_handler', None)
        if handler is None or handler in observed_handlers:
            continue
        manager = getattr(handler, 'kernel_manager', None)
        process = getattr(getattr(manager, 'provisioner', None), 'process', None)
        if process is not None:
            children[process.pid] = process
        observed_handlers.add(handler)
        for stream in ('stdout','stderr'):
            getattr(handler, f'sig_{stream}').connect(
                lambda message, stream=stream: record('kernel_'+stream, text=redact(message)[:12000]))
    handler = getattr(shell, 'kernel_handler', None)
    current = (len(console.get_widget().clients), str(getattr(handler, 'connection_state', 'none')))
    if current != previous_console:
        record('console-state', tabs=current[0], connection=current[1],
               children={pid: process.poll() for pid,process in children.items()})
        previous_console = current


def finish(error=None):
    timer.stop()
    if error:
        record('failure', error=error)
        (out / 'error.txt').write_text(error)
    else:
        state['result'] = 'PASS'
    window = getattr(app, '_main_window', None)
    if window is not None:
        window.grab().save(str(out / 'final-window.png'))
        try:
            if not window.close():
                raise RuntimeError('GUI refused close')
        except Exception:
            state['result'] = 'FAIL'
            (out / 'close-error.txt').write_text(traceback.format_exc())
    app.quit()


def submit(shell, ve):
    token = uuid.uuid4().hex
    offset = 100 if state['stage'] == 'second' else 0
    state.update(shell=shell, token=token, kernel=None, sent=time.monotonic(),
                 phase='verify', deadline=time.monotonic() + 30, requested=False)
    ve.switch_to_plugin()
    code = '''import os,sys,json,importlib.metadata as md,numpy as np
import scipy.linalg as la,cv2
import matplotlib.pyplot as plt
array_test=np.arange(12).reshape(3,4)+OFFSET
solution=la.solve([[2.,0],[0,4.]],[4.,8.])
SHAPELY
assert np.allclose(solution,[2,2]) and polygon_area==4.0
assert cv2.cvtColor(np.zeros((8,8,3),np.uint8),cv2.COLOR_BGR2GRAY).shape==(8,8)
plt.figure();plt.plot([0,1,2],[0,1,4]);plt.title('Lab314 Spyder acceptance');plt.show()
acceptance_state=dict(token=TOKEN,pid=os.getpid(),executable=sys.executable,python=sys.version,kernels=md.version('spyder-kernels'),ipython=md.version('ipython'),opencv=cv2.__version__,array=array_test.tolist(),area=polygon_area,shapely=SHAPELY_VERSION)
NEGATIVE
open(MARKER,'w').write(json.dumps(acceptance_state))
'''.replace('OFFSET', str(offset)).replace('TOKEN', repr(token))
    if args.reference_without_shapely:
        code = code.replace('SHAPELY_VERSION', "'NOT RUN (reference has no Shapely)'")
        code = code.replace('SHAPELY', 'polygon_area=4.0')
    else:
        code = code.replace('SHAPELY_VERSION', 'shapely.__version__')
        code = code.replace('SHAPELY', 'import shapely\nfrom shapely.geometry import Polygon\npolygon_area=Polygon([(0,0),(2,0),(2,2),(0,2)]).area')
    code = code.replace('NEGATIVE', 'del polygon_area' if args.negative_missing_variable else '')
    code = code.replace('MARKER', repr(str(out / (token + '.json'))))
    state['expected'] = dict(token=token, executable=args.interpreter,
                            array=[[offset + row * 4 + col for col in range(4)]
                                   for row in range(3)], area=4.0)
    record('submit', stage=state['stage'], ready=shell.spyder_kernel_ready,
           token=token, interpreter=args.interpreter)
    shell.execute(code)


def tick():
    try:
        now = time.monotonic()
        w = getattr(app, '_main_window', None)
        if w is None:
            if now > state['deadline']:
                raise TimeoutError('window startup')
            return
        state['gui_started'] = True
        console = w.get_plugin(Plugins.IPythonConsole)
        shell = console.get_current_shellwidget()
        observe_console(console, shell)
        ve = w.get_plugin(Plugins.VariableExplorer)
        if state['phase'] == 'startup':
            if shell is not None and shell.spyder_kernel_ready:
                if state['stage'] == 'first':
                    state['first'] = shell
                submit(shell, ve)
        elif state['phase'] == 'restart':
            # restart replaces the handler; a cached old model cannot qualify.
            if (shell is state['first'] and shell.kernel_handler is not state['old_handler']
                    and shell.spyder_kernel_ready):
                submit(shell, ve)
        elif state['phase'] == 'verify':
            assigned = ve.get_widget().get_widget_for_shellwidget(state['shell'])
            ns = ve.get_widget().current_widget()
            source = ns.editor.source_model.get_data() if ns else {}
            if ns and id(ns.editor.source_model) not in observed_models:
                model_id = id(ns.editor.source_model)
                observed_models[model_id] = 0

                def updated(model_id=model_id):
                    observed_models[model_id] += 1

                ns.editor.source_model.modelReset.connect(updated)
            model = ns.editor.model if ns else None
            if callable(model):
                model = model()
            rows = [model.index(row, 0).data() for row in range(model.rowCount())] if model else []
            alive = bool(shell and shell.kernel_client and shell.kernel_client.is_alive())
            snap = dict(ready=bool(shell and shell.spyder_kernel_ready), alive=alive,
                        same_console=(shell is state['shell'] and ns is assigned
                                      and ns is not None and ns.shellwidget is shell),
                        pane_visible=bool(ns and ns.isVisible()), source=source,
                        rows=rows, kernel=state['kernel'],
                        active_console=console.get_current_client().get_name() if shell else None,
                        connection_state=str(shell.kernel_handler.connection_state) if shell else None,
                        model_type=type(source).__name__,
                        model_resets=observed_models.get(id(ns.editor.source_model)) if ns else None,
                        view_configuration=dict(shell._kernel_configuration) if shell else None,
                        spyder=md.version('spyder'), gui_python=sys.executable)
            elapsed = now - state['sent']
            record('sample', stage=state['stage'], elapsed=elapsed, **snap)
            if shell:
                (out / (state['stage'] + '-console.txt')).write_text(redact(shell._control.toPlainText()))
            if (not state['requested'] and (out / (state['token'] + '.json')).exists()
                    and snap['ready'] and shell is state['shell']):
                state['requested'] = True
                token = state['token']

                def receive(value):
                    record('kernel_value', token=token, value=value)
                    if state.get('token') == token:
                        state['kernel'] = value

                shell.call_kernel(callback=receive).get_value('acceptance_state')
                shell.call_kernel(callback=lambda value: record(
                    'kernel_namespace_view', token=token, value=value)).get_namespace_view()
            verdict, reason = evaluate(snap, state['expected'], elapsed, 30)
            if verdict == 'FAIL':
                raise TimeoutError(reason)
            if verdict == 'PASS':
                if state['stage'] == 'restarted' and state['kernel']['pid'] == state['first_pid']:
                    raise AssertionError('restart reused the previous kernel PID')
                plots = w.get_plugin(Plugins.Plots).get_widget().current_widget()
                assert plots.thumbnails_sb._thumbnails, 'Plots pane has no figure'
                ns.grab().save(str(out / (state['stage'] + '-variables.png')))
                record('accepted', stage=state['stage'], kernel=state['kernel'], rows=rows)
                state['passed'].append(state['stage'])
                if state['stage'] == 'first':
                    state['first_pid'] = state['kernel']['pid']
                    state.update(stage='second', phase='startup', deadline=now + 60)
                    console.create_new_client(give_focus=True)
                elif state['stage'] == 'second':
                    state.update(stage='returned', phase='startup', deadline=now + 30)
                    cw = console.get_widget()
                    index = next(i for i, client in enumerate(cw.clients)
                                 if client.shellwidget is state['first'])
                    cw.tabwidget.setCurrentIndex(index)
                elif state['stage'] == 'returned':
                    state.update(stage='restarted', phase='restart', deadline=now + 60,
                                 old_handler=shell.kernel_handler)
                    console.get_widget().restart_kernel(ask_before_restart=False)
                else:
                    finish()
                    return
        if now >= state['deadline']:
            raise TimeoutError('phase deadline: ' + state['phase'])
    except Exception:
        finish(traceback.format_exc())


record('start', spyder=md.version('spyder'), gui_python=sys.executable,
       profile='isolated', preferences=console_preferences(CONF,sys.executable),
       interpreter=args.interpreter, reference_without_shapely=args.reference_without_shapely,
       negative_missing_variable=args.negative_missing_variable)
timer = QTimer()
timer.timeout.connect(tick)
timer.start(250)
options, remaining = get_options(['--new-instance'])
create_window(MainWindow, app, create_splash_screen(), options, remaining)
orphan_pids = [pid for pid,process in children.items() if process.poll() is None]
if orphan_pids:
    state['result'] = 'FAIL'
    record('kernel-processes-still-running', pids=orphan_pids)
(out / 'result.json').write_text(json.dumps(dict(result=state['result'],
    gui_started=state.get('gui_started',False), stages=state['passed'], closed=not orphan_pids), indent=2))
real_exit(0 if state['result'] == 'PASS' else 1)
