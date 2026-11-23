# Raspberry Pi Scientific Python acceptance

**Accepted on Raspberry Pi 5.** The automated tr3 checks and the manual
clean HOME installation on tr1 passed for the release scope below. The tr3
tests began on 22 November 2026 on an 8 GB Raspberry Pi 5 with a separate
64 GB installation card and a Camera Module 3 (IMX708).

## Manual clean-install acceptance on tr1

On 23 November 2026, the operator accepted staging version
`trixie-staging-20261123-3f499f36811a` on physical Raspberry Pi 5 hardware.
The staging ZIP SHA-256 was
`2e07aadebf7667600f38bec1d4df9c8b2c78a632028b311bd1b911ad5e1c3476`.

| Check | Result | Operator observation |
|---|---|---|
| Clean installation | PASS | The HOME profile completed on the clean tr1 card. |
| Kernel page size | PASS | `getconf PAGESIZE` returned `4096`. |
| Spyder GUI and IPython | PASS | Spyder opened, the IPython console worked and formatted HTML Help rendered. |
| OpenCV | PASS | OpenCV 5.1.0 imported in the scientific environment. |
| Scientific defaults | PASS | SHAP, PyWavelets, Optuna, Plotly, Hypothesis, Polars and XGBoost were available. |
| Interactive Plotly | PASS | Firefox rendered the figure and interactive zoom worked. |
| Normal installer rerun | PASS | `sudo bash setup-rpi.sh` preserved the Conda environments and installed packages. Managed configuration reconciliation reported no changes and no additional reboot was required. |

## Automated tr3 installation and hardware checks

