# Using Spyder with lab314

## Launch on Raspberry Pi OS Trixie

Open **Spyder (Scientific Python)** from the desktop menu or run:

```sh
rpi-lab314-spyder
```

New unified installations put Spyder and its compatible IPython kernel in the
same Conda environment as Scientific Python 3.14. For a clean Spyder profile
the default interpreter is `/opt/lab314/bin/python`. If saved preferences point
to an older interpreter, select the default interpreter under
**Tools → Preferences → Python interpreter** and restart the console.

The desktop menu and terminal command use the same launcher. It selects
the lab314 Qt platform plugin for the current display. The tested Conda
PyQt5 build supplies `xcb`; on the Trixie Wayland desktop this uses XWayland.
The launcher also selects `/opt/conda/bin/conda` for Spyder's kernel startup.
Qt and dynamic loader settings are scoped to this application. The launcher
keeps saved Spyder settings, interpreter preferences and projects.

## Formatted Help and camera work

On Raspberry Pi 5, the stock 4 KiB kernel addresses a page-size problem in
Spyder's formatted Help. On tr3, formatted Help displayed documentation and
executed JavaScript with 4 KiB pages. A standalone test of the Conda
QtWebEngine 5.15.15 renderer hit a separate sandbox error. The installed Spyder
starts its embedded viewer with an upstream sandbox override. Use an external
browser for untrusted web content. If the Help pane
is blank, choose Plain Text mode or open the documentation in an external
browser. The editor and scientific calculations can be used independently.
Other embedded web viewers need their own tests.
[Verify or restore the Pi 5 kernel selection](unified-setup.md#raspberry-pi-5-kernel-compatibility)

For projects that use Raspberry Pi OS Picamera2 and libcamera, select the
interpreter `/opt/rpi/bin/python` in **Tools → Preferences → Python interpreter**
and restart the IPython console. Switch back to `/opt/lab314/bin/python` for
the scientific package set, including lab314's OpenCV. The hybrid setup makes
the OS-provided Picamera2 and libcamera available through `/opt/rpi`.
Those imports are expected to fail in lab314. The hardware interpreter may
expose different library versions, including Raspberry Pi OS's OpenCV.
[Raspberry Pi hardware Python](rpi-env.md)

## Existing installations

Setup preserves valid existing lab314 and external Spyder prefixes. If the
scientific environment predates the integrated IDE, setup reports the deferred
migration. Install into a vacant prefix and test it before retiring the old
one. Existing external IDE maintenance remains available separately.
[Lab314 package ownership and maintenance](lab314-maintenance.md)

Run `sudo bash setup-rpi.sh` from the new ZIP's `trixie/base/install`
directory to reconcile the installed launcher. To diagnose a startup failure
or explicitly repair the existing launcher, use the management interface:

```sh
sudo bash setup-rpi.sh --manage --action repair --component spyder --plan
sudo bash setup-rpi.sh --manage --action repair --component spyder
```

The repair checks the kernel and installs the approved launcher files under
`/usr/local`. The Conda packages and the working `/opt/rpi` environment stay intact.

## Legacy Ubuntu layout

On Ubuntu:

* Spyder is kept in a separate `tools` environment
* the current Scientific Python installation uses `science` for scientific packages and its kernel; older Ubuntu lab314 examples below describe the legacy installer

Typical setup:

```text
tools environment:
    spyder
    jupyter
    notebooks
    developer tools

lab314 environment:
    Python 3.14
    scientific packages
    opencv
    spyder-kernels
```

Example:

```bash
micromamba activate tools
spyder
```

Then configure Spyder to use:

```text
lab314 interpreter
```

for example:

```text
~/micromamba/envs/lab314/bin/python
```

or whichever path micromamba uses.

---

## Verification

Run in Spyder console:

```python
import sys
import numpy, scipy, cv2, spyder_kernels

print(sys.executable)
print(spyder_kernels.__version__)
```

Expected on Raspberry Pi:

```text
/opt/lab314/bin/python
<kernel version compatible with the selected IDE>
```

If another interpreter appears, Spyder is not using `lab314`.

Use **Spyder (Scientific Python)** in the desktop menu or activate
`/opt/lab314` with Conda or Micromamba and run `spyder` as the desktop user.
The activation hook and menu entry use the same Raspberry Pi launcher.
Open a new terminal or reactivate `lab314` after installing the hook.
The explicit `rpi-lab314-spyder` command is also available. Installer-managed
desktop integration redirects the old Conda menu ID to this launcher.

If Spyder shows **No connected console**, try **Consoles → New console** once.
Check the default interpreter in Preferences if the new console also fails.
Run the desktop diagnostic from the ZIP's `trixie/base` directory in the same
graphical session as the normal user:

```sh
/opt/lab314/bin/python -IB install/check_spyder_gui.py
```

The diagnostic labels its result **Isolated** and leaves normal desktop
acceptance pending. It uses a temporary Spyder profile. It tests actual Qt platform
initialization and local HTML rendering in separate processes, then drives
Spyder's own IPython Console, Variable Explorer and Plots panes. The private
diagnostic directory contains process status, stderr, and console state changes.

If the desktop console stays disconnected, close all Spyder windows and run
this command from the extracted ZIP's `trixie/base` directory. Use the
affected user's graphical session and run without sudo.

```sh
/opt/lab314/bin/python -IB install/check_spyder_gui.py --normal
```

The diagnostic checks the installed launcher, helper and desktop entry against
the archive. It invokes the installed helper with the verified launcher's
environment setup. In Spyder, wait for the initial console to connect or fail.
If it remains blank, wait 45 seconds, use **Consoles → New console** once, then
close Spyder. The command prints the path of the private
`/tmp/rpi-spyder-desktop-<uid>-*.jsonl` report.

The report distinguishes the current profile, console request, Jupyter runtime
and connection-file checks, actual kernel process, Jupyter reply, Spyder comms,
widget connection and prompt. It records process exit status or signal when
observed and whether the jemalloc correction accepted the warning during
startup. Error categories and matching source frames can be shared. The log
excludes raw stderr, connection information, environment values, project
filenames and startup code. The original stderr remains in the terminal.

**Trace current desktop profile** on the menu entry, where supported, still
captures the desktop's own environment and console summary. To compare with
the plain `lab314` terminal entry point, repeat the command with `--direct`.
Both detailed traces use the existing profile. The isolated diagnostic
without either option uses temporary settings. If an existing Spyder instance
receives the launch, close it and repeat the trace.

### Raspberry Pi 5 with 16 KiB pages

The Conda `qt-webengine` build `5.15.15-h6406779_4` reproduced the Chromium
allocator fault in an ARM64 guest at the same page size. Its WebEngine child
called `mprotect` with an address that was unaligned for 16 KiB pages. The
fault also occurred with the `xcb` plugin and a working X11 display. PyArrow's
jemalloc diagnostic is separate. The launcher selects the system memory pool
if the parent explicitly selects jemalloc on large-page ARM64. Spyder 6.1.8
interprets that exact warning during graphical console startup as fatal and
shuts down the kernel. The launcher preserves the warning on stderr and
classifies it as nonfatal for that version on large-page ARM64. The warning
goes to the launcher’s original stderr stream, since Spyder routes its own
stderr to the internal error dialog after startup. Other kernel errors follow
Spyder's existing error handling.

The graphical console, additional console, Variable Explorer, plot and kernel
restart passed in ARM64 QEMU using the scoped correction. The QtWebEngine
subprocess fault remained in the Conda build, so Help and any other HTML views
still require their own acceptance. Debian's Trixie QtWebEngine 5.15.18 build
rendered the local test page and returned a JavaScript result on 16 KiB.
The installer keeps the Conda Qt runtime and does not mix distribution libraries
into it automatically.
The two WebEngine builds share a SONAME and consume private Qt ABI symbols.
The Debian build also expects dependencies such as `libicuuc.so.76`,
`libjpeg.so.62` and `libxml2.so.2` that differ from the Conda dependency tree.
The Conda build's Qt libraries, plugins, Chromium helper and assets must be kept
coherent. A replacement needs a compatible build in the same Conda stack, or
an independently validated Qt stack and process boundary. The Debian rendering
probe establishes that its build works on 16 KiB pages. It does not validate a
drop-in replacement in the integrated Spyder environment.

### Hardware acceptance

Open Spyder from the desktop menu. From the initial `In [1]:` prompt run:

```python
import sys, numpy as np, scipy, cv2
import matplotlib.pyplot as plt
print(sys.executable, np.__version__, scipy.__version__, cv2.__version__)
x = np.linspace(0, 2*np.pi, 1000)
y = np.sin(x)
print(np.max(y))
plt.plot(x, y); plt.grid(True); plt.show()
```

Check that `x` and `y` are inspectable in Variable Explorer and the plot is
visible. Open a second console and confirm its namespace is independent.
Restart the first kernel and run a command again, then exit Spyder normally.
Record any WebEngine failures separately, including whether Help renders.

---

## Using Spyder with `/opt/rpi`

For normal analysis work, keep using:

```text
/opt/lab314/bin/python
```

Use `/opt/rpi/bin/python` for scripts that import Raspberry Pi OS APT Python
modules such as:

```text
picamera2
libcamera
cv2 from APT python3-opencv
smbus2
RPi.GPIO
gpiod
```

The installer selects the separate hardware environment by default. Use
it for hardware-facing code and keep the default Spyder console in lab314.
