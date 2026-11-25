# Installation profile builder

Installation profiles are versioned JSON **preferences for setup**, separate from
rpi-share JSON catalogs (remote gateways and destinations). The standard-library
builder runs with the system Python; it needs no Conda environment or network.
GENERAL, HOME and the existing AALTO/CHEM deployment remain supported. Other
organizations customize a base without adding school-specific installer code.

From `rpi-images/trixie/base/install`, start the menu without sudo:

```bash
python3 -B profile-builder.py
```

Create a base profile, edit numbered settings, validate, preview, and save.
Load an existing file to edit it. Use generic accounts such as `researcher` and
hostnames such as `rpi-workstation`. Keep real site profiles outside Git, for
example `~/workstation.json`. Profiles contain no credentials. Never enter
passwords, tokens, private keys or password hashes into preference values.

## Export, validate, preview and install

```bash
python3 -B profile-builder.py --export GENERAL --output ~/workstation.json
python3 -B profile-builder.py --validate ~/workstation.json
python3 -B profile-builder.py --preview ~/workstation.json
bash setup-rpi.sh --profile-file ~/workstation.json --plan
sudo bash setup-rpi.sh --profile-file ~/workstation.json
```

Export accepts GENERAL, HOME or AALTO. Output is UTF-8 JSON, mode 0600, with a
stable field order. Existing files are refused unless `--replace` is explicitly
specified; the menu asks for `REPLACE`. Symlink destinations are refused. Back up
profiles before replacing them. No profile is automatically published.

Preview uses the current host's accounts and existing environments, and performs
no provisioning. Missing accounts are displayed as simulated creations; this
never authorizes creation during installation. For the setup plan command, a
missing intended account still requires an explicit recovery choice. Actual
installation requires the existing confirmation and interactive password rules.

The built-in commands remain supported:

```bash
sudo bash setup-rpi.sh --profile GENERAL
sudo bash setup-rpi.sh --profile HOME
sudo bash setup-rpi.sh --profile AALTO
```

AALTO always uses the existing CHEM account policy, regardless of the invoking
username. `--school CHEM` remains a compatibility alias; AALTO rejects
`--school custom`. Its dedicated maintenance account is required: optional
additional accounts supplement it, and an empty additional-account list or
`--no-additional-users` is rejected. Explicit primary-account selections and
recovery safeguards are retained. Use GENERAL for other custom deployments.

## Version 1 format

All fields below are required; unknown fields and unsupported versions are
rejected. `null` means the original base/host default, not a stored username or
snapshot of the machine that exported the profile. This preserves the built-in
account selection, hostname, SSH/NTP and component behavior on the target host.
For GENERAL/HOME, an empty additional-user array explicitly selects no additional
accounts. AALTO rejects that value because its maintenance account is required.

```json
{
  "version": 1,
  "name": "Research workstation",
  "base": "GENERAL",
  "settings": {
    "primary_user": null,
    "additional_users": null,
    "hostname": null,
    "ssh": null,
    "ntp_servers": null,
    "lab_prefix": "/opt/lab314",
    "ide_prefix": null,
    "components": {
      "system": null,
      "conda": null,
      "lab314": null,
      "spyder": null,
      "hardware": null,
      "wolfram": null,
      "share": null,
      "imaging": null
    },
    "share": {
      "source": "later",
      "path": null,
      "users": [],
      "prefix": null,
      "default_group": null
    },
    "imaging": {
      "source": null,
      "apps": []
    }
  }
}
```

| Setting | Values and effect |
|---|---|
| `base` | GENERAL, HOME or AALTO; original profile policy and defaults |
| `primary_user` | Local username or null for base/host selection |
| `additional_users` | Array of local usernames; null for base defaults, `[]` for none in GENERAL/HOME; AALTO always retains its maintenance account |
| `hostname` | Single DNS label or null to keep the Imager hostname |
| `ssh` | `keep`, `enable`, `disable`, or null for base policy |
| `ntp_servers` | Nonempty array of hostnames/IP addresses, or null for base servers |
| `lab_prefix`, `ide_prefix` | Canonical absolute environment paths; null IDE uses existing APT fallback |
| `components` | Boolean choices or null for each existing component's base default |
| `share.source`, `share.path` | `auto` (discover by profile), `later` (defer), `example`, `json`, `csv`. Supply an absolute path for JSON or CSV. |
| `share.users` | Local catalog owners; empty array defaults to primary account |
| `share.prefix` | Absolute software prefix or null for existing location detection |
| `share.default_group` | Catalog navigation group or null; requires a selected catalog |
| `imaging.source`, `imaging.apps` | Reviewed local source path or null, and explicit application-name array |

Paths to catalogs and Imaging sources are absolute so installation does not
depend on the current directory. Catalogs are loaded and validated locally when
planning. Structural validation of preferences does not prove a host has the
required existing dependencies, accounts, catalog groups or application source;
preview on the intended host as well. HOME/AALTO retain their required share
client. `/opt/rpi` remains optional and separate from scientific Python.

## Overrides and approval

Explicit CLI settings override corresponding file values. Repeated CLI options
replace the file list; a CLI share-source choice replaces the file source choice.
Selecting `--share-later` also clears the file's catalog-group override. For example:

```bash
bash setup-rpi.sh --profile-file ~/workstation.json --hostname rpi-workstation \
  --no-hardware --ntp-server time.example.invalid --share-later --plan
```

This placeholder NTP host is for syntax illustration; use a reachable server for
installation. No override retains the original profile NTP servers.

Files cannot store `--yes`, recovery decisions, `--apt-upgrade`,
`--update-existing`, `--replace-share-config` or `--imaging-approved`.
Those remain explicit runtime decisions. The existing primary-administrator
`NOPASSWD: ALL` policy grants full administrative privileges; additional accounts
join the sudo group without a new per-user passwordless rule. SSH disablement
can interrupt remote administration. The installer displays actual account
names and security-relevant choices before applying. See the
[setup reference](unified-setup.md) for recovery and separate account removal.
