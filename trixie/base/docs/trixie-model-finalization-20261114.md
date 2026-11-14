# Trixie reference-installation finalization — 2026-11-14

> Historical finalization of the November 2026 snapshot. Normal installation and
> verification now use rolling direct requirements; exact snapshot behavior is
> opt-in. See [current maintenance policy](lab314-maintenance.md). Test results
> below are historical, not acceptance of a new rolling installation.

## Implementation and preservation of existing work

The local `rpi-images` worktree's Git status and existing changes were reviewed
before work began. Older GitHub files were not cloned or copied over them.
The installation, activation, verification and HOME/AALTO orchestration scripts
remained byte-for-byte unchanged. Only the following files were changed:

1. `trixie/README.md`: Trixie Full / ARM64, a general-purpose laboratory base,
   environment layout, 128 GB production and 64 GB test cards, and current commands.
2. `trixie/base/README.md`: production versions, optional `/opt/rpi` on camera
   systems, installer responsibilities, Git/ZIP source layout, locks and caches.
3. `trixie/base/install/packages/rpi-apt.txt`: 11 proven preview development dependencies.
4. `trixie/base/config/lab314/SHA256SUMS`: checksums for the three existing
   lock/contract files; the locks themselves were not changed.
5. `trixie/base/docs/rpi-env.md`: camera-system setup, Python 3.13, SPI/serial
   support and existing commands invoked through Bash.
6. `trixie/base/docs/sci-apps.md`: the pilot installer's relationship to the new application installer.
7. `trixie/base/docs/lab314/README.md`: a prominent reference to the latest
   accepted production report; earlier failure/rollback reports were retained.
8. This finalization report.

The retained paths are `/opt/conda`, `/opt/lab314`, `/opt/rpi`,
`/opt/sci/bin`, `/opt/sci/bin-rpi` and `/opt/sci/lib`. No new application wrappers,
installers, environment model or startup sequence were introduced.

## APT additions

`common-apt.txt` already contains `build-essential` and `pkg-config`.
The following packages were added to `rpi-apt.txt`:

```text
libcamera-dev meson ninja-build libboost-program-options-dev
libexif-dev libjpeg-dev libtiff-dev libpng-dev
libdrm-dev libx11-dev libepoxy-dev
```

These are the direct development dependencies established by Scientific
Imaging's current Meson project and the successful libcamera 0.8 / IMX477
build/preview test. The program-options-dev package supplies the Boost development
headers. No separate libboost-all-dev, Qt, TFLite, Hailo, OpenCV-C++ or
experimental-storage package set was added speculatively.

Candidates for all 11 packages were found in the Pi's existing APT cache.
`libcamera-dev` and `python3-libcamera`: 0.8.0+rpt20261104-1 from Raspberry Pi's
`archive.raspberrypi.com/debian` source. Debian's 0.4.0-7 appeared as an older
alternative and was not forced. `rpicam-apps`: 1.15.0-1, Meson: 1.7.0-1,
Ninja: 1.12.1-1+b1. APT sources, priorities and version pins were not changed.
These are read-only inspection results, not a fresh APT installation on a clean card.

C++ source compatibility with libcamera was corrected in the earlier Scientific
Imaging task. Installing an older libcamera library is not a substitute for that fix.

## Lab314 and the hardware environment

The current production environment was inspected without starting functional tests:

| Check | Result |
|---|---|
| Python | 3.14.10 |
| OpenCV | 5.0.0 |
| Shapely / GEOS | 2.2.0 / 3.14.1 |
| Installed Python distributions | 145 |
| Comparison with the `packages.json` contract | 145/145 matching versions, 0 differences |
| `/opt/rpi` | Python 3.13.13, prefix `/opt/rpi` |
| Hardware module discovery in `/opt/rpi` | Picamera2, libcamera, cv2, RPi.GPIO, gpiod, smbus2, spidev and serial were found |

Module discovery is not a GPIO/I2C/SPI/serial hardware test. On the current
system, spidev is available through the system installation; it was not built
into a new Conda environment. Hardware modules on a clean Full card will be
checked during the future installation test. This task did not change
`/opt/rpi`'s package selection.

The earlier production acceptance recorded **103 PASS, 0 FAIL, 0 SKIP**.
The Spyder, Variable Explorer, GUI and Bash results from that acceptance were
reused; those tests were not repeated. The detailed production report remains
local and is not part of the public repository. T9 paths in the retained local
reports identify development/rollback history, not inputs to the current installer.

HOME/AALTO still omit `/opt/rpi` by default. On a camera system it is created
after the base installation with the existing `create_rpi_env.sh`, before
Scientific Imaging camera applications are installed. The existing alternative
`--with-cam-imgcheck PATH` pilot selection creates a missing environment at its
original point in the sequence. Existing environments are not removed or recreated.

