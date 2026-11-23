# Raspberry Pi OS Trixie — laboratory reference installation

`base/` is a general-purpose laboratory installation based on Raspberry Pi OS
**Trixie Full, 64-bit**, for camera systems, data loggers and other research
instruments.

The environment layout is:

| Path | Purpose |
|---|---|
| `/opt/conda` | Conda/Miniforge foundation |
| `/opt/lab314` | Scientific Python 3.14 with Spyder, its IPython kernel and GUI OpenCV |
| `/opt/rpi` | Separate hardware Python 3.13 environment using Trixie's APT camera libraries |
| `/opt/sci/bin` | general Scientific Imaging commands |
| `/opt/sci/bin-rpi` | Pi-specific Scientific Imaging commands |
| `/opt/sci/lib` | application support files |

New users: follow the [hands-on installation guide](../QUICKSTART.md).

## Installation profiles

Use `setup-rpi.sh` for all new Raspberry Pi OS Trixie installations. Setup offers
keyboard layout selection before asking for a profile. On Raspberry Pi 5 Model B
it also initializes the hardware interfaces. If setup pauses for a reboot, run
the same command again after reboot.

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

All profiles select `/opt/rpi` by default. It can be disabled through
customization or `--no-hardware`. [Unified setup guide](base/docs/unified-setup.md)

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
for installation, updates and verification commands. Start the
[lifecycle menu](base/docs/unified-setup.md#installation-lifecycle) with
`sudo bash setup-rpi.sh --manage`.

`rpi-share` and legacy `/opt/lab` tools retain their current paths; they are not
moved or removed when the Scientific Imaging paths are introduced.
[Rpi-share guide](base/docs/rpi-share.md).

### Legacy / profile-specific installation scripts

The historical [HOME](base/install/legacy/run_rpi_home.sh) and
[AALTO](base/install/legacy/run_rpi_aalto.sh) scripts are archived under
`base/install/legacy/` for existing installations.

## Installation and maintenance

Normal installations resolve current compatible direct requirements from
`base/config/lab314/requirements.json`. Python stays within 3.14. The November
2026 exact locks remain optional with `--snapshot`; they are not the normal
version policy. Updates are explicit: selected scientific libraries, the full
scientific environment with `--all`, or an explicitly selected external IDE and its matching
kernel. See [installation, updates and recovery](base/docs/lab314-maintenance.md).
