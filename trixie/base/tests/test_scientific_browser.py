"""Exercise the profile-independent Python hook and browser lifetime."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


BASE = Path(__file__).resolve().parents[1]
HOOK = BASE / 'config/lab314/rpi-scientific-browser.pth'
LAUNCHER = BASE / 'bin/rpi-scientific-browser'
URL = 'http://127.0.0.1:1234/figure'


class ScientificBrowserTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.work = Path(scratch.name)
        self.runtime = self.work / 'runtime'
        self.runtime.mkdir()
        self.report = self.work / 'report'
        fake = self.work / 'firefox'
        fake.write_text(f"""#!{sys.executable}
import os
from pathlib import Path
import signal
import sys

flag, option, profile, window, url = sys.argv[1:]
assert (flag, option, window) == ('--no-remote', '--profile', '--new-window')
profile = Path(profile)
assert profile.stat().st_mode & 0o777 == 0o700
assert profile.parent == Path(os.environ['XDG_RUNTIME_DIR'])
assert 'signon.rememberSignons", false' in (profile/'user.js').read_text()
Path(os.environ['REPORT']).write_text(url + '\\n' + str(profile))
if os.environ.get('WAIT'):
    signal.pause()
raise SystemExit(int(os.environ.get('STATUS', '0')))
""")
        fake.chmod(0o755)
        self.launcher = self.work / 'launcher'
        self.launcher.write_text(LAUNCHER.read_text().replace('/usr/bin/firefox', str(fake)))
        self.launcher.chmod(0o755)
        self.environment = os.environ.copy()
        self.environment.update(XDG_RUNTIME_DIR=str(self.runtime), REPORT=str(self.report))
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'BROWSER', 'PLOTLY_RENDERER'):
            self.environment.pop(key, None)

    def run_hook(self, code, **environment):
        directory = self.work / 'site'
        directory.mkdir(exist_ok=True)
        (directory / HOOK.name).write_text(
            HOOK.read_text().replace('/usr/local/bin/rpi-scientific-browser', str(self.launcher))
        )
        return subprocess.run(
            [sys.executable, '-IS', '-c', f'import site; site.addsitedir({str(directory)!r}); {code}'],
            env={**self.environment, **environment}, capture_output=True, text=True,
            check=True, timeout=10,
        ).stdout.strip()

    def wait_for_profile(self, url=URL):
        for _ in range(100):
            if self.report.exists():
                lines = self.report.read_text().splitlines()
                if len(lines) == 2:
                    self.assertEqual(lines[0], url)
                    return Path(lines[1])
            time.sleep(0.02)
        self.fail('The browser did not receive the test URL')

    def test_desktop_defaults_and_headless_and_explicit_overrides(self):
        show = 'import os; print(os.getenv("BROWSER"), os.getenv("PLOTLY_RENDERER"))'
        expected = f'{self.launcher} %s & browser'
        self.assertEqual(self.run_hook(show, DISPLAY=':0'), expected)
        self.assertEqual(self.run_hook(show, WAYLAND_DISPLAY='wayland-0'), expected)
        self.assertEqual(self.run_hook(show), 'None None')
        self.assertEqual(
            self.run_hook(show, DISPLAY=':0', BROWSER='custom', PLOTLY_RENDERER='svg'),
            'custom svg',
        )

    def test_webbrowser_uses_the_background_launcher(self):
        self.assertEqual(
            self.run_hook(
                'import webbrowser; assert isinstance(webbrowser.get(), webbrowser.BackgroundBrowser); '
                f'print(webbrowser.open({URL!r}))',
                WAYLAND_DISPLAY='wayland-0',
            ),
            'True',
        )
        self.assertFalse(self.wait_for_profile().exists())

    def test_cleanup_after_browser_failure(self):
        status = subprocess.run(
            [self.launcher, URL], env={**self.environment, 'STATUS': '3'}, timeout=10,
        ).returncode
        self.assertEqual(status, 3)
        self.assertFalse(self.wait_for_profile().exists())

    def test_cleanup_after_termination(self):
        with subprocess.Popen([self.launcher, URL], env={**self.environment, 'WAIT': '1'}) as browser:
            try:
                profile = self.wait_for_profile()
                self.assertTrue(profile.is_dir())
            finally:
                browser.terminate()
            self.assertEqual(browser.wait(timeout=10), 143)
        self.assertFalse(profile.exists())


if __name__ == '__main__':
    unittest.main()
