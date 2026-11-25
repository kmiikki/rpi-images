# rpi-share

`rpi-share` is a portable Bash CLI tool for mounting remote storage (Aalto or NAS) on a Raspberry Pi or Linux system.

It is designed for simple and reliable data transfer between lab instruments and shared storage.

---

## What it does

* Mounts remote storage locally using SSHFS or CIFS
* Uses existing authentication (SSH / Aalto AD)
* Allows file transfer using a file manager (e.g. Nemo) or terminal
* Safely unmounts when finished

---

## Typical usage (recommended)

Start guided mode:

```bash
rpi-share
```

Follow the prompts:

1. Select gateway
2. Select storage location
3. Enter your username
4. Copy files
5. Press Enter to disconnect

---

## Direct usage

You can skip guided mode:

```bash
rpi-share -g example-gateway -s example-share
```

With explicit username:

```bash
rpi-share -g example-gateway -s example-share -u username
```

---

## Installation

From the repository root, install the client and its shared offline catalog module:

```bash
sudo bash trixie/base/install/install_rpi_share.sh
# To update an established /opt/lab/bin installation in place:
sudo bash trixie/base/install/install_rpi_share.sh --prefix /opt/lab
```

The source-tree client can also be run directly with Bash. When copying the
client manually, keep `rpi_share_catalog.py` beside it; the builder entrypoint
uses the same module. No lab314 environment is required.

---

## Configuration (required)

`rpi-share` requires a JSON configuration file.

Search order:

```text
1. Explicit --config FILE, if selected
2. ./rpi-share.json
3. ~/.config/rpi-share.json
4. /etc/rpi-share/rpi-share.json
5. <script_dir>/rpi-share.json
```

Override with:

```bash
rpi-share --config /path/to/file.json
```

---

## Common commands

```bash
rpi-share --list
rpi-share --status
rpi-share --cleanup
rpi-share --cleanup --remove-dirs
rpi-share --check
```

---

## Mount location

Mounted shares appear under:

```text
/media/rpi-share/<gateway>/<share>
```

This is a local mount location, not a remote server path. For example:

```text
/media/rpi-share/example-gateway/example-share
```

---

## Important notes

* Close file manager windows before disconnecting
* Do not use lazy or forced unmount
* Access rights are controlled by the remote system (e.g. Aalto AD)
* Catalog navigation filters control visibility; remote permissions control access

---

## Aalto usage notes

* Use the gateway recommended for your role in your administrator's private AALTO catalog.
* The same logical share may use different remote paths on different gateways
* Use shared storage for research data (not personal home directories)

---

## Troubleshooting

When a HOME catalog offers a default mapping, review the gateway, share,
destination and authorization notes before confirming. A browse destination
then prints its URL and invokes the file manager. In a plain SSH session,
open the printed URL from a desktop session. If the graphical opener exits
with an error, the command reports that failure. Confirm server connectivity
and access in the file manager or by completing a mount and an authorized
file operation.

Check active mounts:

```bash
rpi-share --status
```

Clean up:

```bash
rpi-share --cleanup
```

Check dependencies:

```bash
rpi-share --check
```

---

## Advanced usage

See:

```text
docs/rpi-share-advanced.md
```

---

## Design principles

* No stored credentials
* No privilege escalation
* Uses existing authentication
* Safe and predictable behavior
* Minimal user friction


## Offline catalogs, hierarchy and CSV editing

The existing version-1 configurations and commands above remain supported.
For version-2 hierarchical destinations, navigation groups, offline tree views,
configuration precedence and lossless JSON ↔ CSV editing in LibreOffice Calc,
see the [catalog specification and commands](rpi-share-catalog.md).
Software installation and per-user configuration are integrated into the
[unified setup workflow](unified-setup.md). Selecting a navigation group grants
no remote rights: the gateway authorizes login and remote filesystem ACLs
authorize directory access. `--tree-all` displays the entire configured guide
without contacting a server.
