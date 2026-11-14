# Using Spyder with lab314

## Goal

Use Spyder installed outside the environment, while the Python interpreter and packages come from `lab314`.

This avoids maintaining a separate full Spyder installation inside every environment.

---

## Raspberry Pi

On Raspberry Pi OS Trixie:

* Spyder is installed with apt
* `spyder-kernels` is installed inside `/opt/lab314`

Installed packages:

```text
apt install spyder python3-spyder-kernels
```

Environment package:

```text
spyder-kernels (range declared by the selected external Spyder IDE)
```

The matching interpreter is:

```text
/opt/lab314/bin/python
```

In Spyder:

1. Open Preferences
2. Python Interpreter
3. Select:

```text
Use the following Python interpreter
```

4. Set:

```text
/opt/lab314/bin/python
```

5. Restart Spyder

---

## Ubuntu

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

## Why This Structure Is Used

Advantages:

* only one Spyder installation
* faster updates
* smaller scientific environments
* easier to rebuild `lab314`
* fewer Qt conflicts

This is especially useful because Raspberry Pi and Ubuntu may use different Spyder versions.

The historical Pi acceptance used Spyder 6.0.5 with kernel 3.0.5.
This is not a permanent constraint or a claim that 6.0.5 is the latest IDE.
The targeted update scenario moves from IDE 6.0.5 to 6.1.8 and from kernel
range `>=3.0.3,<3.1.0` to `>=3.1.0,<3.2.0`, allowing kernel 3.1.7.
Actual requirements come from the selected installed IDE's metadata.

The IDE can now be installed/updated independently in an administrator-selected
external Conda prefix using `update_lab314.py --ide-prefix`. APT Spyder remains
a fallback. Launch the IDE's existing `bin/spyder` directly and select its
`bin/python` with `LAB314_SPYDER_PYTHON` for kernel maintenance. No application
wrapper or new fixed installation path is introduced.

Then target only `spyder-kernels` and required dependencies in lab314. Scientific
libraries remain independently updatable; their current versions are not frozen.
See [the implemented workflows](lab314-maintenance.md#spyder-ide-and-kernel-maintenance).

---

## Verification

Run in Spyder console:

```python
import sys
import spyder_kernels

print(sys.executable)
print(spyder_kernels.__version__)
```

Expected on Raspberry Pi:

```text
/opt/lab314/bin/python
<kernel version compatible with the selected IDE>
```

If another interpreter appears, Spyder is not using `lab314`.

---

## Using Spyder with `/opt/rpi`

For normal analysis work, keep using:

```text
/opt/lab314/bin/python
```

If you need to run or debug Raspberry Pi hardware scripts in Spyder, set the
interpreter to:

```text
/opt/rpi/bin/python
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

The `/opt/rpi` environment is optional and is intended for Raspberry Pi
hardware-facing code. It is not the default analysis environment.
