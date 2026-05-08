# Raspberry Pi vs Ubuntu lab314

## Main Difference

Raspberry Pi and Ubuntu use related scientific Python environments, but their
installation models differ.

| Item                | Raspberry Pi                      | Ubuntu                   |
| ------------------- | --------------------------------- | ------------------------ |
| Analysis environment| `/opt/lab314`                     | `micromamba env lab314`  |
| Hardware environment| optional `/opt/rpi`               | not used by default      |
| Package manager     | conda + pip                       | micromamba               |
| Spyder location     | apt package outside env           | tools env outside lab314 |
| Autoactivate lab314 | yes                               | no                       |
| Picamera2           | APT/system Python                 | not installed            |
| OpenCV in lab314    | pip `opencv-python`               | micromamba/conda package |
| OpenCV in rpi       | APT `python3-opencv`              | not applicable           |

---

## Raspberry Pi Structure

Raspberry Pi uses:

```text
/opt/conda
/opt/lab314
```

`lab314` is created with:

```bash
install_conda_base.sh
create_lab314_env.sh
```

The environment is automatically activated for new terminals:

```text
(lab314)
```

Reason:

- researchers should immediately get the correct analysis environment
- Raspberry Pi is usually a dedicated machine

---

## Optional Raspberry Pi Hardware Environment

Some Raspberry Pi OS Python modules are installed with APT and are tied to the
system Python ABI. Examples:

```text
picamera2
libcamera
cv2 from python3-opencv
smbus2
RPi.GPIO
gpiod
```

These modules are not visible from `/opt/lab314`.

For hardware-facing scripts, create the optional environment:

```text
/opt/rpi
```

It uses the same Python minor version as:

```text
/usr/bin/python3
```

and sees:

```text
/usr/lib/python3/dist-packages
```

Use it with:

```bash
envrun rpi script.py
```

---

## Python Environment Selection

Use:

```bash
envrun lab314 script.py
```

for analysis, plotting, `udplot`, and generic Python scripts.

Use:

```bash
envrun rpi script.py
```

for Raspberry Pi hardware scripts that need Picamera2, libcamera, APT OpenCV,
GPIO, I2C/smbus2, or gpiod.

---

## Why Raspberry Pi `lab314` Uses pip OpenCV

On Raspberry Pi, the pip version of `opencv-python` worked better with Python
3.14 than the available distro packages for the clean analysis environment.

However, this caused the Qt font problem described in:

```text
docs/opencv-qt-font-fix.md
```

This statement applies to `/opt/lab314`.

The optional `/opt/rpi` environment uses APT `python3-opencv` instead, because
that is the preferred model for Picamera2/libcamera compatibility.

---

## Ubuntu Structure

Ubuntu uses micromamba and keeps environments separate:

```text
tools
lab314
```

Typical use:

```bash
micromamba activate tools
spyder
```

and Spyder uses the interpreter from `lab314`.

Reason:

- Ubuntu is often a general-purpose workstation
- automatic activation could interfere with other development work
- multiple environments are common

---

## Long-Term Plan

The intention is:

- one base installation per Raspberry Pi OS release
- one common analysis environment name: `lab314`
- optional hardware bridge environment on Raspberry Pi: `rpi`
- same scientific package set where practical

Current target for `lab314`:

```text
Python 3.14
```

Future directory structure may become:

```text
rpi-images/
├── trixie/
│   ├── base/
│   ├── logger/
│   └── spectrometer/
└── next-release/
```
