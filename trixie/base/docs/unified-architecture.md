# Unified Trixie setup and rpi-share architecture

## Provisioning boundary

Raspberry Pi Imager installs the OS and creates the first account, password,
hostname and initial network settings. `install/setup-rpi.sh` starts after boot.
It is a small Bash entrypoint for `setup_rpi.py`, a system-Python orchestrator.
The orchestrator detects identity, resolves an explicit plan, obtains approval,
calls existing component scripts and reports verification results. On Raspberry
Pi 5 Model B, setup runs preboot before asking for the profile. A first-install
APT upgrade can run before the same manual reboot. Setup verifies the hardware
interfaces on the next invocation and reuses a completed upgrade.
The keyboard menu uses the same installed XKB registry as `rpi-keyboard`.
Plan mode previews both stages without writes. Apply requires Raspberry Pi 4/5,
Trixie and ARM64.

GENERAL, HOME and AALTO share this one implementation. AALTO retains the existing
CHEM deployment's primary account default and required maintenance account.
The pure account-policy resolver in `rpi_accounts.py` is shared by setup, profile
validation and the legacy AALTO entrypoint. AALTO does not depend on the invoking
username: `--school CHEM` remains compatible, while custom policy and empty
additional-account overrides are rejected before host changes. Optional accounts
supplement the required account. Other organizations customize GENERAL through
`profile-builder.py`, without organization-specific branches. Identity recovery and
additional accounts remain explicit. Hostname changes are included in the
approved plan and applied through `hostnamectl`; reconnection/reboot advice is
reported.

Versioned installation preferences are validated by `installation_profiles.py`
and translated into the existing parser's options. Explicit CLI settings take
precedence, including replacement of repeated-option lists and share-source
choices. Null settings retain the original host-dependent defaults. Profile files
contain no credentials or apply/replacement/recovery authorizations. The builder's
preview uses the same resolver in plan mode; it never calls provisioning. These
preferences are separate from runtime rpi-share catalogs.

| Responsibility | Existing/shared component |
|---|---|
| Pi 5 I²C, SPI, i2c-dev and initial keyboard setup | `preboot.py`, `rpi-keyboard` |
| Account creation/recovery and guarded separate removal | `rpi_accounts.py`, `rpi-accounts.py` |
| Approved primary/invoking NOPASSWD policy | `account-policy.sh`, reused by `install_rpi_base.sh` |
| Installation preference export/edit/validation | `profile-builder.py`, `installation_profiles.py` |
| Profile NTP/SSH configuration | `pre_profile.sh`; standalone `pre_home.sh`/`pre_aalto.sh` |
| First-install OS upgrade and later reviewed updates | `os_upgrade.py`, existing Trixie APT repositories |
| Scientific OS dependencies | `install_rpi_base.sh`, existing APT package lists |
| Conda bootstrap | `install_conda_base.sh` |
| Python 3.14.x scientific installation/maintenance | `create_lab314_env.sh`, existing policy/updater/checker |
| Integrated Spyder and kernel matching | Conda-forge lab314 solve and installed IDE metadata |
| Explicit external IDE maintenance | `update_lab314.py --ide-prefix`, separate from the default |
| System-compatible hardware bridge selected by default | `create_rpi_env.sh`, `verify_rpi_env.sh` |
| Shell integration / explicit environment runner | `enable_lab314_autoactivate_rpi.sh`, `install_envrun.sh` |
| Optional Wolfram | existing install/uninstall scripts; CLI and GUI status separated |
| Share client/software-only installation | `rpi-share`, `install_rpi_share.sh` |
| Offline catalog interchange/validation/navigation | `rpi_share_catalog.py`, `rpi-share-builder.py` |
| Scientific Imaging applications and native builds | separate application's approved `01-install.sh`–`04-remove.sh` |

Scientific Python environment creation/update logic is not duplicated. lab314
and `/opt/rpi` remain separate. IDE maintenance does not turn the scientific
environment into an IDE environment. Existing standalone installers and update
interfaces remain available. Existing valid environments are kept unless their
established maintenance route is explicitly selected. Failed package operations
are reported without a claim of transactional rollback. The maintenance menu
reuses these component scripts and reads the private installation journal for
ownership, drift, diagnostic logs and interrupted stages. Reset reverses only
changes whose originals and installed state the journal can establish.

## Identity and password lifecycle

The original sudo invoker is distinguished from root. Missing/ambiguous identity
requires an explicit primary-account choice. Passwords are never stored in
configuration, supplied through argv/environment, logged or reset automatically.
A new account is created with a disabled shell; secure interactive `passwd` and
requested privileges precede shell enablement. Failure locks/expires the new
account. The approved primary administrator receives the established
`NOPASSWD: ALL` rule; additional selected sudo-group accounts do not silently
receive a new per-user rule.

Account removal is a distinct maintenance command after successful login and
sudo verification as the replacement administrator. It refuses the current
login/system account, old sessions/processes, an unusable replacement
administrator and outstanding inspected task/autologin/SSH references. It requires
separate confirmation and preserves the home and UID-owned data. Sites review
remaining consumers before authorizing removal.

## Catalog and runtime boundary

```text
Administrator's local JSON or CSV
             |
             v
System-Python lossless converter + local validator
             |
             v
Validated JSON, per-user or explicitly selected system file
             |
             v
rpi-share: offline tree/group selection -> selected destination
             |
             v
Existing SSHFS / CIFS / SMB browse lifecycle
             |
             +--> Gateway authenticates and authorizes remote login
             +--> Remote filesystem permissions/ACLs authorize directory access
```

CSV and JSON are two reversible representations of the same local configuration,
not competing systems. JSON remains the runtime format. Two CSV columns encode
JSON Pointers and typed JSON literals, preserving nested/unknown fields and absent
versus explicit values. Validation checks structure/references/cycles/backend
syntax without any network request. Output is deterministic and atomically
published only after complete validation.

Navigation categories and parent metadata form a local tree independent of actual
remote directory layout. SSHFS can target an explicit deep directory directly;
CIFS separates its share root and subdirectory; SMB browse preserves valid URLs.
Gateways may expose different paths for the same logical destination.

Navigation groups use union semantics for a primary role and additional custom
groups. `all`/`--tree-all` provide unfiltered views. Visible children retain parent
context even under a filtered category. Existing explicit-only, `--all`, `--admin`
and direct CLI behavior remain distinct. Navigation is not proof of staff/student
status or remote permission. `allowed_groups` describes an intended audience.
The gateway and remote filesystem make the authoritative decisions.

## Configuration and update ownership

Public functionality consists of the complete client, builder, validator,
generic schema/examples, installer integration, documentation and offline tests.
Private inventories need not be available for public build/install/test.
The original HOME/AALTO JSON files remain unchanged during this migration.

Explicit config, current-directory config and per-user config retain their
priority; a documented system fallback precedes script-directory fallback.
Setup writes only an explicitly selected catalog to the intended local user's
home with correct ownership and restricted permissions. Software updates do not
overwrite catalogs. Multiple local owners are individually selected.

No remote connection, real ACL acceptance, physical camera/GUI behavior or clean
image installation is implied by static and mocked automated tests. See the
[installation guide](unified-setup.md) and [catalog specification](rpi-share-catalog.md)
for operational commands and acceptance boundaries.
