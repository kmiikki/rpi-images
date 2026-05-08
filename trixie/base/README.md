# Trixie Base (lab-install)

This profile provides a reproducible laboratory environment for Raspberry Pi OS
(Debian Trixie), with a standard analysis environment and optional Raspberry Pi
hardware support.

---

## Purpose

Creates and manages:

- `/opt/lab314`: clean Python 3.14 analysis environment
- optional `/opt/rpi`: Raspberry Pi hardware bridge environment
- `envrun`: launcher for running Python scripts in a selected environment
- Spyder integration with external Spyder and environment-specific kernels
- consistent system tooling for research, data transfer, logging, and analysis

Key design goals:

- one shared default analysis environment for users
- optional hardware-specific environment when needed
- stable and predictable behaviour
- minimal user configuration
- safe system-level tooling
- no hidden credentials or hidden automation

---

## Environment Model

### lab314

`/opt/lab314` is the default clean analysis environment.

Use it for:

- data analysis
- plotting
- image analysis that does not need Raspberry Pi OS hardware bindings
- `udplot`
- generic Python scripts
- serial/RS485 tools using `pyserial`

Interpreter:

```text
/opt/lab314/bin/python
```

Important:

```text
/opt/lab314 does not see APT-installed Raspberry Pi Python modules.
```

This is intentional. It keeps `lab314` isolated from system Python packages.

---

### rpi

`/opt/rpi` is an optional Raspberry Pi hardware bridge environment.

Use it for scripts that need Raspberry Pi OS APT Python modules, for example:

- Picamera2
- libcamera
- APT OpenCV (`python3-opencv`)
- GPIO
- I2C / `smbus2`
- `gpiod`
- other Raspberry Pi OS hardware bindings

Interpreter:

```text
/opt/rpi/bin/python
```

`/opt/rpi` uses the same Python minor version as `/usr/bin/python3` and sees:

```text
/usr/lib/python3/dist-packages
```

through a `.pth` file.

This allows `/opt/rpi` to use APT-installed Raspberry Pi Python modules while still
providing a conda-based scientific stack.

---

### envrun

`envrun` runs a Python script with a selected environment.

Preferred form:

```bash
envrun ENV SCRIPT [ARGS...]
```

Examples:

```bash
envrun lab314 udplot.py
envrun lab314 dps-profile-cycle.py -p /dev/ttyLOG -a 1,2,3,4
envrun rpi camera_test.py
envrun rpi gpio_test.py
```

Alternative form is also accepted:

```bash
envrun SCRIPT ENV [ARGS...]
```

Examples:

```bash
envrun udplot.py lab314
envrun camera_test.py rpi
```

Known environments:

```text
lab314 -> /opt/lab314/bin/python
rpi    -> /opt/rpi/bin/python
```

See:

```text
docs/envrun.md
docs/rpi-env.md
```

---

## Directory Structure

### Install scripts

```text
install/
├── packages/
│   ├── common-apt.txt
│   ├── rpi-apt.txt
│   └── ubuntu-apt.txt
├── pre_home.sh
├── pre_aalto.sh
├── install_rpi_base.sh
├── install_ubuntu_base.sh
├── install_conda_base.sh
├── create_lab314_env.sh
├── create_rpi_env.sh
├── enable_lab314_autoactivate_rpi.sh
├── install_envrun.sh
├── install_optional_wolfram.sh
├── setup_lab314_ubuntu.sh
├── verify_rpi_lab314.sh
├── verify_rpi_env.sh
├── verify_lab314_ubuntu.sh
├── run_rpi_home.sh
├── run_rpi_aalto.sh
├── run_ubuntu_lab314.sh
├── uninstall_lab314_env.sh
├── uninstall_rpi_env.sh
├── uninstall_conda_base.sh
├── uninstall_envrun.sh
├── uninstall_rpi_autoactivate.sh
├── uninstall_optional_wolfram.sh
├── run_uninstall_rpi_home.sh
├── run_uninstall_rpi_aalto.sh
└── run_uninstall_ubuntu_lab314.sh
```

### Additional components

```text
base/
├── bin/
│   ├── envrun
│   └── rpi-share
├── config/
│   ├── rpi-share.aalto.json
│   └── rpi-share.home.json
├── docs/
│   ├── envrun.md
│   ├── opencv-qt-font-fix.md
│   ├── rpi-env.md
│   ├── rpi-share.md
│   ├── rpi-share-advanced.md
│   ├── rpi-share-quick.md
│   ├── rpi-vs-ubuntu.md
│   ├── spyder-lab314.md
│   └── wolfram.md
└── install/
    ├── install_optional_wolfram.sh
    └── uninstall_optional_wolfram.sh
```

---

## Installation

### Raspberry Pi (home)

```bash
cd install
sudo ./run_rpi_home.sh
```

### Raspberry Pi (Aalto)

```bash
cd install
sudo ./run_rpi_aalto.sh
```

Use only one Raspberry Pi profile.

The Raspberry Pi install path sets up:

