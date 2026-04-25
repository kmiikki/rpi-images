# Trixie Base (lab-install)

This profile provides a reproducible laboratory environment for Raspberry Pi OS (Debian Trixie).

---

## Purpose

Creates and manages a standard Python environment:

- Python 3.14
- `lab314` environment
- Spyder integration (external)
- consistent toolchain for research use

Key design goals:

- one shared environment for users
- stable and predictable behaviour
- minimal user configuration
- safe system-level tooling

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
├── enable_lab314_autoactivate_rpi.sh
├── verify_rpi_lab314.sh
├── setup_lab314_ubuntu.sh
├── verify_lab314_ubuntu.sh
├── run_rpi_home.sh
├── run_rpi_aalto.sh
├── run_ubuntu_lab314.sh
├── uninstall_lab314_env.sh
├── uninstall_conda_base.sh
├── uninstall_rpi_autoactivate.sh
├── run_uninstall_rpi_home.sh
├── run_uninstall_rpi_aalto.sh
└── run_uninstall_ubuntu_lab314.sh
````

### Additional components

```text
base/
├── bin/
│   └── rpi-share
├── config/
│   ├── rpi-share.aalto.json
│   └── rpi-share.home.json
├── docs/
│   ├── rpi-share.md
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

### Ubuntu

```bash
cd install
./run_ubuntu_lab314.sh
```

Ubuntu does not autoactivate `lab314`.

---

## PATH and Tools

The following directory is added to PATH:

```text
/opt/lab/bin
```

This is the standard location for user-facing tools.

---

## rpi-share (Network Access)

`rpi-share` provides safe access to network storage.

### Features

* session-based mounts
* supports:

  * sshfs (Aalto)
  * cifs (NAS)
  * browse (GUI)
* no stored passwords
* safe unmount behaviour

### Lifecycle

```text
start script → mount
exit script  → unmount
```

### Safe Unmount Policy

The tool intentionally avoids:

```text
umount -l
umount -f
```

Reason:

> Forced or lazy unmount may freeze the system when GUI applications (e.g. Nemo) use CIFS mounts.

Behaviour:

* normal unmount is attempted
* if busy → user closes applications
* retry loop continues until safe

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
```

---

## Sudo Policy

Passwordless sudo is enabled for the invoking user.

```text
/etc/sudoers.d/010_<user>-nopasswd
```

Verify:

```bash
sudo -n true
```

---

## Optional Wolfram Engine

Not installed by default.

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

## Test

```bash
python - <<'EOF'
import numpy, pandas, matplotlib, scipy, skimage, cv2
print("Environment OK")
EOF
```

Spyder interpreter:

```text
/opt/lab314/bin/python
```

---

## Design Principles

* no hidden automation
* no stored credentials
* user-controlled workflows
* stable over clever
