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

Start with the [hands-on installation guide](QUICKSTART.md). For reusable local
preferences, see the [profile builder](trixie/base/docs/profile-builder.md).

## Installation profiles

`setup-rpi.sh` is the only supported entry point for new Raspberry Pi OS Trixie
installations. Choose a profile and approve the plan before setup applies your
keyboard layout and initializes the Raspberry Pi 5 Model B hardware interfaces.
If setup pauses for a reboot, repeat the same command afterward.

```bash
cd rpi-images/trixie/base/install
sudo bash setup-rpi.sh
```

The unified installer supports three profiles.

| Profile | Purpose |
|---|---|
| GENERAL | Generic Raspberry Pi installation without HOME- or AALTO-specific configuration |
| HOME | Home environment with its predefined settings |
| AALTO | Aalto University CHEM environment with its predefined settings |

These commands work from a cloned repository or an extracted ZIP package.
Run them from the parent of the repository directory; if the extracted folder
has a different name, substitute that name in the `cd` command. Keep the full
directory tree together; Git metadata is not required.

See the [base installation guide](trixie/base/README.md#installation-profiles)
and [unified setup guide](trixie/base/docs/unified-setup.md) for prerequisites,
optional components, maintenance and recovery.