```text
APT base packages
/opt/conda
/opt/lab314
lab314 autoactivation
envrun
/opt/lab/bin PATH support
```

It does not automatically create `/opt/rpi`.

---

### Optional Raspberry Pi hardware environment

Create `/opt/rpi` only when Raspberry Pi hardware Python modules are needed:

```bash
cd install
./create_rpi_env.sh
./verify_rpi_env.sh
```

Use `/opt/rpi` for:

- Picamera2
- libcamera
- APT OpenCV
- GPIO
- I2C / `smbus2`
- `gpiod`

---

### Ubuntu

```bash
cd install
./run_ubuntu_lab314.sh
```

Ubuntu does not autoactivate `lab314`.

Ubuntu uses a separate micromamba-based `lab314` environment rather than the
Raspberry Pi `/opt/lab314` prefix model.

---

## PATH and Tools

The following directory is added to PATH:

```text
/opt/lab/bin
```

This is the standard location for user-facing lab tools.

`envrun` is installed to:

```text
/usr/local/bin/envrun
```

---

## rpi-share (Network Access)

`rpi-share` provides safe access to network storage.

### Features

- session-based mounts
- supports:
  - SSHFS (Aalto)
  - CIFS (NAS)
  - browse (GUI)
- no stored passwords
- safe unmount behaviour

### Lifecycle

```text
start script -> mount
exit script  -> unmount
```

### Safe Unmount Policy

The tool intentionally avoids:

```text
umount -l
umount -f
```

Reason:

> Forced or lazy unmount may freeze the system when GUI applications
> such as Nemo use CIFS mounts.

Behaviour:

- normal unmount is attempted
- if busy, the user closes applications
- retry loop continues until safe

### Configuration

```text
rpi-share.json
```

Resolution order:

1. working directory
2. `~/.config/rpi-share.json`
3. script directory

See:

```text
docs/rpi-share.md
docs/rpi-share-quick.md
docs/rpi-share-advanced.md
```

---

## Sudo Policy

Passwordless sudo is enabled for the invoking user on Raspberry Pi installs.

```text
/etc/sudoers.d/010_<user>-nopasswd
```

Verify:

```bash
sudo -n true
```

---

## Optional Wolfram Engine

Wolfram Engine is not installed by default.

Install:

```bash
cd install
sudo ./install_optional_wolfram.sh
```

Uninstall:

```bash
cd install
sudo ./uninstall_optional_wolfram.sh
```

See:

```text
docs/wolfram.md
```

---

## Logs

```text
/opt/lab/logs
```

---

## Verification

### Shell syntax

```bash
bash -n install/*.sh bin/envrun && echo "Shell syntax OK"
```

This checks Bash syntax only. It does not execute the install or uninstall
commands.

---

### lab314 on Raspberry Pi

```bash
./install/verify_rpi_lab314.sh
```

Manual quick test:

```bash
/opt/lab314/bin/python - <<'EOF'
import numpy, pandas, matplotlib, scipy, skimage, cv2, serial
print("lab314 OK")
EOF
```

Expected interpreter:

```text
/opt/lab314/bin/python
```

---

### rpi hardware environment

If `/opt/rpi` has been created:

```bash
./install/verify_rpi_env.sh
```

Expected signs of success:

```text
System dist-packages visible: True
cv2 file: /usr/lib/python3/dist-packages/...
picamera2 OK
envrun executable: /opt/rpi/bin/python
```

---

### envrun

```bash
envrun --help
```

Optional quick test:

```bash
cat >/tmp/envrun_test.py <<'EOF'
import sys
print(sys.executable)
print(sys.version.split()[0])
EOF

envrun lab314 /tmp/envrun_test.py
envrun rpi /tmp/envrun_test.py
```

---

## OpenCV Notes

`lab314` and `rpi` use OpenCV differently.

```text
/opt/lab314:
  pip opencv-python
  Python 3.14
  isolated from system Python
  needs the OpenCV Qt font fix

/opt/rpi:
  APT python3-opencv
  Python minor version matches /usr/bin/python3
  sees /usr/lib/python3/dist-packages
  intended for Picamera2/libcamera compatibility
```

See:

```text
docs/opencv-qt-font-fix.md
docs/rpi-env.md
```

---

## Uninstall

### Remove optional rpi environment only

```bash
cd install
./uninstall_rpi_env.sh
```

### Remove envrun only

```bash
cd install
./uninstall_envrun.sh
```

### Full Raspberry Pi uninstall

Home profile:

```bash
cd install
./run_uninstall_rpi_home.sh
```

Aalto profile:

```bash
cd install
./run_uninstall_rpi_aalto.sh
```

Optional flags:

```bash
--remove-apt
--purge
```

Use full uninstall with care. It removes `/opt/lab314`, `/opt/rpi`, and
`/opt/conda`.

---

## Design Principles

- no hidden automation
- no stored credentials
- user-controlled workflows
- stable over clever
- analysis and hardware environments are separated
- Raspberry Pi APT Python modules are used only through `/usr/bin/python3` or `/opt/rpi`
- `/opt/lab314` remains a clean analysis environment
