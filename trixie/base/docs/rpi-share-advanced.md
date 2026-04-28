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
1. ./rpi-share.json
2. ~/.config/rpi-share.json
3. <script_dir>/rpi-share.json
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
  "gateway": "viila",
  "share": "teamwork-chem"
}
```

Used in guided mode.

---

## Gateways

```json
"viila": {
  "host": "viila.org.aalto.fi",
  "description": "Aalto staff gateway",
  "allowed_groups": ["staff"]
}
```

```json
"kosh": {
  "host": "kosh.org.aalto.fi",
  "description": "Aalto student and staff gateway",
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
"work-t100": {
  "description": "Work CHEM",
  "mount_type": "sshfs",
  "remote_path": "/m/work/t100"
}
```

---

### SSHFS (gateway-specific paths)

```json
"teamwork-chem": {
  "description": "Teamwork CHEM",
  "mount_type": "sshfs",
  "paths": {
    "viila": "/m/teamwork/t1/T100",
    "kosh": "/m/teamwork/T100"
  }
}
```

---

### CIFS share (home NAS)

```json
"code": {
  "mount_type": "cifs",
  "remote_path": "/Code",
  "cifs_options": "iocharset=utf8,vers=3.0,noserverino"
}
```

---

### Browse share

```json
"root": {
  "mount_type": "browse",
  "browse_url": "smb://nasse/"
}
```

---

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
"teamwork-chem-scratch": {
  "mount_type": "sshfs",
  "explicit_only": true,
  "paths": {
    "viila": "/m/teamwork/chem_scratch"
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
1. CLI (-u)
2. interactive input
3. $USER
```

Example:

```bash
rpi-share -g viila -s work-t100 -u username
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
- avoids exposing restricted paths
```

---

## Home configuration

Home setups may use:

* CIFS shares
* browse mode
* default_user

Example:

```json
"nasse": {
  "host": "nasse",
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
