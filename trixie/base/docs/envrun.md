# `envrun`

`envrun` runs a Python script with a selected system-wide environment.

It is intentionally small and explicit. It avoids relying on the currently
active shell prompt or conda activation state.

---

## Usage

Preferred form:

```bash
envrun ENV SCRIPT [ARGS...]
```

Alternative form:

```bash
envrun SCRIPT ENV [ARGS...]
```

---

## Known environments

```text
lab314 -> /opt/lab314/bin/python
rpi    -> /opt/rpi/bin/python
```

---

## Examples

```bash
envrun lab314 udplot.py
envrun lab314 dps-profile-cycle.py -p /dev/ttyLOG -a 1,2,3,4
envrun rpi camera_test.py
envrun rpi gpio_test.py
```

Alternative order:

```bash
envrun udplot.py lab314
envrun camera_test.py rpi
```

---

## Rules of thumb

Use `lab314` for:

- analysis
- plotting
- udplot
- generic Python scripts
- pyserial-based scripts

Use `rpi` for:

- Picamera2
- libcamera
- APT OpenCV
- GPIO
- I2C/smbus2
- gpiod

---

## Why not rely on shell activation?

The visible prompt may not be enough to guarantee reproducible script
execution. `envrun` chooses the interpreter explicitly:

```text
/opt/lab314/bin/python
/opt/rpi/bin/python
```

This is safer for scripts, launchers, shortcuts, and documentation.
