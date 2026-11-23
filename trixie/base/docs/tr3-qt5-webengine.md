# Standalone Qt5 WebEngine and Spyder Help on tr3

**Standalone renderer under default security: FAIL. Spyder formatted Help:
PASS for functionality.** On the clean Raspberry Pi OS Trixie ARM64 install,
both used `/opt/lab314/bin/python` (Python 3.14.10), PyQt5 5.15.11 and the
Conda QtWebEngine 5.15.15 build `h6406779_4`. The runtime user agent reported
Chromium 87.0.4280.144. The kernel was `6.18.60+rpt-rpi-v8` with 4096-byte
pages and Trixie's glibc was 2.41.

## What differs between the runs

| Path | Result | Evidence |
|---|---|---|
| Earlier standalone test on tr2 | PASS, reported by the operator | The operator reported a working standalone test after selecting the 4 KiB v8 kernel. The successful run's command, environment, exact loaded package files and renderer arguments were not available for comparison. The archived probe source alone cannot establish the old run's security settings. |
| Spyder Help on tr3 | PASS | Ctrl+I displayed formatted Help for the operator. A separate test verified the actual rendered docstring DOM and JavaScript result of 42. In the installed Spyder 6.1.8 sources, `spyder/utils/qthelpers.py` constructs its application with `--no-sandbox`. The configuration manager also uses that argument when it constructs a Qt application. |
| Standalone `QWebEngineView` on tr3 | FAIL | With `QApplication` started without a sandbox override, Qt opened the XWayland window but its renderer exited with status 2, code 31. Neither the DOM nor JavaScript checks passed. |
| Same standalone code, one temporary diagnostic argument | PASS for diagnosis | With the same presentation, Python and libraries, the temporary test application passed `--no-sandbox`. It verified the expected HTML DOM, JavaScript result 42 and exited 0. The setting applied only to this local test. |

The compared tr3 applications used the same logged-in Wayland session with
Qt's Conda `xcb` plugin over XWayland. The tests shared the X11 display, Wayland
socket and runtime directory. No explicit XAUTHORITY override was needed.
The standalone runs had no custom Qt plugin, resources, helper or Chromium
environment overrides. Qt5 mapped its own libraries from `/opt/lab314/lib`.
The standard launcher chooses `xcb` for this build and clears inherited
WebEngine sandbox and Chromium flags. Spyder itself supplies its Qt application
argument after that cleanup.
[Qt WebEngine sandbox documentation](https://doc.qt.io/qt-6/qtwebengine-platform-notes.html#sandboxing-support)

The tr3 Qt application argument lists were recorded for both standalone
runs. The installed Spyder application constructor was inspected locally.
The extra trace intended to capture all of Spyder's final helper command lines
could not be retrieved after SSH became unreachable. The working Spyder
behavior, installed argument and controlled standalone result are separately
recorded. The report does not classify an unobserved worker status as a
verified `/proc` result.

## Process-level cause

`strace` captured a renderer installing a seccomp BPF filter and then receiving
`SIGSYS` (`SYS_SECCOMP`) on AArch64 `clone3` while starting threads. The parent
application started without an inherited seccomp filter. The trace and the
one-variable test identify Chromium's renderer sandbox as the immediate
cause. A missing Wayland plugin is a separate startup issue; selecting the
installed XWayland-compatible plugin removed that variable and the crash
persisted. Neither the 16 KiB page allocator error nor mixed Qt libraries
explains this run.

The earlier Qt6 investigation found the same syscall and signal in its own
binary. This Qt5 trace establishes the blocked syscall, and it does not
establish that the Qt5 package was built with the same headers or uses that
same source-level filter branch. The scoped glibc rseq diagnostic and an extra
deny-only syscall policy both left the standalone renderer failure in place.

## Release interpretation

Keep the stock 4 KiB kernel selection and existing installed packages. Treat
Spyder's Help acceptance as application functionality. Its upstream
`--no-sandbox` behavior provides no evidence that the shared standalone
renderer passes with default Chromium isolation. For untrusted web content,
use a maintained external browser with its normal security settings.
The installer must keep its current launcher environment and must not add a
sandbox override.

The minimal test genuinely detects a failed renderer. A more explicit harness
was used to check the rendered DOM, JavaScript and bounded exit status on the
same active display. The smallest maintainable secure fix would be a compatible
prebuilt QtWebEngine update from the package maintainers that passes the same
test with default sandboxing. The Debian Qt5 runtime tested previously has a
different package and ABI context. Mixing its libraries into lab314 is not a
validated installation option. No replacement package or source build was
installed during this investigation.
