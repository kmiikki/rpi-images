# Raspberry Pi vs Ubuntu lab314

## Main Difference

Raspberry Pi and Ubuntu use the same Python version and nearly the same package selection, but the installation method differs.

| Item                | Raspberry Pi            | Ubuntu                   |
| ------------------- | ----------------------- | ------------------------ |
| Python environment  | `/opt/lab314`           | `micromamba env lab314`  |
| Package manager     | conda + pip             | micromamba               |
| Spyder location     | apt package outside env | tools env outside lab314 |
| Autoactivate lab314 | yes                     | no                       |
| Picamera2           | installed               | not installed            |
| OpenCV Qt font fix  | required                | usually not required     |

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

* researchers should immediately get the correct Python environment
* Raspberry Pi is usually a dedicated machine

Picamera2 and Raspberry Pi-specific packages are installed with apt:

```text
python3-picamera2
python3-libcamera
python3-rpi.gpio
```

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

* Ubuntu is often a general-purpose workstation
* automatic activation could interfere with other development work
* multiple environments are common

---

## Why Raspberry Pi Uses pip For OpenCV

On Raspberry Pi, the pip version of `opencv-python` worked better with Python 3.14 than the available distro packages.

However, this caused the Qt font problem described in:

```text
docs/opencv-qt-font-fix.md
```

Ubuntu may later move fully to micromamba packages if they become more reliable with Python 3.14.

---

## Long-Term Plan

The intention is:

* one base installation per Raspberry Pi OS release
* one common environment name: `lab314`
* same Python version on Raspberry Pi and Ubuntu
* same scientific package set where possible

Current target version:

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