| Check | Result | Evidence |
|---|---|---|
| Clean Raspberry Pi OS | PASS | Trixie Full ARM64, Raspberry Pi reference image dated 2026-10-06, pi-gen stage 5, 47 GiB available on the root filesystem. No existing scientific, hardware or Miniforge prefixes or installer journal. |
| Remote access | PASS | The target reported hostname `tr3`; public-key login and noninteractive sudo worked. The reference card was outside the test. |
| Initial kernel | PASS | `6.18.50+rpt-rpi-2712`; `getconf PAGESIZE` returned `16384`. |
| Installed 4 KiB boot files | PASS | The installer read the ARM64 image header, matched `kernel8.img` and `initramfs8` to the installed v8 files, and checked the corresponding module tree for `6.18.50+rpt-rpi-v8`. |
| Profile selection | PASS | Interactive Finnish keyboard, GENERAL, default Scientific Python, integrated Spyder and hardware bridge. No Wolfram, rpi-share or Scientific Imaging selected. |
| Profile policies | PASS for read-only plans | GENERAL, HOME and AALTO/CHEM display the expected time servers. HOME enables SSH and AALTO selects Wolfram by default. AALTO on the clean image requests an explicit account recovery choice; previewing with `--recovery create` did not create accounts. |
| Initial OS upgrade | PASS | Reviewed and applied 212 upgrades, 23 new packages and replacement of `libcamera0.7` by `libcamera0.8`. The installer requested and received separate approval for the proposed removal. |
| I²C and SPI boot configuration | PASS | The installer showed the changes, asked for confirmation and created a backup before enabling the interfaces. Live device checks follow reboot. |
| 4 KiB selection and reboot | PASS | After the OS upgrade, the installer verified the new stock files and asked separately before selecting `kernel8.img`. One reboot switched the system to `6.18.60+rpt-rpi-v8` and `4096` byte pages. The file has exactly one `kernel=kernel8.img` setting. |
| Live devices and stored keyboard | PASS | `/dev/i2c-1`, `/dev/spidev0.0`, and `/dev/spidev0.1` appeared after reboot. System and active user's saved keyboard configuration both report `fi`. Physical typing is untested. |
| System camera preview | PASS | `rpicam-apps` 1.15.0, libcamera 0.8.0, Picamera2 package 0.3.39. `rpicam-hello --list-cameras` found IMX708; a three-second, 2304 × 1296 Wayland EGL preview exited successfully. |
| System Picamera2 | PASS | Trixie's system interpreter captured a 1296 × 2304 × 3 RGB frame containing image data, closed the IMX708 and reacquired it successfully. The `/opt/rpi` bridge is tested separately. |
| Resume over SSH | FAIL first attempt, access corrected | SSH survived reboot. The new sudo session requested a password and exited before launching setup. The operator supplied a temporary sudo rule, verified independently of the timestamp cache. Setup resumed with the same command and saved profile. |
| System package resolution | FAIL first attempt, PASS after correction | The resolver refused to remove preinstalled `python3-rpi-lgpio` for the older `python3-rpi.gpio` package. A separate APT simulation confirmed the conflict. The installed Trixie provider imported `RPi.GPIO` on Pi 5. The revised package list retained that provider and the installer completed. |
| Package and environment setup | PASS | Miniforge and prebuilt conda-forge packages created `/opt/lab314` and the separate Raspberry Pi system-module bridge `/opt/rpi`. The installer exited 0. Spyder is in lab314. |
| Scientific Python and OpenCV | PASS | Python 3.14.10, OpenCV 5.1.0, NumPy 2.5.5, SciPy 1.18.1, pandas 3.1.1 and Matplotlib 3.11.2 passed calculations, graphics and image round trip. HighGUI displayed a real Qt window on the desktop. The installer also passed Shapely, HDF5, NetCDF and native kernel checks. |
| Spyder imports, GUI and IPython | PASS | Spyder 6.1.8, spyder-kernels 3.1.7, IPython 9.18.1 and PyQt5 5.15.11. The real-display test passed separate consoles, plots, Variable Explorer, kernel restart and clean close. Launching the installed desktop entry opened a mapped Spyder (Python 3.14) window. |
| Spyder formatted Help and interpreter switch | PASS | The operator saw formatted Help via Ctrl+I. Separately, a real-display test read a unique rendered docstring from the Help pane's DOM and checked a JavaScript result of 42. It ran three distinct IPython processes using `/opt/lab314` → `/opt/rpi` → `/opt/lab314`. The hardware kernel imported the system libcamera binding. |
| Standalone QtWebEngine HTML and JavaScript | FAIL | Qt5 QtWebEngine 5.15.15 build `h6406779_4` (Chromium 87.0.4280.144) loaded from lab314 and crashed its standalone local HTML renderer with code 31 on 4096-byte pages. `strace` confirmed ARM64 `clone3` triggered `SIGSYS/SYS_SECCOMP`. This run reached a different failure from the 16 KiB page allocator error. No Chromium protections were disabled. |
| Raspberry Pi hardware bridge | PASS | `/opt/rpi/bin/python` imported Picamera2 and libcamera from system dist-packages. The test captured a 1296 × 2304 × 3 IMX708 frame, checked pixels and reacquired the device after release. The hardware bridge used system OpenCV 4.10.0. Camera bindings are intentionally unavailable inside the separate Scientific Python 3.14 environment. |
| No-argument rerun | PASS | Reused GENERAL and the selected components. Before/after APT inventory, Conda metadata hashes, prefix inodes, managed file timestamps and hashes, boot setting and shell marker counts were identical. The first tests exposed an unnecessary APT query for the virtual ExifTool package name. After removing that alias from the required list, the rerun kept the existing `exiftool` executable and skipped APT work. |
| Updated definition and user settings | PASS | A second installer copy changed only the desktop launcher's description. The normal command updated the launcher, saved a byte-identical backup of its prior version and preserved a test setting in the user's shell file. Repeating the revised installer kept the launcher inode and timestamp. The normal installer restored the original launch definition from the original source with no package changes. |
| Card adaptation plans | PASS on running Pi 5 | Both target plans verified their firmware files, stock v8 image/initramfs and installed modules. The boot configuration hash was unchanged. Physical Pi 4 migration is **UNTESTED — pending validation on physical Raspberry Pi 4 hardware.** |
| Wolfram package and CLI | PASS | GENERAL initially left it uninstalled. YES installed `15.0.1+202608182322` from the Pi OS repository (2174 MB download, 5444 MB installed). The desktop account ran `wolframscript` and received 4 and 7919. It exported a sine plot as SVG. Package setup reported the EULA already accepted, and the test used the supplied Raspberry Pi authorization. |
| Wolfram NO with existing install | PASS | The installer reported Wolfram unselected, and the before/after inventory and configuration hashes were identical. |
| Wolfram managed removal and reinstall | PASS | Managed removal affected only `wolfram-engine`. The installer reinstalled it and `Prime[1000]` returned 7919. Installed package inventories, Conda metadata and tracked configuration matched the pre-removal snapshots. |
| Wolfram after a further reboot | UNTESTED | SSH became unreachable after the successful reinstall, before the planned post-reboot verification. The earlier 4 KiB reboot was verified separately. |
| Mathematica desktop | PASS | With the XWayland GUI, the generated `tr3-graphics.nb` notebook opened in a mapped Wolfram Mathematica window. The first unqualified launch did not produce a notebook window in the test timeout. |

