# Raspberry Pi OS Trixie

This directory contains installation profiles for Raspberry Pi OS Trixie.

Currently available:

```text
base/
````

`base` is the common laboratory/scientific installation profile.

It provides:

* Python 3.14
* `lab314` environment
* Spyder integration
* OpenCV, NumPy, SciPy, pandas, scikit-image, matplotlib
* Raspberry Pi specific packages such as Picamera2
* common utilities and development tools

---

# Additional Tools

The base profile also defines a standard location for user-facing tools:

```text
/opt/lab/bin
```

This directory is automatically added to PATH.

## rpi-share

`rpi-share` provides safe access to network storage.

Features:

* Aalto (sshfs)
* NAS (cifs)
* session-based mount model
* no stored passwords
* avoids unsafe unmount operations

See:

```text
base/docs/rpi-share.md
```

---

# Directory structure

```text
trixie/
└── base/
    ├── bin/
    ├── config/
    ├── install/
    ├── docs/
    └── README.md
```

---

To continue, see:

```text
base/README.md
