# Unified Raspberry Pi scientific installation

`install/setup-rpi.sh` is the only supported entry point for new Raspberry Pi OS
Trixie installations. Run it after Raspberry Pi Imager has installed Raspberry
Pi OS Trixie Full 64-bit and the machine has booted. Profile installation
supports Raspberry Pi 4 and 5. Preboot supports Raspberry Pi 5 Model B. Imager
normally sets the hostname, first user/password, network, optional SSH, locale
and timezone.
Setup preserves that first account and hostname unless explicitly instructed.
It never installs an OS, formats storage or automatically removes an account.

Run setup from the intended desktop account. Use the same command to resume
after reboot or to apply the current installer's configuration to an existing installation.

```bash
cd rpi-images/trixie/base/install
sudo bash setup-rpi.sh
```

Keep the complete tree from the clone or extracted ZIP. Substitute the actual
directory name as needed. Git metadata is optional.

## First-boot preparation on Raspberry Pi 5

On Raspberry Pi 4 and 5 Model B, setup offers keyboard layout selection after
you approve the profile's installation plan.
The numbered menu starts with Finnish, Swedish, German, US and UK layouts.
Select **Show all available keyboard layouts** for the installed XKB registry.
Search by code or name, move between pages, select a displayed number or choose
**Back**. Finnish is the first-run default. A previously used layout is kept
on reruns, including changes made outside setup.

Setup installs `rpi-keyboard`, applies the selected layout and verifies the
stored configuration. It reports whether a running labwc session was detected
and a reload requested. Test typing to confirm the active layout.

