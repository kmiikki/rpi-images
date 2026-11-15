# Raspberry Pi scientific Python quick start

This guide installs the scientific Python environment on a Raspberry Pi 4 or 5.
Use GENERAL unless you need the predefined HOME or AALTO/CHEM environment.
The optional camera environment and Scientific Imaging applications are separate.

## 1. Prepare and boot the Raspberry Pi

Download and open [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
Select your Raspberry Pi model, **Raspberry Pi OS Trixie Full (64-bit)** and the
microSD card. Writing the card erases its contents. In customization, set the
hostname, username, password, network and locale; enable SSH if needed. Imager
creates this first local account. Write the card, insert it and boot the Pi.

## 2. Open a terminal and get the installer

On the Pi desktop, open Terminal from the menu or press **Ctrl+Alt+T**.
An SSH session is also possible. Run:

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/kmiikki/rpi-images.git
cd rpi-images/trixie/base/install
```

An extracted repository ZIP works too: open its `trixie/base/install` directory
in the terminal, substituting the extracted folder name. Keep the full tree.

## 3. Install

```bash
sudo bash setup-rpi.sh
```

Select **GENERAL** for an independent installation without site-specific defaults.
HOME provides predefined home settings. AALTO provides the existing CHEM
deployment settings. GENERAL needs no access to either environment.

Keep the existing Imager account and hostname unless you intend to change them.
For the normal scientific workstation, include system dependencies, Conda,
lab314 and Spyder. The default Spyder uses the APT IDE; leave the separate IDE
prefix unset unless you maintain another IDE. Leave hardware, Wolfram,
rpi-share and Imaging unselected unless needed. HOME/AALTO include rpi-share;
select configuration later if no reviewed catalog is ready.

Review the displayed account, SSH, NTP and component plan before confirming.
The primary administrator retains the existing passwordless sudo policy, giving
full administrative access. New accounts require interactive password entry;
existing passwords are retained. SSH changes affect remote administration.
No full OS upgrade is implicit. Existing valid environments are kept.
If a stage fails, correct the reported cause and rerun the reviewed command.

## 4. Open a fresh terminal and verify

Log out and back in if account/group or login-shell settings changed. Open a new
terminal for shell activation and PATH changes. A hostname change may require
reconnection or a reboot for all services; follow the installer's message.
An unconditional reboot is not required.

From the same repository's `trixie/base/install` directory:

```bash
bash verify_rpi_lab314.sh
/opt/lab314/bin/python --version
/opt/lab314/bin/python -c 'import numpy; print(numpy.__version__)'
command -v spyder
spyder
```

The verification script checks the scientific environment. Check that Spyder
opens on the desktop; select `/opt/lab314/bin/python` as its Python interpreter
under **Tools → Preferences → Python interpreter**, then restart its console.
See [Spyder setup](trixie/base/docs/spyder-lab314.md) if the console cannot connect.
The IDE and the scientific environment remain separate.

## 5. Optional hardware and camera support

Select hardware during setup, or add it later using:

```bash
sudo bash setup-rpi.sh --profile GENERAL --hardware
bash verify_rpi_env.sh
/opt/rpi/bin/python -c 'from picamera2 import Picamera2; print(Picamera2)'
rpicam-hello --list-cameras
```

`/opt/rpi` is optional and separate from `/opt/lab314`. It bridges the OS-compatible
Picamera2/libcamera packages. Power down before connecting a camera ribbon.
A listed camera and successful imports do not replace a physical capture test.
Base setup does not automatically install the Scientific Imaging application suite.

## Next steps

- [Unified setup and recovery reference](trixie/base/docs/unified-setup.md)
- [Create or reuse installation profiles](trixie/base/docs/profile-builder.md)
- [Scientific Python maintenance](trixie/base/docs/lab314-maintenance.md)
- [rpi-share usage](trixie/base/docs/rpi-share.md) and [catalog editing](trixie/base/docs/rpi-share-catalog.md)
- [Scientific Imaging integration and ownership](trixie/base/docs/unified-setup.md#optional-scientific-imaging)