## Locks, GitHub and reproducibility

- Conda explicit lock: 23 ARM64/noarch URLs with MD5 checksums.
- Wheel lock: 144 fixed wheel URLs with SHA-256 checksums.
- These packages and Conda's pip form the matching 145-distribution Python contract.
- Python 3.14.10 and OpenCV wheel 5.0.0.93 (`cv2` 5.0.0) are pinned.
- The new `SHA256SUMS` verifies the three supplied lock/contract files. It is not
  a digital signature and does not change the existing installer's per-artifact checks.

The network check issued HEAD requests to 23 Conda and 144 wheel URLs, plus
the current Miniforge ARM64 bootstrap, GitHub repository and main ZIP URLs:
**170/170 PASS**. Redirects were followed. Package contents were not downloaded
and artifact hashes were not recalculated from network downloads. Lock-entry
hash formats and version consistency were checked locally. The lock contents
remained identical to those used for the accepted production installation.

Miniforge retains the existing `releases/latest` bootstrap selection; no new
policy was introduced to pin the exact Conda base version. The scientific
environment comes from explicit/require-hashes locks, not a new solver run.
APT and `/opt/rpi`'s existing Conda package selection retain their current version
policy. Reproducibility does not mean a bit-for-bit OS image rebuild from
changing APT repositories.

The existing installation scripts resolve resources relative to their own
directories. Static inspection used a source copy without `.git`: the required
resources were present, and install/config sources had no `file://`, Niobium
home-directory or T9 dependency. This supports using either a cloned repository
or an extracted ZIP source tree. No new environment was actually built from
either acquisition method during this task.

## Responsibilities and recording storage

The Trixie reference installation handles the OS, APT development libraries and
Python environments. Scientific Imaging's current installer handles applications.
This repository's cam-imgcheck pilot and the Scientific Imaging installer derived
from it were retained side by side; neither was removed, replaced or merged.
A second ownership chain is not adopted automatically for the same application.

The camera-system instructions reference VRecorder Full RPi's persistent-storage
ext4 requirement. The final metadata publication step uses a hard link, which
exFAT does not support. This reference is application-specific, not a general
storage restriction for all data loggers or applications. No new exFAT adapter
was implemented.

## Scoped checks and publication readiness

| Check | Result |
|---|---|
| Bash syntax: 30 install scripts, envrun and rpi-share | PASS, 32 files |
| Common/RPi APT lists: names, duplicates, no version pins | PASS, 64 unique names |
| Actual APT candidates for the added packages | PASS, 11/11 |
| Version consistency and hash formats of locks and the 145-distribution contract | PASS |
| Supplied checksums for the three lockfiles | PASS |
| Production metadata comparison with the current contract, read-only | PASS, 0 differences |
| Essential relative script resource paths | PASS |
| HOME/AALTO sequence and optional `/opt/rpi` | PASS, preserved |
| Local documentation links in the new instructions | PASS |
| HEAD availability of package, bootstrap, GitHub and ZIP URLs | PASS, 170/170 |
| New full regression / new Spyder GUI cycle | NOT RUN, earlier 103 PASS reused |
| OS/APT upgrade or Python environment reinstallation | NOT RUN, not authorized for this task |
| Separate clean 64 GB test card and cloned 128 GB production reference image | NOT TESTED, next hardware phase |
| Commit/push of this version and installation from the newly published GitHub ZIP | NOT RUN, publication approval required |

At the time of finalization, the local tree was prepared for commit/push approval;
new locks and other previously untracked files needed to be included in the same
publication. Availability of the existing GitHub URL did not establish that the
then-unpublished worktree could already be downloaded there.

Existing account defaults in startup profiles and host/user/share settings in
rpi-share HOME/AALTO examples were identified as profile-specific. They contain
no stored passwords and must be reviewed for the target installation before
cloning the reference image. They were not removed or replaced with new user logic.
The scoped inventory covered 80 files / approximately 0.50 MB. No files over
5 MiB, credential/key-named files or matches for the checked common private-key,
GitHub or AWS token formats were found. This was not an exhaustive audit of
all possible secrets. No new machine-specific settings, packages, caches,
videos or test environments were added to the repository. Existing development
reports were retained.

Niobium working data was kept in a verified RAM-backed `/tmp` directory. No
temporary installation, package cache or test recordings were created on the Pi.
The existing scripts' cache method for installation workloads was not changed:
lab314's cache resides next to the new prefix and is removed by the EXIT trap;
a failed prefix is retained as before.

**Deviations from agreed solutions: NONE.**
No proposed architecture changes were implemented. Possible future consolidation
of the application installers was not performed, and no new testing framework
was started.
