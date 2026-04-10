# rpi-images

Collection of reproducible Raspberry Pi OS installation profiles.

The goal of this repository is to keep one clean and repeatable base installation for each Raspberry Pi OS release.

Each OS release has its own directory, for example:

```text id="a2n7mf"
trixie/
bookworm/
future-release/
```

Each release may later contain multiple installation profiles, such as:

```text id="y6r8t3"
base/
logger/
spectrometer/
camera/
```

Currently available:

```text id="j5k40t"
trixie/base
```

This profile provides:

* Raspberry Pi OS Trixie base installation
* common laboratory/scientific environment
* Python 3.14 environment called `lab314`
* Spyder outside the environment
* scientific packages inside `lab314`
* Raspberry Pi specific packages such as Picamera2

Repository structure:

```text id="0tt3x5"
rpi-images/
└── trixie/
    └── base/
        ├── install/
        ├── docs/
        └── README.md
```

Start with:

```text id="rk6m4o"
trixie/base/README.md
```

for installation instructions.