The [standalone QtWebEngine follow-up](tr3-qt5-webengine.md) explains why the
two rendering paths differ and records the status of Chromium isolation.

## Required scientific packages

**Original staging package: FAIL.** All seven imports were absent from the
installed Python 3.14 environment. The shared scientific manifest included them,
but the Raspberry Pi manifest did not. GENERAL, HOME and AALTO all use that
same Raspberry Pi list. The old rerun verified the packages listed there
without adding missing requirements, so both initial installation and rerun
missed the omission. The 22 November ZIP is superseded.

**Corrected argumentless rerun on tr3: PASS.** It added fifteen Conda packages,
consisting of the seven required defaults and eight dependencies. All 850
existing Conda package metadata files across the three prefixes retained their
hashes. The Linux package inventory, prefix inodes and managed configuration
were identical before and after. The second `sudo bash setup-rpi.sh` reported
that every default was present and ran no package transaction.
The corrected fresh-install manifest also passed an ARM64 dry solve on tr3.
It selected the seven versions below and all the other requested scientific
packages. The test created no second environment.

| Required default | Import and version | Representative test |
|---|---|---|
| SHAP | `shap` 0.52.0 | Exact feature attribution satisfied additivity |
| PyWavelets | `pywt` 1.10.0 | Haar wavelet transform and reconstruction |
| Optuna | `optuna` 5.1.0 | Grid search found the expected optimum |
| Plotly | `plotly` 7.1.0 | External Chromium drew the interactive SVG and handled a zoom event |
| Hypothesis | `hypothesis` 6.170.17 | Generated examples passed a list property |
| Polars | `polars` 2.1.0 | Grouping and aggregation gave the expected sums |
| XGBoost | `xgboost` 3.4.2 | CPU model trained and classified the test rows |

The first external-browser invocation timed out while Chromium requested access
to the desktop keyring. The rerun used a disposable browser profile and kept
browser credentials out of the test. Plotly's `browser` renderer used its
loopback HTTP server to deliver the figure to Raspberry Pi OS Chromium
156.0.8078.79. The test checked the actual line in the SVG, a Plotly relayout
event and the updated axis range. QtWebEngine was neither imported by the
test nor changed by the package transaction.

### Chromium keyring prompt

The initial automated launch of a new Chromium profile produced the dialog.
The operator entered an empty password to continue that test. tr3's Wayland
desktop uses LightDM automatic login. A read-only Secret Service check after
the dialog found the default collection unlocked, with one item and no
`login` alias. The check counted items without reading their contents or
changing the collection. The ordinary Chromium profile already existed.
The evidence points to Chromium initializing its desktop credential store for
the fresh test profile. The state of the keyring at the time of the original
prompt is unknown.
[Chromium password storage](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/linux/password_storage.md)

