# Unified Raspberry Pi scientific installation

The entrypoint is `install/setup-rpi.sh`. It runs after Raspberry Pi Imager has
installed Raspberry Pi OS Trixie Full 64-bit and the machine has booted
successfully. Raspberry Pi 4 and 5 are supported targets. Imager normally sets
the hostname, first user/password, network, optional SSH, locale and timezone.
Setup preserves that first account and hostname unless explicitly instructed.
It never installs an OS, formats storage or automatically removes an account.

## Installation profiles

The unified installer is the recommended initial installation method for all users:

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

An explicitly changed hostname also updates an existing matching `127.0.1.1`
alias in `/etc/hosts`; unrelated entries and aliases are preserved.

The interactive workflow asks for a deployment profile, identity, additional
accounts, SSH policy, software and share configuration. It shows an account and
component plan before requesting confirmation. Passwords are entered only through
the operating system's interactive `passwd` program for newly created accounts.
Existing passwords are retained. `--yes` approves the installation plan; it does
not bypass password input or authorize account removal.

Explicit equivalents:

```sh
# Public installation, retaining the invoking Imager account:
sudo bash setup-rpi.sh --profile GENERAL

# HOME: primary NTP time.mikes.fi, existing HOME SSH-enable default:
sudo bash setup-rpi.sh --profile HOME --share-later

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
implementations in dependency order: profile policy, APT, Conda, selected external
Spyder IDE, lab314, shell/envrun, optional hardware environment, Wolfram,
rpi-share, optional Scientific Imaging, verification.

```sh
sudo bash setup-rpi.sh --profile GENERAL --hardware --wolfram --share --share-later
sudo bash setup-rpi.sh --profile AALTO --school CHEM --no-wolfram --no-hardware

# Optional separate, administrator-selected Spyder IDE prefix:
sudo bash setup-rpi.sh --profile GENERAL --ide-prefix /opt/research-ide
```

Existing valid Conda/lab314/hardware/IDE environments are kept by default and
verified. Incomplete or symlinked environments are rejected rather than replaced.
`--update-existing` explicitly requests the established rolling update path for
lab314 and the selected IDE. Without that option, selecting a different external
IDE against an existing lab314 requests only `spyder-kernels` and its necessary
dependencies through the current updater. The IDE metadata determines the range;
APT Spyder remains the fallback. Python stays in 3.14.x. `/opt/rpi` retains its
system-Python-compatible APT bridge and is never merged into lab314.

No full OS upgrade is implicit. `--apt-upgrade` explicitly enables the existing
`DO_APT_UPGRADE=1` policy. Normal APT dependency installation may update the named
packages according to APT's own semantics. Package operations are not fully
transactional. A failed stage is reported with completed and blocked stages;
rerun the reviewed command after correcting the cause. Setup does not perform
destructive rollback or recreate existing environments as recovery.

Wolfram is selected by default for AALTO and optional otherwise. Existing
Engine/`wolframscript` installations are kept. A missing package candidate is
reported as unavailable. Installation reuses `install_optional_wolfram.sh`.
An installed Engine or successful CLI check is not a graphical Mathematica/Wolfram
acceptance result. See [Wolfram licensing and component details](wolfram.md).

## Share configuration and ownership

Choose an existing JSON, a local CSV, an explicitly selected public example, or
configuration later. HOME/AALTO always install the client but do not silently
activate a generic or legacy site inventory.

```sh
sudo bash setup-rpi.sh --profile HOME --share-json /etc/rpi-share/site.json
sudo bash setup-rpi.sh --profile AALTO --school CHEM \
  --share-csv /etc/rpi-share/shares.csv --default-group staff
sudo bash setup-rpi.sh --profile GENERAL --share --share-example
```

The client keeps the existing `/opt/lab` software prefix when an installed
`/opt/lab/bin/rpi-share` is detected, otherwise uses `/usr/local`. Override with
`--share-prefix /absolute/prefix` if needed.

Configuration is written as `~/.config/rpi-share.json` for the selected primary
account, using that local account's actual home and ownership, not root's home.
Use repeated `--share-user USER` to configure an explicit set of existing/planned
accounts. Files are mode 0600. A different existing configuration is preserved
unless `--replace-share-config` explicitly authorizes replacement. Software-only
updates never overwrite catalogs. Symlinked configuration destinations are refused.

The original public HOME/AALTO JSON files remain available unchanged. The new
public `rpi-share.example.json`/`.csv` are generic examples using reserved example
hosts. Real site inventories can remain entirely outside Git.

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
sudo bash uninstall_optional_wolfram.sh
bash verify_rpi_lab314.sh
bash verify_rpi_env.sh
```

The lab314 rerun above explicitly requests its normal rolling update. Use the
[existing maintenance workflow](lab314-maintenance.md) for targeted updates,
external IDE maintenance, backups and exact snapshot reproduction.

### Legacy / profile-specific installation scripts

The standalone HOME/AALTO scripts remain available for compatibility and maintenance.
From `rpi-images/trixie/base/install`, choose the appropriate script:

```sh
sudo bash run_rpi_home.sh
sudo bash run_rpi_aalto.sh
```

Their existing optional arguments remain available; see the
[base guide](../README.md#legacy--profile-specific-installation-scripts).
The unified installer remains the recommended initial installation method for
GENERAL, HOME and AALTO.

## Verification and acceptance

Setup reports identity/accounts, sudo, SSH/time synchronization, selected
components, environment verification, configuration source/default group,
deferred components and failures. It reuses current environment verification.
Hardware and GUI checks, remote login, directory existence and filesystem ACLs
require separate authorized acceptance on the target machine.

Run only the new isolated tests from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover \
  -s trixie/base/tests -p 'test_rpi_*.py' -v
```

These tests use temporary fixtures and mocked provisioning/connections. Optional
LibreOffice tests use a separate temporary profile and real local CSV→ODS→CSV
conversions. No real accounts, mounts, Aalto/Home connections or `/opt` changes
are used by the automated tests.
