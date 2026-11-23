"""Unit tests for Spyder's application-scoped desktop environment."""

from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'install'))
import check_spyder_gui as gui
import spyder_runtime as runtime


class SpyderRuntimeTests(unittest.TestCase):
    def test_wayland_host_without_qt5_plugin_uses_xwayland(self):
        display={'WAYLAND_DISPLAY':'wayland-0','DISPLAY':':0'}
        self.assertEqual(runtime.select_platform(display,{'xcb'}),'xcb')
        self.assertEqual(runtime.select_platform(display,{'xcb','wayland'}),'wayland')
        with self.assertRaisesRegex(ValueError,'XWayland'):
            runtime.select_platform({'WAYLAND_DISPLAY':'wayland-0'}, {'xcb'})

    def test_x11_and_missing_display(self):
        self.assertEqual(runtime.select_platform({'DISPLAY':':19'},{'xcb','wayland'}),'xcb')
        with self.assertRaisesRegex(ValueError,'desktop display'):
            runtime.select_platform({}, {'xcb'})

    def test_settings_are_limited_to_spyder_and_preserve_display_credentials(self):
        source={key:'foreign' for key in ('LD_LIBRARY_PATH','LD_PRELOAD','QT_PLUGIN_PATH','QT_API',
                'QT_QPA_PLATFORM','QT_QPA_PLATFORM_PLUGIN_PATH','PYTHONPATH','QTWEBENGINEPROCESS_PATH',
                'QTWEBENGINE_DISABLE_SANDBOX','QTWEBENGINE_CHROMIUM_FLAGS')}
        source.update(PATH='/usr/bin',HOME='/home/researcher',XAUTHORITY='/home/researcher/.Xauthority',
                      DISPLAY=':1',ARROW_DEFAULT_MEMORY_POOL='jemalloc')
        with patch.object(runtime.platform,'machine',return_value='aarch64'),\
                patch.object(os,'sysconf',return_value=16384):
            result=runtime.isolated_environment(source,Path('/opt/lab314'))
        self.assertNotIn('LD_PRELOAD',result)
        self.assertEqual(result['PATH'],'/opt/lab314/bin:/usr/bin')
        self.assertEqual(result['ARROW_DEFAULT_MEMORY_POOL'],'system')
        self.assertEqual(result['XAUTHORITY'],source['XAUTHORITY'])
        self.assertEqual(source['QT_API'],'foreign')
        self.assertEqual(source['ARROW_DEFAULT_MEMORY_POOL'],'jemalloc')

    def test_fatal_webengine_output_cannot_qualify_and_is_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'probe.log'
            passed,status=gui.run_check([sys.executable,'-c',
                'import sys; print("FATAL:page_allocator_internals_posix.h(169) token=secret",file=sys.stderr)'],
                os.environ.copy(),log,5)
            self.assertFalse(passed)
            self.assertIn('status 0',status)
            self.assertNotIn('token=secret',log.read_text())
            self.assertIn('token=[redacted]',log.read_text())

    def test_console_uses_the_installed_miniforge_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            conda=Path(tmp)/'conda'
            conda.touch(mode=0o755)
            env=runtime.isolated_environment({'CONDA_EXE':'old','MAMBA_EXE':'old'},Path('/opt/lab314'),conda)
        self.assertEqual(env['CONDA_EXE'],str(conda))
        self.assertNotIn('MAMBA_EXE',env)

    def test_known_warning_is_visible_and_other_kernel_errors_reach_spyder(self):
        forwarded=[]
        def original(_client,message):
            forwarded.append(message)
            return False
        message='<jemalloc>: Unsupported system page size\n'
        with redirect_stderr(io.StringIO()) as stderr:
            trap=runtime.preserve_arrow_warning(original)
        with redirect_stderr(io.StringIO()) as reporter:
            self.assertTrue(trap(None,message))
            self.assertFalse(trap(None,message+'Traceback: import failed\n'))
        self.assertEqual(stderr.getvalue(),message)
        self.assertEqual(reporter.getvalue(),'')
        self.assertEqual(forwarded,[message+'Traceback: import failed\n'])

    def test_desktop_audit_distinguishes_user_override_and_installed_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            user,system=(root/'user',root/'system')
            for directory,command in ((user,'/other/spyder bearer-token'),(system,str(gui.LAUNCHER))):
                path=directory/'applications'/gui.DESKTOP_ID
                path.parent.mkdir(parents=True)
                path.write_text(f'[Desktop Entry]\nExec={command}\n')
            found=gui.desktop_candidates({'XDG_DATA_HOME':str(user),'XDG_DATA_DIRS':str(system)},root)
        self.assertEqual([(entry['user_entry'],entry['kind']) for entry in found],
                         [(True,'different launcher'),(False,'official launcher')])
        self.assertNotIn('bearer-token',str(found))

    def test_conda_desktop_id_resolves_to_hidden_compatibility_launcher_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            local=root/'local'
            system=root/'system'
            for directory in (local,system):
                (directory/'applications').mkdir(parents=True)
            alias=Path(gui.HERE).parent/'config/lab314/spyder-conda-compat.desktop'
            (local/'applications'/gui.CONDA_DESKTOP_ID).write_bytes(alias.read_bytes())
            (system/'applications'/gui.CONDA_DESKTOP_ID).write_text(
                '[Desktop Entry]\nExec=/opt/lab314/bin/spyder\n')
            entries=gui.desktop_candidates({'XDG_DATA_DIRS':f'{local}:{system}'},root)
            self.assertEqual([entry['kind'] for entry in entries],['official launcher','different launcher'])
            self.assertTrue(entries[0]['no_display'])
            self.assertFalse(entries[0]['hidden'])

    def test_environment_and_saved_interpreter_categories_exclude_raw_values(self):
        snapshot=runtime.environment_summary({'CONDA_EXE':'secret=original'}, {'CONDA_EXE':str('/opt/conda/bin/conda')})
        self.assertEqual(snapshot['CONDA_EXE'],'launcher-changed')
        self.assertNotIn('secret',str(snapshot))
        settings={('main_interpreter','custom'):True,('main_interpreter','custom_interpreter'):'/missing/python',
                  ('ipython_console','startup/run_lines'):'SECRET=123'}
        config=SimpleNamespace(get=lambda section, option, default=None:settings.get((section,option),default))
        facts=runtime.console_preferences(config,sys.executable)
        self.assertTrue(facts['custom_interpreter'])
        self.assertEqual(facts['saved_interpreter'],'missing or inaccessible')
        self.assertTrue(facts['startup_commands'])
        self.assertNotIn('SECRET',str(facts))

    def test_normal_snapshot_distinguishes_absent_plugin_from_unconnected_tab(self):
        plugins=SimpleNamespace(IPythonConsole='console',Projects='projects')
        missing=SimpleNamespace(get_plugin=lambda *args,**kwargs:None)
        self.assertFalse(runtime.console_snapshot(missing,plugins)['console_plugin'])
        client=SimpleNamespace(shellwidget=None,error_text='startup error')
        console=SimpleNamespace(get_current_client=lambda:client,get_widget=lambda:SimpleNamespace(clients=[client]))
        visible=SimpleNamespace(get_plugin=lambda name,**kwargs:console if name=='console' else None)
        snapshot=runtime.console_snapshot(visible,plugins)
        self.assertEqual(snapshot['tabs'],1)
        self.assertTrue(snapshot['startup_error'])
        self.assertFalse(snapshot['kernel_ready'])