Chromium may prompt again if its credential store needs setup or becomes
locked, for example after automatic login. The earlier Chromium test's
temporary profile and credential-store selection applied only to that test.
Use the shared scientific browser below for routine visualization. The
installer leaves existing keyrings and normal browser profiles in place.
[Secret Service locking and prompts](https://specifications.freedesktop.org/secret-service/latest/ch03.html) · [GNOME automatic keyring unlocking](https://wiki.gnome.org/Projects/GnomeKeyring/Pam)

### Keyring-free scientific browser

| Check | Status | Evidence |
|---|---|---|
| Argumentless reconciliation | Hardware PASS, tr3 | The saved profile and time settings were GENERAL. The first run installed the lab314 startup file and the Firefox launcher. The second kept their contents and timestamps, the APT inventory, Conda metadata, boot settings and both environment directories. |
| Ordinary Plotly 7.1.0 | Hardware PASS, tr3 | A desktop lab314 session used plain `fig.show()` twice in Firefox 160.0. The SVG rendered and manual mouse zoom changed the x-axis. The test recorded no Secret Service prompt call during the launches. |
| Other local HTML | Hardware PASS, tr3 | A standard Python `webbrowser.open()` call rendered a local HTML test page through the same launcher. |
| Profile isolation | Hardware PASS, tr3 | Every test used a fresh profile under the RAM-backed user runtime directory. All test profiles were removed and the checked normal-browser files retained their hashes. The original keyring was left in place. |
| Installation profile equivalence | Configuration PASS | Mocked GENERAL, HOME and AALTO installs applied the same launcher and lab314 startup file and did not rewrite either on rerun. The GENERAL and HOME browser workflows also passed on Pi 5 hardware. AALTO has configuration-level coverage. |

No browser setup or keyring password is required for the default lab314
desktop workflow. Existing Spyder Help and standalone QtWebEngine findings
remain applicable to embedded content. [Setup and scientific browser guide](unified-setup.md#interactive-figures-on-the-desktop)

The existing ARM64 environment also contained Python ABI 3.14 cp314, the
GPL FFmpeg 9.1.0 build, and CPU builds of Arrow 26.0.1 and PyArrow Core.
The shared desktop definition names a separate `apache-arrow-proc` CPU
selector. The tested ARM64 CPU build is present directly in the Arrow
packages. The functional package comparison found no other missing
shared scientific libraries.

The temporary tr3 test sudo policy was removed, and a new sudo request
required authentication.

## Remaining limitations and deferred checks

- **UNTESTED — pending validation on physical Raspberry Pi 4 hardware.**
  Pi 4 to Pi 5 and Pi 5 to Pi 4 passed fixture tests. The target plans passed
  read-only checks on tr3. Physical card transfers and booting on a Pi 4
  remain unverified.
- **FAIL — standalone Qt5 QtWebEngine with its default sandbox on tr3.**
  Even with 4 KiB pages, the renderer received `SIGSYS/SYS_SECCOMP` on
  ARM64 `clone3`. Spyder's formatted Help passed on both Pi 5 installations.
  The installer leaves Chromium sandbox settings unchanged. [Diagnosis and scope](tr3-qt5-webengine.md)
- The additional Wolfram check after a later reboot remains **UNTESTED**.
  The CLI and desktop results on tr3 are recorded above.
- Additional I²C/SPI peripherals, interactive Jupyter browser sessions and
  embedded HTML tools beyond Spyder were outside the verified combinations.
- **Update All** remains available in the management interface and has local
  regression coverage. No full package update was applied to the accepted
  scientific versions during rerun testing.

The [setup guide](unified-setup.md#reruns-and-maintenance) describes the
differences between initial installation, normal reconciliation, refreshing
configuration with a newer installer and **Update All**.

## Local verification

All shell scripts in the installer directory passed `bash -n`. The local
Python suite ran 417 tests, with 416 passing and one skipped. These results
cover local regression tests. The hardware and desktop results are reported
separately above.
