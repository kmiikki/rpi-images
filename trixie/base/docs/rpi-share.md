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
rpi-share -g viila -s work-t100
```

With explicit username:

```bash
rpi-share -g viila -s work-t100 -u username
```

---

## Installation

Copy the script to a suitable location:

```bash
sudo cp rpi-share /opt/lab/bin/rpi-share
sudo chmod +x /opt/lab/bin/rpi-share
```

The script is fully portable and does not require installation.

---

## Configuration (required)

`rpi-share` requires a JSON configuration file.

Search order:

```text
1. ./rpi-share.json
2. ~/.config/rpi-share.json
3. <script_dir>/rpi-share.json
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

Example:

```text
/media/rpi-share/viila/work-t100
```

---

## Important notes

* Close file manager windows before disconnecting
* Do not use lazy or forced unmount
* Access rights are controlled by the remote system (e.g. Aalto AD)
* Some shares may not be visible if you do not have permission

---

## Aalto usage notes

* `viila` → staff gateway (recommended for staff)
* `kosh` → student + staff gateway
* Teamwork and Work shares may differ between gateways
* Use shared storage for research data (not personal home directories)

---

## Troubleshooting

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
