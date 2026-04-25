# rpi-share – Quick Guide

`rpi-share` is used to access network storage (Aalto / NAS) safely.

---

## Basic Usage

### Interactive (recommended)

```

rpi-share

```

---

### Direct use

```

rpi-share -g nasse -s code
rpi-share -g viila -s teamwork-t100

```

---

## What Happens

```

start script → mount
exit script  → unmount

```

The network share is available only while the script is running.

---

## How to Use

1. Run `rpi-share`
2. Open files using:
   - Nemo (file manager)
   - terminal
3. When done:
   - close file manager windows
   - leave the directory (`cd ~`)
4. Press Enter → disconnect

---

## Important Rules

✔ Always close file manager before exiting  
✔ Do not stay inside the mounted directory  
✔ Use `cd ~` before disconnect  

---

## If You See “target is busy”

This means something is still using the share.

Fix:

1. Close Nemo / file manager  
2. Close terminals inside the share  
3. Close editors or viewers  
4. Press Enter to retry  

---

## Cleanup

If something gets stuck:

```

rpi-share --cleanup --remove-dirs

```

---

## Last Resort

```

reboot

```

---

## What NOT to do

Do NOT run:

```

umount -l
umount -f

```

These can freeze the system.

---

## Examples

### Home NAS

```

rpi-share -g nasse -s code

```

### Aalto

```

rpi-share -g viila -s teamwork-t100

```

---

## Summary

✔ Run → use → close → exit  
✔ Always close file manager first  
✔ If busy → retry  
✔ If stuck → cleanup or reboot  