On Raspberry Pi 5 Model B, preboot also enables `i2c_arm` and `spi` in
`/boot/firmware/config.txt` and schedules `i2c-dev` for boot when needed. Setup
shows the proposed changes, asks for approval and checks the live device nodes.
It saves a
`config.txt.preboot.bak.*` beside the firmware file before changing it. A repeat
run with matching settings creates no extra backup or configuration edits.
Active firmware includes, ambiguous conditional or overlay parameter scopes,
and custom Device Tree directives require manual review. [Raspberry Pi firmware configuration](https://www.raspberrypi.com/documentation/computers/config_txt.html)

On a reliably identified first installation, setup refreshes the configured APT
repositories and simulates a full Trixie package upgrade after the early hardware
configuration. Package removals require a separate confirmation of the displayed
list. The full upgrade keeps locally changed package configuration files and
records its result in the installation journal. An interrupted first upgrade
is resumed when the same setup command is run again.

If hardware, kernel or firmware changes require a reboot, setup can combine
them in one reboot after the upgrade. It saves the approved profile and pauses
before installing scientific software. Answer `y` to reboot from setup, or reboot manually
with `sudo reboot`. Then run the same `sudo bash setup-rpi.sh` command again.
The installer verifies the running kernel, page size and live I²C and SPI devices.
If the boot settings are correct and nodes still fail to appear,
setup reports the problem for investigation. A reboot flag lives in `/run`
for the current boot. Startup runs the regular system services only.

### Raspberry Pi 5 kernel compatibility

Spyder's formatted Help embeds a web browser. The Qt5 WebEngine build used by
this environment fails to display that content with the Pi 5's default 16 KiB
pages. When Spyder is selected, setup offers the Raspberry Pi OS stock ARM64
4 KiB kernel. This also applies to existing installations on their next normal
rerun. The switch has its own approval prompt.

On the target, the plan reports whether verification is pending, a boot edit
needs approval, a reboot is due, or the compatible kernel is ready. A ready
result checks the running release and page size against the stock image, modules
and initramfs. Unexpected firmware settings or a mismatch after a recorded
reboot are reported for review.

The kernel switch addresses the original page-size issue. On the clean tr3
Trixie installation, Spyder's formatted Help displayed documentation and ran
JavaScript with 4 KiB pages. A separate standalone test of the same Conda
QtWebEngine build still hit a renderer sandbox error. Verify the application's
own embedded views. Use Plain Text Help or an external browser if a formatted
pane is blank. [tr3 acceptance results](tr3-acceptance.md)

Setup checks `kernel8.img`, its matching `initramfs8` and installed modules
before editing boot files. It adds this selection in a marked Pi 5 section of
`/boot/firmware/config.txt` and saves the previous file beside it:

```ini
[pi5]
kernel=kernel8.img
[all]
```

Setup keeps an existing verified selection, including a manually configured
`kernel=kernel8.img`. Other explicit kernel selections and ambiguous firmware
settings require manual review. After reboot, the following should report
`4096` and a running version ending in `-rpi-v8`:

```sh
getconf PAGESIZE
uname -r
```

To restore the default Pi 5 kernel, remove the whole marked Scientific Python
Environment kernel block. Preserve other boot changes. If the system cannot
boot, use another machine to access the card's boot partition and restore the
saved pre-kernel `config.txt.preboot.bak.*` after checking its contents. Reboot
and check the live page size again. To retain your choice on future installer
runs, use `sudo bash setup-rpi.sh --no-kernel-4k` and approve the plan once.
This option records the preference and leaves the current boot file in place.
On 16 KiB pages, use Plain Text Help or open the documentation in an external
browser. Raspberry Pi OS supplies and updates both kernel variants.
[Raspberry Pi kernel documentation](https://www.raspberrypi.com/documentation/computers/linux_kernel.html)

### Moving an installation card between Raspberry Pi 4 and 5

Use `adapt-rpi-model.sh` from the install directory for Raspberry Pi 4 Model B
and Raspberry Pi 5 Model B. For example, before moving a card from a Pi 4 to
a Pi 5, preview and then apply the preparation on the source machine:

```sh
bash adapt-rpi-model.sh --target pi5 --plan
sudo bash adapt-rpi-model.sh --target pi5 --prepare
```

Use `--target pi4` for the reverse move. Shut down the source, move the card
and boot the target. Then check the running model, kernel and page size:

```sh
bash adapt-rpi-model.sh --plan
uname -r
getconf PAGESIZE
```

The tool checks the target board's Device Tree, the Pi 4 firmware where
applicable, and the common `kernel8.img`, initramfs and modules. It reuses the
Pi 4 default and the installer-managed Pi 5 section. A card with these settings
needs no edit in either direction. Starting from stock settings, preparing for
Pi 5 can add the same 4 KiB setting as setup, while preserving the Pi 4 settings.
The adaptation tool changes only the boot selection if needed. Keep
`/opt/lab314`, `/opt/rpi` and Wolfram on the card and verify the applications and
connected devices on the target. Startup still depends on each board's EEPROM
boot order, the actual card and any board-specific overlays or peripherals.
Review custom kernel, firmware or conditional boot settings before moving the card.
[Raspberry Pi model-specific boot settings](https://www.raspberrypi.com/documentation/computers/config_txt.html)

When an edit is required, the tool asks for approval and prints the backup name.
Preview its rollback with `bash adapt-rpi-model.sh --rollback BACKUP --plan` and
apply with sudo if appropriate. Automatic rollback checks that the boot file has
not changed since that edit. If it has, review the marked block and backup
before making any manual change. A change on the running board takes effect
after reboot. If the target cannot boot, put the card back in the source board
or inspect the boot partition from another system.

**Physical Raspberry Pi 4 migration: UNTESTED — pending validation on
physical Raspberry Pi 4 hardware.** Both directions have fixture tests.

### Keyboard layout

For noninteractive selection, use `sudo bash setup-rpi.sh --keyboard-layout de`
with a profile if running without a terminal. Reset and component removal
preserve the chosen layout and the keyboard utility.

Run `rpi-keyboard` or `rpi-keyboard --list` to list the installed XKB layouts, and
`rpi-keyboard --current` to see the stored system and available labwc keyboard
assignments. Choose a layout from the desktop account that should receive the
change. The utility requests sudo when a change is needed and delegates it to
`raspi-config nonint do_configure_keyboard`. Trixie's labwc-aware implementation
reloads the desktop keyboard without a logout or reboot. The status command
reports stored values. Verify the active layout by typing in the local desktop.
[Raspberry Pi OS Trixie keyboard implementation](https://github.com/RPi-Distro/raspi-config/blob/trixie/raspi-config)

```bash
rpi-keyboard --current
rpi-keyboard us
rpi-keyboard fi
```

The keyboard layout controls key mapping. The interface language comes from
the language settings, and individual locale categories control regional
formatting. Over SSH, an unavailable forwarded category such as `LC_TIME`
falls back to the target's usable settings for installer commands. Check
`locale -a` on the Pi for the generated locales. When applying a keyboard
change as root, the utility can generate a missing requested locale already
enabled in `/etc/locale.gen` with `locale-gen --keep-existing`. To select a new
regional preference deliberately, use `sudo dpkg-reconfigure locales` and
choose the desired default interface language separately.

### WLAN country and Ethernet

GENERAL, HOME and AALTO show the WLAN country in the installation plan.
Interactive setup accepts a two-letter ISO country code. Setup prefers the
country configured for boot, then the current valid global domain. On an
unconfigured target it offers Finland (`FI`). For example, use
`--wlan-country DE` for a Pi operated in Germany. A stale plan stops if a
different valid country has appeared since inspection.

On Trixie, setup delegates country changes to `raspi-config`, uses WLAN-only
rfkill operations and enables the NetworkManager Wi-Fi radio. The connection
profiles stay in NetworkManager. Association and a wireless password are
optional. Before a planned installation reboot, setup applies the approved
country so the resumed installation can check the boot setting and live radio.

### Hardware acceptance

On a clean Raspberry Pi 5 Model B, run `sudo bash setup-rpi.sh`. Choose a layout
and test typing when the reboot question appears. Reboot if requested, then verify the
device nodes, page size and persisted keyboard layout before rerunning the same
setup command. The saved profile is resumed. Check the installation summary.

```bash
ls -l /dev/i2c-1 /dev/spidev0.*
id -nG
rpi-keyboard --current
```

If `i2cdetect` is installed and the connected devices support bus probing, run
`i2cdetect -y 1` from an account with I²C device access. Device access and live
layout switching require a target Pi.

## Installation profiles

Choose the profile for your deployment when running setup.

| Profile | Purpose |
|---|---|
| GENERAL | Generic Raspberry Pi installation without HOME- or AALTO-specific configuration |
| HOME | Home environment with its predefined settings |
| AALTO | Aalto University CHEM environment with its predefined settings |

An explicitly changed hostname also updates an existing matching `127.0.1.1`
alias in `/etc/hosts`; unrelated entries and aliases are preserved.

Normally, choose a profile and approve the plan. The installer derives account,
SSH, NTP and software defaults from the profile and asks when needed for account
recovery. Enter `customize` at the approval prompt to change settings and review
the revised plan. Passwords are entered only through
the operating system's interactive `passwd` program for newly created accounts.
Existing passwords are retained. `--yes` approves the installation plan; it does
not bypass password input or authorize a reboot or account removal.

## Advanced installation options

`--plan` and `--dry-run` preview the profile and, on Raspberry Pi 5 Model B,
preboot settings without changing the system. On a terminal the preview offers
the same profile prompts as setup. Outside a terminal the default preview uses
GENERAL. On development hosts the profile preview identifies the Pi 5 preboot
stage and omits firmware inspection.

```sh
# Full preview without sudo
bash setup-rpi.sh --plan

# Preboot-only maintenance on Raspberry Pi 5 Model B
sudo bash setup-rpi.sh --preboot

# Public installation, retaining the invoking Imager account:
sudo bash setup-rpi.sh --profile GENERAL

# HOME: primary NTP time.mikes.fi, existing HOME SSH-enable default:
sudo bash setup-rpi.sh --profile HOME --hardware --share-later

# Existing AALTO/CHEM deployment defaults:
sudo bash setup-rpi.sh --profile AALTO --school CHEM --share-later

# Reusable customized installation preferences (kept outside Git):
sudo bash setup-rpi.sh --profile-file /absolute/private/workstation.json

# Completely non-mutating preview; can run without sudo on a development host:
bash setup-rpi.sh --profile GENERAL --primary-user researcher --plan
```

Replace example usernames with existing local accounts. If the intended account
does not exist, select recovery explicitly as described below. Root without a
reliable `SUDO_USER` must name the primary account; setup does not guess from an
unrelated account's home directory. A mismatched `SUDO_UID` is rejected.

## Profiles and privileges

| Profile | Primary account | Additional accounts | NTP | SSH default | Wolfram | rpi-share |
|---|---|---|---|---|---|---|
| GENERAL | Imager/invoking user | none | public pool / Cloudflare | keep | optional | optional |
| HOME | Imager/invoking user | none | time.mikes.fi | enable, as in existing HOME provisioning | optional | included |
| AALTO (CHEM deployment) | Preconfigured primary account, configurable | Dedicated maintenance account, configurable | ntp.aalto.fi | keep | selected, deselectable | included |

AALTO always selects the existing CHEM-specific account policy, independently of
the invoking username. It is not a hierarchy of University schools. The legacy
`--school CHEM` option remains compatible; `--school custom` is rejected for
AALTO before provisioning. For other organizations, use the
[profile builder](profile-builder.md) with GENERAL.

AALTO always includes its dedicated maintenance account. Repeated
`--additional-user` options add optional accounts alongside it, with no duplicate
entries. `--no-additional-users` and an explicitly empty additional-account list
are rejected for AALTO. GENERAL/HOME retain their existing exact-list and
no-additional-user behavior. Additional accounts do not receive a new per-user
NOPASSWD rule. Explicit primary-account selection and recovery safeguards remain
available; review the actual names in the displayed plan.

The approved primary/invoking administrator's `NOPASSWD: ALL` policy is retained.
It is also provided to an explicitly recovered primary administrator. Shared
`account-policy.sh` validates sudoers before publishing the existing policy form.
Existing global/group sudo policies are not redesigned. No unrelated accounts
receive privileges silently. `--ssh keep|enable|disable` is explicit; disabling
SSH may disconnect remote administration and is shown in the plan.

## Username typo recovery

If Imager created `wronguser` but `correctuser` was intended, setup offers create, keep and
cancel. Equivalent commands are:

```sh
# Preview creating the intended account; existing wronguser remains:
bash setup-rpi.sh --profile GENERAL \
  --primary-user correctuser --recovery create --plan

# Create correctuser with secure interactive password provisioning, preserving wronguser:
sudo bash setup-rpi.sh --profile GENERAL \
  --primary-user correctuser --recovery create

# Deliberately retain and use the original invoking account instead:
sudo bash setup-rpi.sh --profile GENERAL \
  --primary-user correctuser --recovery keep
```

The new account starts with a disabled login shell. Only after password and
requested privilege setup succeed is its normal shell enabled. A failed setup
locks/expires the new account and retains its data for review. Existing accounts
are never silently renamed, recreated, password-reset or deleted. Without a
terminal, a plan requiring a new password fails before provisioning changes.

After creating the correct account, log out of the incorrect account, log in as
the correct account, and verify `sudo -n true`. Removal is a separate maintenance
operation, never a stage of setup:

```sh
# Run from a successful correctuser login, through sudo:
sudo python3 rpi-accounts.py --remove wronguser --replacement correctuser --plan

# After reviewing the reported files, tasks, SSH and autologin references:
sudo python3 rpi-accounts.py --remove wronguser --replacement correctuser \
  --apply --login-verified --files-reviewed
```

The removal command requires a separate `REMOVE wronguser` confirmation (or the
explicit `--confirm-remove wronguser` argument). It refuses the current login,
system users, active old sessions/processes, an unverified replacement login,
unusable replacement sudo access, scheduled tasks, lingering user services and
unreviewed account references in inspected SSH/desktop/cron files. Account data
and the home directory are retained: `userdel` is invoked without `-r`. Review
all other old UID-owned files, user services, backup jobs and residual sudo rules
separately; the command does not claim to discover every site-specific consumer.

## Saved installation preferences

Use the [profile builder](profile-builder.md) to create, edit, validate and preview
local versioned JSON preferences. These files are distinct from rpi-share catalogs.

```sh
python3 -B profile-builder.py --export GENERAL --output ~/workstation.json
python3 -B profile-builder.py --validate ~/workstation.json
sudo bash setup-rpi.sh --profile-file ~/workstation.json
```

Explicit CLI settings override the corresponding file settings. Repeated CLI
options replace that file list; selecting a CLI share source replaces the file's
source choice. `--ntp-server time.example.invalid` can be repeated to replace the
base NTP list. No NTP override retains the original profile default. Files cannot
authorize account recovery, apply confirmation, upgrades, catalog replacement or
application approval. Runtime safety checks and confirmation remain in force.

## Software and existing installations

All components remain independently executable. Setup calls their current
implementations in dependency order: profile policy, APT, Conda, Scientific
Python with integrated Spyder, shell/envrun, Raspberry Pi hardware Python,
optional tools and verification. All profiles select hardware Python by default.
Use `--no-hardware` to omit that environment while retaining early I²C/SPI setup.

```sh
sudo bash setup-rpi.sh --profile GENERAL --hardware --wolfram --share --share-later
sudo bash setup-rpi.sh --profile AALTO --school CHEM --no-wolfram --no-hardware
```

Existing valid environments are kept and verified. If the native lab314
environment has no integrated Spyder, setup can add the pinned Spyder only when
the dependency solver can preserve every installed package. Older environment
layouts may require a separate, reviewed migration.
The shared scientific defaults for GENERAL, HOME and AALTO include SHAP,
PyWavelets, Optuna, Plotly, Hypothesis, Polars and XGBoost. The normal
`sudo bash setup-rpi.sh` command adds missing packages from the current list
and verifies their imports. If Conda cannot add the packages while preserving
the installed builds, setup reports the conflict for review.
New lab314 environments use Conda-forge for Python 3.14, the IDE, the kernel and
GUI OpenCV. Open **Spyder (Scientific Python)** from the desktop menu or run
`rpi-lab314-spyder`. A standard install uses the integrated Spyder.
`/opt/rpi` is a separate Python 3.13 bridge to Trixie's Picamera2 and libcamera
packages. [Spyder and migration](spyder-lab314.md)

### Interactive figures on the desktop

On the desktop, use `fig.show()` from Spyder or a local lab314 Python script
to open an interactive Plotly figure. GENERAL, HOME and AALTO open figures
in a separate Firefox window, so no browser account or desktop keyring setup
is needed. Other local lab314 tools that use Python's standard browser
launcher open pages in the same way. Spyder's embedded Help uses its own
viewer. [Plotly renderer documentation](https://plotly.com/python/renderers/#browser)

Each window uses a private profile in the session's temporary storage in
RAM. Closing the browser removes the profile and its data. If a forced stop
prevents cleanup, the runtime directory is cleared after the last logout or
at reboot. Keep using your usual browser for sign-ins
and bookmarks. Existing browser profiles keep their own settings and password
protection. Programs that select their own browser or use an embedded viewer
still follow their own settings. The installer preserves explicit
`PLOTLY_RENDERER` and `BROWSER` settings, and Python sessions without a
graphical display keep their existing defaults.

### Reruns and maintenance

| Operation | Behavior |
|---|---|
| Initial `sudo bash setup-rpi.sh` | Choose a profile, approve changes and install the selected components. A qualifying clean OS installation may receive the reviewed first OS upgrade. |
| Same command on an installed system | Use the saved GENERAL, HOME or AALTO profile and explicit selections. Check the latest definitions, install missing selections and keep working environments and package versions. |
| Configuration refresh | Run the normal command from the newer installer. It updates installer-owned files when they match the last recorded version, backs up changed files, and reports files preserved for local review. No refresh option is needed. |
| `sudo bash setup-rpi.sh --manage` → **Update All** | Review and request package maintenance separately. Individual package repair and update actions also remain available. |

When setup cannot identify an old installation's profile, choose it once and
review the plan. Local catalog contents, data, Spyder preferences and unrelated
lines in the system shell configuration are kept. If adding a missing package
would require replacing an installed dependency, the stage reports the blocker
and leaves the dependency maintenance to `--manage`. Package operations can
leave an incomplete stage on error. Review the log and rerun after correcting
the cause. The summary reports updated or preserved files and any reboot needed.

Wolfram is selected by default for AALTO and optional otherwise. Existing
Engine/`wolframscript` installations are kept. A missing package candidate is
reported as unavailable. Installation reuses `install_optional_wolfram.sh`.
An installed Engine or successful CLI check is not a graphical Mathematica/Wolfram
acceptance result. See [Wolfram licensing and component details](wolfram.md).

## Share configuration and ownership

Before starting setup, place your private JSON catalog in the directory you run
setup from, beside `setup-rpi.sh`, or in the directory containing the extracted
package. The top-level package directory itself is also searched.

| Profile | Production filename |
|---|---|
| GENERAL | `rpi-share.json` |
| HOME | `rpi-share.home.json` |
| AALTO | `rpi-share.aalto.json` |

You can keep all three files in one directory. Setup proposes only the filename
for the selected profile. A matching GENERAL catalog enables the optional
rpi-share component unless you pass `--no-share`. HOME and AALTO always
include the client. If several matching catalogs are found, setup lists their
absolute paths and asks you to choose. For unattended installation with several
matches, pass `--share-json PATH` or `--share-later`.

The plan displays the absolute path of the validated catalog for approval.
An explicit `--share-json PATH` overrides discovery and the profile file's
source choice. When no match is available, choose **share** in the approval
prompt to select a JSON, import a CSV, or see the path to the generic public
template. Copy the template to a private location, edit it for your site, and
select the resulting file. Approving a plan with no catalog defers
configuration. For GENERAL without a matching catalog, select rpi-share in
**customize** or pass `--share` to see these options.

```sh
sudo bash setup-rpi.sh --profile HOME --share-json /etc/rpi-share/site.json
sudo bash setup-rpi.sh --profile AALTO --school CHEM \
  --share-csv /etc/rpi-share/shares.csv --default-group staff
sudo bash setup-rpi.sh --profile GENERAL --share --share-later
```

The client keeps the existing `/opt/lab` software prefix when an installed
`/opt/lab/bin/rpi-share` is detected, otherwise uses `/usr/local`. Override with
`--share-prefix /absolute/prefix` if needed.

Configuration is written as `~/.config/rpi-share.json` for the selected primary
account, using that local account's actual home and ownership, not root's home.
Use repeated `--share-user USER` to configure an explicit set of existing/planned
accounts. New files are mode 0600. Existing configurations are kept unless
`--replace-share-config` explicitly authorizes replacement. Setup always
preserves the selected source itself. Software-only updates never overwrite
catalogs. Symlinked configuration destinations are refused. If installation
pauses for a reboot, keep the selected source available at the same path.
Repeat `--replace-share-config` on resumption if you still want replacement.

Keep production catalogs outside public Git repositories. The repository
ignores the three production filenames and excludes them from Git source
archives. Build releases from the tracked source tree. The public
`rpi-share.example.json` and `rpi-share.example.csv` use reserved example hosts.

See [the reversible CSV/JSON format](rpi-share-catalog.md) for Calc editing,
hierarchy, groups, full-tree navigation and the authentication/ACL boundaries.

## Optional Scientific Imaging

Scientific Imaging remains a separate application repository. Setup does not
clone an unpublished GitHub repository or substitute the older cam-imgcheck
pilot for the complete application installer.

```sh
sudo bash setup-rpi.sh --profile HOME --hardware --share-later \
  --imaging-source /absolute/reviewed/scientific-imaging \
  --imaging-approved --imaging-app vrecorder-full-rpi.py --imaging-app cam-preview
```

The administrator must have reviewed that local application source and selected
its applications. Setup calls its `scripts/install/01-install.sh` and
`02-diagnose.sh`. Missing/unapproved source or missing selections produce a
DEFERRED component, allowing base provisioning to finish without claiming an
application installation. Application updates, diagnostics and removal continue
through Scientific Imaging's own `03-update.sh`, `02-diagnose.sh` and
`04-remove.sh`. `rpi-images` owns OS/accounts/APT/environments/hardware/share setup;
Scientific Imaging owns application and native application lifecycles.

## Independent installation and maintenance

```sh
sudo bash install_rpi_base.sh
sudo bash install_conda_base.sh
sudo bash create_lab314_env.sh
sudo bash create_lab314_env.sh --package spyder-kernels
sudo bash create_lab314_env.sh --package numpy
bash create_lab314_env.sh --plan
sudo bash create_rpi_env.sh
sudo bash install_envrun.sh
sudo bash install_rpi_share.sh
sudo bash install_optional_wolfram.sh
bash verify_rpi_lab314.sh
bash verify_rpi_env.sh
```

The lab314 rerun above explicitly requests its normal rolling update. Use the
[existing maintenance workflow](lab314-maintenance.md) for targeted updates,
external IDE maintenance, backups and exact snapshot reproduction.

### Legacy / profile-specific installation scripts

The historical [HOME](../install/legacy/run_rpi_home.sh) and
[AALTO](../install/legacy/run_rpi_aalto.sh) scripts are archived under
`install/legacy/` for existing installations. [Legacy script options](../README.md#legacy--profile-specific-installation-scripts)

## Installation lifecycle

Open the maintenance menu from `trixie/base/install`.

```sh
sudo bash setup-rpi.sh --manage
```

Status detects components that are installed, missing, incomplete, untracked or
changed since the recorded operation. Verify runs the installed component
checks. Neither applies preboot or changes the keyboard. A previously completed
verification is shown separately from current verification. GUI and physical
hardware checks still need a target Pi.

### LXTerminal zoom shortcuts

With the `fi` or `se` keyboard layout, setup configures the invoking desktop
user's selected LXTerminal. Ctrl + + zooms in, Ctrl + − zooms out, and Ctrl + 0
resets zoom. Existing explicit definitions and markers for absent definitions
are kept in that user's `~/.config/lxterminal/lxterminal.conf`. Open a new
LXTerminal session to use the updated accelerators.
An unchanged older installer block is upgraded to Ctrl + 0 while retaining its
original settings for reset.

Status identifies the recorded owner. Reset or
`sudo bash setup-rpi.sh --manage --action remove --component terminal-shortcuts --plan`
previews restoration from the recorded account. Restoration keeps other terminal
settings and preserves the file for review if a managed binding or marker has
changed. Setup skips other keyboard layouts and other selected terminals.

### Repair and update

For an existing Pi, preview and apply just the WLAN repair with the corrected
checkout. The commands work over Ethernet SSH. Add `--wlan-country XX` to
the repair to choose the country where the Pi operates.

```sh
sudo bash setup-rpi.sh --manage --action repair --component wlan --plan
sudo bash setup-rpi.sh --manage --action repair --component wlan
sudo bash setup-rpi.sh --manage --action verify --component wlan
```

Run the verify command again after the next normal reboot to check persistence.
It compares the boot setting, the global section of `iw reg get`, WLAN rfkill
and NetworkManager's radio setting. The driver can report a separate PHY
country such as `99`. A missing or hardware-blocked adapter produces a deferred
result. For a failed check inspect `rfkill list wlan`, `iw reg get`,
`nmcli radio` and the `cfg80211.ieee80211_regdom` token in
`/boot/firmware/cmdline.txt`.

If package output is indented or overwritten in a terminal, check the command
in the installation log and inspect `stty -a` in that terminal. Logged APT
transactions use line-oriented dpkg output. The combined stream and exit
status are recorded under `/var/lib/rpi-images/logs`.

For later full OS upgrades, preview the cached APT plan and then refresh and
approve the current plan:

```sh
sudo bash setup-rpi.sh --manage --action os-upgrade --plan
sudo bash setup-rpi.sh --manage --action os-upgrade
```

The action uses the existing Trixie repository configuration. It checks package
list retrieval and the distribution codenames, keeps modified dpkg conffiles,
and requires the displayed removals to be explicitly approved. Confirmation is
rechecked against the actual APT transaction. A completed upgrade is checkpointed
even when it requires a reboot. The journal preserves completion across a
scientific environment reset. Logs survive reboot under `/var/lib/rpi-images/logs`.

Preview named repairs and updates before approving them. The scientific updater
reports its Conda or pip solver output and keeps Python 3.14. Hardware Python
maintenance keeps Python 3.13 and the distro camera libraries. A selection
changes its own package set and necessary dependencies. Close applications
using the environment and take a separate copy of important data before maintenance.

```sh
sudo bash setup-rpi.sh --manage --action status
sudo bash setup-rpi.sh --manage --action verify --component lab314
sudo bash setup-rpi.sh --manage --action repair --component lab314 --package numpy --plan
sudo bash setup-rpi.sh --manage --action update --component spyder --plan
```

Remove `--plan` to review and approve the change. For scripted operations,
`--yes` approves repair or update. A damaged package can be reinstalled in its
existing environment. Repair preserves unowned configuration and refuses an
automatic rebuild. Scientific Imaging still uses its own manager. Automatic
delegation requires the recorded source and a reviewed, administrator-owned
checkout. For another source, use the application's manual lifecycle procedure.

### Component removal and reset

```sh
sudo bash setup-rpi.sh --manage --action remove --component hardware --plan
sudo bash setup-rpi.sh --manage --action reset --plan
```

Apply a reviewed plan with the corresponding confirmation word `REMOVE` or
`RESET`. For automation use `--confirm REMOVE` or `--confirm RESET`. The plan
lists actions and conflicts. Environment removal requires ownership evidence,
matching recorded files, and no detected consumers. Conda stays installed while
dependent environments remain. APT packages are retained unless the installer
can prove ownership and limit the simulated removal to the selected package.

Reset reverses known installer-owned changes. It preserves the selected
keyboard layout and `rpi-keyboard`, users, passwords, privileges, home directories,
catalogs, measurements, and unrelated software. SSH and hostname restoration
require an interactive local console. Hardware restoration can need a manual
reboot and may turn enabled interfaces off. Packages shared with the OS and
changes without reliable ownership evidence need manual review. The result is
an installer-managed reset. A reimage is a different operation.

The private versioned manifest is
`/var/lib/rpi-images/installation.json`. Original managed file contents are
stored by checksum in `original/`; the manifest records package inventory,
configuration, service states, component status, and completed or interrupted
operations. Older installations can have an unknown original state. For
unknown or drifted items compare the current setting and any original backup
manually before changing it. Run `sudo bash setup-rpi.sh` again after reset
to reinstall missing components. The keyboard choice is reused.

### Diagnose and resume a failed Scientific Python installation

On the Pi, use the new ZIP and run:

```sh
sudo bash setup-rpi.sh --manage --action diagnose
```

For the tr2 failure at `kernel_info`, check the existing integrated Spyder and
its kernel in place:

```sh
sudo bash setup-rpi.sh --manage --action repair --component spyder --plan
```

The check prints the kernel process status and its captured stderr and stdout
on failure. It reports the page size and checks PyArrow and PyZMQ in separate
processes. For a completed installation, approve the launcher repair and run
the [Spyder desktop diagnostic](spyder-lab314.md#verification) as the desktop
user. If provisioning stages remain, rerun `sudo bash setup-rpi.sh` to resume
the recorded profile. Keep the existing Scientific Python prefix.

If startup still fails, share the `kernel_info` result, kernel stderr and exit
information. Installation logs are under `/var/lib/rpi-images/logs/` and survive
reboot. They record the failed command, child output and stage. Dependent checks
are shown as blocked. See [16 KiB kernel verification](lab314-maintenance.md#16-kib-kernel-verification).

If lab314 has valid metadata, use targeted repair when the log identifies a
damaged package. If the metadata is incomplete or the prefix fails
verification and cannot be repaired, preview:

```sh
sudo bash setup-rpi.sh --manage --action quarantine --plan
```

An approved quarantine moves only an incomplete `/opt/lab314` directory to a
new sibling backup. It refuses a verified environment, unsafe paths and running
consumers. Confirm with `QUARANTINE` after review. Resume with the same normal
setup command. Existing valid Miniforge, account and profile settings are reused.

## Verification and acceptance

Setup reports identity/accounts, sudo, SSH/time synchronization, selected
components, environment verification, configuration source/default group,
deferred components and failures. It reuses current environment verification.
Hardware and GUI checks, remote login, directory existence and filesystem ACLs
require separate authorized acceptance on the target machine.

Run the complete regression suite from the repository root. On Niobium,
confirm that `/tmp` is the RAM-backed mount and check its available capacity
before starting. The subshell removes its own temporary directory on exit or
interruption.

```sh
(
  set -eu
  test "$(findmnt -no FSTYPE -T /tmp)" = tmpfs
  df -h /tmp
  TMPDIR=$(mktemp -d /tmp/rpi-regression.XXXXXXXX)
  export TMPDIR PYTHONDONTWRITEBYTECODE=1
  trap 'rm -rf -- "$TMPDIR"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  python3 -B -m unittest discover -s trixie/base/tests -v
)
```

The suite uses temporary fixtures, real terminal pairs and mocked provisioning.
The optional LibreOffice checks use an isolated profile for CSV→ODS→CSV
round trips. [Clean HOME results and physical retests on tr2](tr2-home-acceptance.md)

## Update an installed system

The maintenance menu has **Update All installed components**. Preview the same
operation from the extracted installation archive:

```sh
sudo bash setup-rpi.sh --manage --action update --all --plan
sudo bash setup-rpi.sh --manage --action update --all
```

The plan uses the saved component selection. It refreshes APT lists in a
temporary directory, solves the installed Conda environments, and lists changes
to installer-owned settings and programs. The second command shows the plan
again and asks for approval. If APT proposes removing any packages, it asks for
separate typed confirmation. A Conda package with no replacement blocks the
whole update. User-edited settings and optional components that were not
selected are preserved. Close Spyder and other programs using the affected
environments before applying the plan.

For noninteractive execution after review, pass `--yes --expect-plan ID` with
the ID printed by the preview. A different plan requires a new review.
The update records its result, verifies the installed components, and reports
any pending manual reboot. Spyder's graphical acceptance remains a separate
desktop check.
