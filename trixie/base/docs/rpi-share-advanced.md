# rpi-share – Advanced Guide

This document describes the internal design, configuration, and behavior of `rpi-share`.

---

## Overview

`rpi-share` is a portable Bash tool for mounting remote storage using:

* SSHFS (Aalto gateways)
* CIFS (NAS / SMB)
* browse (GUI access via smb://)

It does not manage permissions — access is controlled externally (e.g. Aalto AD).

---

## Architecture

```text
User → rpi-share → sshfs/cifs → gateway → storage
```

Key principle:

> rpi-share does not decide access. Authentication and authorization are handled by the remote system.

---

## Configuration file

A JSON config file is required.

Search order:

```text
1. Explicit --config FILE, if selected
2. ./rpi-share.json
3. ~/.config/rpi-share.json
4. /etc/rpi-share/rpi-share.json
5. <script_dir>/rpi-share.json
```

Override:

```bash
rpi-share --config /path/to/file.json
```

---

## JSON structure

Top-level:

```json
{
  "version": 1,
  "defaults": { ... },
  "gateways": { ... },
  "shares": { ... }
}
```

---

## Defaults

```json
"defaults": {
  "gateway": "example-gateway",
  "share": "example-share"
}
```

Used in guided mode.

---

## Gateways

```json
"example-gateway": {
  "host": "gateway.example.invalid",
  "description": "Example staff gateway",
  "allowed_groups": ["staff"]
}
```

```json
"alternate-gateway": {
  "host": "alternate.example.invalid",
  "description": "Example student and staff gateway",
  "allowed_groups": ["students", "staff"]
}
```

Fields:

| Field          | Description            |
| -------------- | ---------------------- |
| host           | SSH hostname           |
| description    | user-facing text       |
| allowed_groups | informational only     |
| default_user   | optional (home config) |

---

## Shares

### Common fields

| Field          | Description             |
| -------------- | ----------------------- |
| description    | user-facing description |
| mount_type     | sshfs / cifs / browse   |
| allowed_groups | informational only      |

---

### SSHFS (single path)

```json
"example-share": {
  "description": "Shared data",
  "mount_type": "sshfs",
  "remote_path": "/srv/example/data"
}
```

---

### SSHFS (gateway-specific paths)

```json
"example-share": {
  "description": "Shared data",
  "mount_type": "sshfs",
  "paths": {
    "example-gateway": "/srv/example/data",
    "alternate-gateway": "/exports/example/data"
  }
}
```

---

### CIFS share (home NAS)

```json
"files": {
  "mount_type": "cifs",
  "remote_path": "/Files",
  "cifs_options": "iocharset=utf8,vers=3.0,noserverino"
}
```

---

### Browse share

```json
"root": {
  "mount_type": "browse",
  "browse_url": "smb://storage.example.invalid/"
}
```

---

All server names and paths above are placeholders. The `remote_path`/`paths`
values are server paths; they are distinct from the local mountpoints below.

## Path resolution

```text
if share has "paths":
    use paths[gateway]
else:
    use remote_path
```

---

## explicit_only shares

Example:

```json
"maintenance-share": {
  "mount_type": "sshfs",
  "explicit_only": true,
  "paths": {
    "example-gateway": "/srv/example/maintenance"
  }
}
```

Behavior:

```text
- hidden in guided mode
- visible with --list --all
- selectable only explicitly or with --admin
```

---

## Guided mode

Triggered when:

```bash
rpi-share
```

Flow:

1. User role (staff / student)
2. Gateway selection
3. Share selection (filtered by gateway)
4. Username
5. Mount

Important:

```text
Share list is built AFTER gateway selection
```

---

## Username handling

Priority:

```text
1. Explicit CLI (-u)
2. Interactive input, with gateway default_user as an optional prompt default
```

Example:

```bash
rpi-share -g example-gateway -s example-share -u username
```

---

### Admin accounts

Examples use placeholder names:

```text
username_admin
```

Admin accounts are intended for maintenance tasks only.

---

## Mountpoints

Structure:

```text
/media/rpi-share/<gateway>/<share>
```

Ownership:

```text
base dir        → root
gateway dir     → root
sshfs mount     → user
```

---

## Unmount behavior

Safe unmount sequence:

```text
1. try normal unmount
2. if busy → user closes applications
3. retry
```

Not used:

```text
umount -l
umount -f
```

---

## Error handling

Default:

```text
User-friendly message
```

Debug mode:

```bash
rpi-share --debug
```

Shows raw sshfs/cifs errors.

---

## Security model

```text
- no credentials stored
- no privilege escalation
- relies on SSH / AD
- navigation visibility is not an access control mechanism
```

---

## Home configuration

Home setups may use:

* CIFS shares
* browse mode
* default_user

Example:

```json
"example-storage": {
  "host": "storage.example.invalid",
  "default_user": "username"
}
```

---

## Limitations

```text
- sshfs copy via GUI is not resumable
- large transfers may benefit from rsync
- network interruption cancels transfers
```

---

## Design principles

```text
- minimal user friction
- safe defaults
- no hidden behavior
- transparency over automation
```


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
