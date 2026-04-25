# rpi-share

`rpi-share` is a portable CLI tool for accessing network shares safely on Raspberry Pi and Linux systems.

Designed for lab environments where:

- USB storage is restricted
- multiple users share machines
- stability and predictability are critical

---

## Key Features

- Session-based network mounts
- Supports:
  - `sshfs` (Aalto)
  - `cifs` (NAS)
  - `browse` (GUI open)
- No passwords stored in configuration
- Safe unmount (no forced or lazy unmount)
- Works with GUI (Nemo) and CLI

---

## Configuration

Configuration is provided via JSON:

```

rpi-share.json

```

Resolution order:

1. Current working directory
2. `~/.config/rpi-share.json`
3. Script directory

Override:

```

rpi-share --config file.json

```

---

## Usage

### Interactive

```

rpi-share

```

### Non-interactive

```

rpi-share -g nasse -s code
rpi-share -g viila -s teamwork-t100

```

### Cleanup

```

rpi-share --cleanup
rpi-share --cleanup --remove-dirs

```

---

## Mount Lifecycle

```

start script → mount
exit script  → unmount

```

- Mount exists only during session
- Script attempts clean unmount on exit

---

## Safe Unmount Behaviour

The tool intentionally avoids:

```

umount -l
umount -f

```

Reason:

> Lazy or forced unmount may freeze the system when GUI applications (e.g. Nemo) are using CIFS mounts.

Instead:

1. Normal unmount
2. If busy → user closes applications
3. Retry loop until safe
4. User may exit (`q`) and retry later

---

# 🔍 Debugging & Diagnostics

## Check active mounts

```

mount | grep rpi-share

```

or:

```

mountpoint /media/rpi-share/<...>

```

---

## Check processes using the mount

```

lsof +D /media/rpi-share

```

or:

```

fuser -vm /media/rpi-share

```

---

## Check network connectivity

### NAS

```

ping nasse

```

### Aalto

```

ssh viila

```

---

## Check SSHFS

```

sshfs user@host:/path /mnt/test

```

---

## Check CIFS manually

```

sudo mount -t cifs //host/share /mnt/test -o user=USER

```

---

## Check dependencies

```

which sshfs
which mount.cifs
which jq
which timeout

```

---

# ⚠️ Common Failure Cases

## 1. Mount is busy

Error:

```

target is busy

```

Cause:

- Nemo open
- terminal inside mount
- file in use

Fix:

```

cd ~
close Nemo
close editors
rpi-share --cleanup

```

---

## 2. System freeze risk (IMPORTANT)

Cause:

```

umount -l or forced unmount

* CIFS
* GUI

```

Effect:

- UI freeze
- kernel I/O hang

Prevention:

```

NEVER use:
umount -l
umount -f

```

---

## 3. Wrong hostname

Error:

```

host not found

```

Fix:

```

/etc/hosts

```

Example:

```

10.0.0.5 nasse

```

---

## 4. Permission denied (SSH)

Cause:

- wrong username
- missing SSH key

Fix:

```

ssh user@host

```

---

## 5. CIFS authentication failure

Cause:

- wrong password
- domain mismatch

Fix:

- re-enter password
- verify NAS user

---

## 6. Mount disappears in GUI

Cause:

- session ended
- mount cleaned up

Expected behaviour:

```

session-based model

```

---

## 7. Cleanup does not remove directory

Cause:

- mount still active
- hidden process

Fix:

```

lsof +D /media/rpi-share
kill process if needed

```

---

# 🧪 Advanced Debug

## Trace mount activity

```

strace -f rpi-share ...

```

---

## Monitor kernel messages

```

dmesg -w

```

Look for:

- CIFS errors
- I/O timeouts

---

## Check mount table

```

cat /proc/mounts | grep rpi-share

```

---

# 🔐 Security Model

- No passwords stored in JSON
- Credentials requested at runtime
- Temporary credentials removed on exit

---

# 🧠 Design Principles

- No hidden automation
- No stored credentials
- No unsafe unmount operations
- User remains in control
- Stability over convenience

---

# 🧯 Recovery Strategy

If things go wrong:

1. Close all applications using the mount
2. Run:

```

rpi-share --cleanup --remove-dirs

```

3. If still stuck:

```

reboot

```

---

# 🧭 Notes

- Do not use `.local` (no mDNS)
- Use `/etc/hosts` or DNS
- Works on Raspberry Pi OS and Ubuntu

