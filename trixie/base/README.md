# Trixie Base (lab-install)

This profile provides the common laboratory environment for **Raspberry Pi OS
Trixie Full, 64-bit**: cameras, data loggers and other research instruments.


---

## Unified initial installation

Use `setup-rpi.sh` for all new Raspberry Pi OS Trixie installations with GENERAL,
HOME or AALTO after Raspberry Pi Imager and first boot. See [Installation profiles](#installation-profiles)
for the command and the [unified setup guide](docs/unified-setup.md) for preboot,
previews and options.
On Raspberry Pi 5, setup offers the stock 4 KiB kernel for Spyder's formatted
Help. Boot changes need approval and a reboot. The same install command resumes
setup after reboot and reconciles managed settings on future runs.
On the tr3 test system, Spyder formatted Help worked with 4 KiB pages while a
standalone WebEngine diagnostic failed. Use Plain Text Help or an external
browser if an embedded view is blank.
[Kernel compatibility and rollback](docs/unified-setup.md#raspberry-pi-5-kernel-compatibility)
For a prepared card moving between Pi 4 and Pi 5 Model B, use
[`adapt-rpi-model.sh`](docs/unified-setup.md#moving-an-installation-card-between-raspberry-pi-4-and-5).
From `trixie/base`, preview with `bash install/setup-rpi.sh --profile GENERAL --primary-user YOUR_USER --plan`.
Existing component installers remain independently usable. See the
[architecture](docs/unified-architecture.md) and
[offline, reversible rpi-share JSON/CSV catalogs](docs/rpi-share-catalog.md).

## Purpose

Creates and manages:

- `/opt/conda`: existing Miniforge/Conda bootstrap
- `/opt/lab314`: rolling Python 3.14 scientific environment with Spyder and GUI OpenCV
- `/opt/rpi`: separately configurable Raspberry Pi hardware bridge, selected by default
- `envrun`: launcher for running Python scripts in a selected environment
- Spyder IDE and its matching kernel in the scientific environment
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

`/opt/lab314` is the default clean analysis environment. Normal installation
resolves current compatible direct requirements, keeps Python within 3.14,
and installs GUI OpenCV with a Qt6 build from Conda-forge. Compatible maintenance
updates are accepted by normal verification. The integrated Spyder installation
and compatible kernel use package metadata from the same environment.

The historical November 2026 snapshot (Python 3.14.10, OpenCV 5.0.0,
Shapely 2.2.0 / GEOS 3.14.1, 145 distributions) remains available explicitly
with `--snapshot`. Its prior 103 PASS acceptance is historical evidence, not
an instruction to reject valid updates. See [maintenance and recovery](docs/lab314-maintenance.md).

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
- SPI / `spidev` (APT module; present in the current test system)
- serial / `pyserial`
- I2C / `smbus2`
- `gpiod`
- other Raspberry Pi OS hardware bindings

Interpreter:

```text
/opt/rpi/bin/python
```

`/opt/rpi` uses the same Python minor version as `/usr/bin/python3`
(current Trixie: **Python 3.13**) and sees:

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
├── setup-rpi.sh
├── legacy/
│   ├── run_rpi_home.sh
│   └── run_rpi_aalto.sh
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
│   ├── rpi-share.example.csv
│   ├── rpi-share.example.json
│   └── rpi-share.schema.json
├── docs/
│   ├── envrun.md
│   ├── opencv-qt-font-fix.md
│   ├── rpi-env.md
│   ├── rpi-share.md
│   ├── rpi-share-advanced.md
│   ├── rpi-share-catalog.md
│   ├── rpi-vs-ubuntu.md
│   ├── spyder-lab314.md
│   └── wolfram.md
└── install/
    ├── install_optional_wolfram.sh
    └── uninstall_optional_wolfram.sh
```

---

New users: follow the [hands-on installation guide](../../QUICKSTART.md).

## Installation profiles

Use `setup-rpi.sh` for a new Raspberry Pi OS Trixie installation and choose a
profile at the prompt. On Raspberry Pi 5 Model B, preboot configures the keyboard
and interfaces first. If it pauses for a reboot, repeat the same command to
resume the profile already selected.
[Preboot and hardware verification](docs/unified-setup.md#first-boot-preparation-on-raspberry-pi-5)

```bash
cd rpi-images/trixie/base/install
sudo bash setup-rpi.sh
```

The unified installer supports three profiles.

| Profile | Purpose |
|---|---|
| GENERAL | Generic Raspberry Pi installation without HOME- or AALTO-specific configuration |
| HOME | Home environment with its predefined settings |
| AALTO | Aalto University CHEM environment with its predefined settings |

These commands work from a cloned repository or an extracted ZIP package.
Run them from the parent of the repository directory; if the extracted folder
has a different name, substitute that name in the `cd` command. Keep the full
directory tree together; Git metadata is not required.

Review the account and component plan before confirming. Rerun the command
from a newer ZIP to reconcile configuration. Open `--manage` and choose
**Update All** for reviewed software updates.
[Reruns and maintenance](docs/unified-setup.md#reruns-and-maintenance)

The Raspberry Pi install path sets up:

```text
APT base packages
/opt/conda
/opt/lab314
lab314 autoactivation
envrun
/opt/sci/bin and /opt/sci/bin-rpi PATH support
```

### Legacy / profile-specific installation scripts

The historical [HOME](install/legacy/run_rpi_home.sh) and
[AALTO](install/legacy/run_rpi_aalto.sh) scripts are archived under
`install/legacy/` for existing installations. They retain their profile defaults
and options, including `PRIMARY_USER`, `DO_APT_UPGRADE=1` and
`--with-cam-imgcheck PATH`.

---

### Camera-system hardware environment

`/opt/rpi` is optional for GENERAL, HOME and AALTO. Select hardware support in
the unified installer (or use `--hardware`). For a **new camera machine** where
it was not selected, create it after base provisioning and before Scientific
Imaging camera apps:

```bash
# From trixie/base/install; only when /opt/rpi does not exist:
sudo bash create_rpi_env.sh
bash verify_rpi_env.sh
```

An existing `/opt/rpi` is verified, not recreated. The script currently refuses
an existing prefix. Do not remove a working environment to rerun it.
`/opt/rpi` is not autoactivated by default. Use direct `/opt/rpi/bin/python3`
shebangs for installed camera applications. Preserve `envrun` for its existing
workflows; no new application wrappers are created.

The existing `--with-cam-imgcheck SCIENTIFIC_IMAGING` choice creates a missing
`/opt/rpi` at its current point in the legacy HOME/AALTO sequence and runs the pilot
installer. If using that choice, do not separately recreate `/opt/rpi`.
See [hardware environment details](docs/rpi-env.md).

Use `/opt/rpi` for:

- Picamera2
- libcamera
- APT OpenCV
- GPIO
- I2C / `smbus2`
- `gpiod`

---

### Ubuntu

The old `run_ubuntu_lab314.sh` and related scripts remain in this repository
unchanged as the earlier Ubuntu implementation. They are not the installation
route for the current Scientific Imaging stack: Ubuntu applications use the
separate Scientific Python V4-r5.2 **science** environment and its existing
Micromamba root. This Trixie task does not update or merge those installers.

---

## Scientific Imaging applications and build dependencies

The model installation owns OS/APT and Python environment provisioning.
The current Scientific Imaging repository owns application installation,
diagnostics, update and removal under `/opt/sci/{bin,bin-rpi,lib}`.
After provisioning `/opt/rpi` on a camera machine, use that repository's
`scripts/install/01-install.sh`, for example `--app vrecorder-full-rpi.py
--app cam-preview`, then its `02-diagnose.sh`. Read its
application guide `docs/installation/SCIENTIFIC_IMAGING_APPS.md`
from the matching Scientific Imaging source release. That separate local
repository has not been assigned a public remote here; no publication URL
is invented by this model installer.

This repository's `install_sci_apps.sh`, `verify_sci_apps.sh`, `sci_payload.py`
and shebang tool are the existing **cam-imgcheck 0.1.2 pilot**. Scientific
Imaging reused that payload engine and added its catalogue, lifecycle and
native packaging. Both copies remain: neither was replaced, removed or merged.
Avoid managing the same app with both installers. The newer installer can
verify an external pilot but does not silently adopt its ownership.
See [pilot details and division of responsibility](docs/sci-apps.md).

`common-apt.txt` already provides `build-essential` and `pkg-config`.
`rpi-apt.txt` now explicitly includes the 11 proven Meson/Ninja, libcamera,
Boost, image-format and DRM/EGL development packages for cam-preview.
The application installer checks them and never installs OS packages.
Qt/TFLite/Hailo/OpenCV-C++ or experimental-storage development libraries are
not added without a requirement from the selected preview build.
Keep the official Raspberry Pi APT source: its tested libcamera candidate is
0.8.0; do not force Debian's older 0.4.0 or pin APT versions here.

VRecorder Full RPi requires **ext4 for persistent video recording**. Its final
metadata publication uses a hard link, which exFAT lacks; temporary/candidate
and published files must stay on the same filesystem. This is not a blanket
filesystem rule for data loggers. See its
technical filesystem document in the Scientific Imaging repository:
`docs/architecture/VRECORDER_STORAGE_FILESYSTEM_RPI_LINUX.md`.
No formatting or exFAT adapter is performed by the model installer.

## PATH and Tools

The Pi base profile adds `/opt/sci/bin` and `/opt/sci/bin-rpi`. Ubuntu retains its existing `/opt/lab/bin` convention. Existing Pi installations can keep their legacy commands. Application-private modules live below `/opt/sci/lib`.

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

The installer discovers private JSON catalogs by profile. See
[Share configuration and ownership](docs/unified-setup.md#share-configuration-and-ownership).

When running the client, the configuration is named:

```text
rpi-share.json
```

Resolution order:

1. Explicit `--config FILE`
2. Working directory
3. `~/.config/rpi-share.json`
4. `/etc/rpi-share/rpi-share.json`
5. Script directory

See:

```text
docs/rpi-share.md
docs/rpi-share-catalog.md
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

Wolfram Engine is selected by default in AALTO and optional in GENERAL and HOME.
The installer reports its disk use and license terms before approval. On the
desktop, choose **Wolfram Mathematica (GUI)** or **Wolfram Language (CLI)**.

Install:

```bash
cd install
sudo bash install_optional_wolfram.sh
```

Uninstall:

```bash
cd install
sudo bash uninstall_optional_wolfram.sh
```

See:

```text
docs/wolfram.md
```

---

## Requirements, optional snapshots, caches and logs

Normal installation uses `config/lab314/requirements.json`, the maintained
direct dependency specification. Conda provides Python 3.14, pip and packaging;
pip resolves scientific binary wheels from the existing PyPI/piwheels sources.
No transitive versions are permanently frozen. The kernel compatibility range
is read from the selected external IDE metadata. Rerunning the normal installer updates an existing prefix to the latest
compatible packages. A current environment completes without package changes;
it is never recreated. Targeted updates are explicit optional selections.

```sh
# From trixie/base/install: normal installation and verification
sudo bash create_lab314_env.sh
bash verify_rpi_lab314.sh
# Historical snapshot: only in a new vacant prefix
sudo bash create_lab314_env.sh --snapshot --prefix /absolute/new/lab314-snapshot
bash verify_rpi_lab314.sh --snapshot --prefix /absolute/new/lab314-snapshot
```

The original `conda-linux-aarch64.txt`, `wheels.txt`, `packages.json` and
`SHA256SUMS` are retained unchanged for snapshot mode. Snapshot installation
checks their hashes and exact versions. Normal installation does not use their
version selection. The Miniforge bootstrap and hardware environment are unchanged.

Conda build caches remain next to the new prefix, removed by the EXIT trap;
pip's persistent cache is disabled. A failed prefix is retained for diagnosis.
Updates use temporary plans and explicit apply records. They are not transactional;
take a full external backup before applying them. Use capacity-checked `/dev/shm`
for small Pi tests, without assuming `/tmp` is RAM. No general installer log
directory is created at `/opt/lab/logs`.

See [targeted pip/Conda updates, security fixes, independent Spyder IDE maintenance and recovery](docs/lab314-maintenance.md).

---

## Verification

### Shell syntax

```bash
for script in install/*.sh bin/envrun bin/rpi-share; do
    bash -n "$script" || exit
done
echo "Shell syntax OK"
```

This checks Bash syntax only. It does not execute the install or uninstall
commands.

---

### lab314 on Raspberry Pi

```bash
bash install/verify_rpi_lab314.sh
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
bash install/verify_rpi_env.sh
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
  Conda-forge OpenCV with Qt6 HighGUI in new environments
  Python 3.14 maintenance series, isolated from system Python

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

## Maintenance and uninstall

Open the installer’s maintenance menu to inspect, verify, update, repair or remove
selected components, or preview a full scientific environment reset.

```bash
cd install
sudo bash setup-rpi.sh --manage
```

Reset keeps the keyboard layout, accounts and user data. The
[lifecycle guide](docs/unified-setup.md#installation-lifecycle) explains how the
installer checks ownership and shows any changes it cannot safely reverse.

---

## Design Principles

- no hidden automation
- no stored credentials
- user-controlled workflows
- stable over clever
- analysis and hardware environments are separated
- Raspberry Pi APT Python modules are used only through `/usr/bin/python3` or `/opt/rpi`
- `/opt/lab314` remains a clean analysis environment

