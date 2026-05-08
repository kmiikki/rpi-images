# Raspberry Pi `rpi` Environment

`/opt/rpi` is an optional Raspberry Pi hardware bridge environment.

It is used when Python scripts need Raspberry Pi OS APT Python modules such as:

- Picamera2
- libcamera
- APT OpenCV (`python3-opencv`)
- smbus2 / I2C
- RPi.GPIO
- gpiod

---

## Difference from `lab314`

`/opt/lab314` is a clean conda analysis environment.

It intentionally does **not** see:

```text
/usr/lib/python3/dist-packages
```

This keeps the Python 3.14 analysis environment isolated from Raspberry Pi OS
system Python packages.

`/opt/rpi` is different. It is created with the same Python minor version as:

```text
/usr/bin/python3
```

and includes:

```text
/usr/lib/python3/dist-packages
```

through a `.pth` file.

---

## When to use

Use `lab314` for analysis, plotting, and generic Python tools:

```bash
envrun lab314 script.py
```

Use `rpi` for Raspberry Pi hardware scripts:

```bash
envrun rpi script.py
```

Examples:

```bash
envrun lab314 udplot.py
envrun lab314 dps-profile-cycle.py -p /dev/ttyLOG -a 1,2,3,4
envrun rpi camera_test.py
envrun rpi gpio_test.py
envrun rpi i2c_test.py
```

---

## Installation

Create `/opt/rpi` only when Raspberry Pi hardware Python modules are needed:

```bash
cd trixie/base
./install/create_rpi_env.sh
./install/verify_rpi_env.sh
```

The environment is not autoactivated by default.

---

## Verification

Run:

```bash
./install/verify_rpi_env.sh
```

Expected signs of success:

```text
System dist-packages visible: True
cv2 file: /usr/lib/python3/dist-packages/...
picamera2 OK
envrun executable: /opt/rpi/bin/python
```

---

## OpenCV policy

`lab314` uses pip `opencv-python` and therefore needs the Qt font fix described
in:

```text
docs/opencv-qt-font-fix.md
```

`rpi` uses APT `python3-opencv` through `/usr/lib/python3/dist-packages`.
This is the preferred model for Picamera2/libcamera compatibility.

---

## Rule of thumb

```text
lab314 = clean analysis environment
rpi    = Raspberry Pi hardware bridge environment
```
