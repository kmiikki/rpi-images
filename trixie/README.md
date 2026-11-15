# Raspberry Pi OS Trixie — laboratory reference installation

`base/` is a general-purpose laboratory installation based on Raspberry Pi OS
**Trixie Full, 64-bit**, for camera systems, data loggers and other research
instruments.

The environment layout is:

| Path | Purpose |
|---|---|
| `/opt/conda` | Conda/Miniforge foundation |
| `/opt/lab314` | rolling Scientific Python on Python 3.14; GUI opencv-python |
| `/opt/rpi` | optional hardware environment using Trixie's Python 3.13 APT camera libraries and device interfaces |
| `/opt/sci/bin` | general Scientific Imaging commands |
| `/opt/sci/bin-rpi` | Pi-specific Scientific Imaging commands |
| `/opt/sci/lib` | application support files |

New users: follow the [hands-on installation guide](../QUICKSTART.md).

## Installation profiles

Use the unified installer as the recommended initial installation method:

```bash
cd rpi-images/trixie/base/install
sudo bash setup-rpi.sh
```

The installer interactively offers three independent, fully supported profiles:

| Profile | Purpose |
|---|---|
| GENERAL | Generic Raspberry Pi installation without HOME- or AALTO-specific configuration |
| HOME | Home environment with its predefined settings |
| AALTO | Aalto University CHEM environment with its predefined settings |

These commands work from a cloned repository or an extracted ZIP package.
Run them from the parent of the repository directory; if the extracted folder
has a different name, substitute that name in the `cd` command. Keep the full
directory tree together; Git metadata is not required.

`/opt/rpi` remains optional in every profile. Select hardware support in the
unified installer when needed; see the [unified setup guide](base/docs/unified-setup.md).

The Trixie reference installation provisions the operating system, APT
dependencies and Python environments. Scientific Imaging's own installer
installs imaging applications; no application wrappers or new startup system
are introduced. Meson/Ninja, the libcamera development library and the proven
DRM/EGL preview development dependencies are included in the Pi APT list,
without unnecessary version pins.

The first RPi version of VRecorder Full requires ext4 for persistent video
recording: the final metadata publication step uses a hard link. The detailed,
application-specific rationale is in the Scientific Imaging repository at
`docs/architecture/VRECORDER_STORAGE_FILESYSTEM_RPI_LINUX.md`. This requirement
does not apply to all data loggers or other laboratory applications.

See the [installation guide](base/README.md) and
[lab314 installation, maintenance and recovery](base/docs/lab314-maintenance.md)
for installation, updates and verification commands.

`rpi-share` and legacy `/opt/lab` tools retain their current paths; they are not
moved or removed when the Scientific Imaging paths are introduced.
[Rpi-share guide](base/docs/rpi-share.md).

### Legacy / profile-specific installation scripts

The existing HOME/AALTO scripts remain available for compatibility and maintenance.
From `rpi-images/trixie/base/install`, choose the appropriate script:

```bash
sudo bash run_rpi_home.sh
sudo bash run_rpi_aalto.sh
```

The existing startup sequence and the optional status of `/opt/rpi` remain
unchanged. On a camera system, enable `/opt/rpi` after the base installation
as described in the [base guide](base/README.md#camera-system-hardware-environment).
The existing optional `--with-cam-imgcheck PATH` pilot selection is also retained.

## Installation and maintenance

Normal installations resolve current compatible direct requirements from
`base/config/lab314/requirements.json`. Python stays within 3.14. The November
2026 exact locks remain optional with `--snapshot`; they are not the normal
version policy. Updates are explicit: selected scientific libraries, the full
scientific environment with `--all`, or a separate Spyder IDE and its matching
kernel. See [installation, updates and recovery](base/docs/lab314-maintenance.md).
