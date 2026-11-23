# Raspberry Pi scientific Python quick start

This guide installs the scientific Python environment on a Raspberry Pi 4 or 5.
Use GENERAL unless you need the predefined HOME or AALTO/CHEM environment.
The hardware Python environment and Scientific Imaging applications have separate installation settings.

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

## 3. Run the unified installer

From `trixie/base/install`, run setup as the intended desktop user.

```bash
sudo bash setup-rpi.sh
```

On first setup, choose your keyboard layout. Finnish is the default. **Show all
available keyboard layouts** opens a searchable list. Setup applies the layout
before other questions and keeps it for future runs. On a fresh system, setup
refreshes the APT lists and applies a reviewed full OS upgrade before installing
the scientific software. If hardware setup or the upgrade requires a reboot,
confirm it or reboot manually, then run the same setup command again.

When Finnish or Swedish is selected and LXTerminal is the default terminal,
setup configures zoom in with **Ctrl + +**, zoom out with **Ctrl + −**, and
reset with **Ctrl + 0** for the desktop user.

Choose **GENERAL** for an independent installation, **HOME** for home settings,
or **AALTO** for the Aalto University CHEM settings. Review and approve the plan.
The defaults install Scientific Python 3.14 with Spyder and the separate
Raspberry Pi Python 3.13 environment. The approval prompt offers `customize`
for changes to the defaults. [Advanced options](trixie/base/docs/unified-setup.md#advanced-installation-options)

## 4. Open a fresh terminal and verify

On Raspberry Pi 5 Model B, check `ls -l /dev/i2c-1 /dev/spidev0.*` after the
first-stage reboot, if required, and test typing in your chosen layout.
[Hardware verification](trixie/base/docs/unified-setup.md#hardware-acceptance)

Log out and back in if account/group or login-shell settings changed. Open a new
terminal for shell activation and PATH changes. A hostname change may require
reconnection or a reboot for all services; follow the installer's message.

From the same repository's `trixie/base/install` directory:

```bash
bash verify_rpi_lab314.sh
/opt/lab314/bin/python --version
/opt/lab314/bin/python -c 'import numpy; print(numpy.__version__)'
rpi-lab314-spyder
```

The desktop menu also provides **Spyder (Scientific Python)**. In its IPython
console, check that `import numpy, scipy, cv2` succeeds and that
`sys.executable` points into `/opt/lab314`. [Spyder setup](trixie/base/docs/spyder-lab314.md)

## 5. Optional hardware and camera support

The hardware Python environment is selected by default. If you skipped it when
customizing setup, enable it later using the same profile as the original
installation. This example uses GENERAL.

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

- [Status, repair, updates and reset](trixie/base/docs/unified-setup.md#installation-lifecycle)
- [Unified setup and recovery reference](trixie/base/docs/unified-setup.md)
- [Create or reuse installation profiles](trixie/base/docs/profile-builder.md)
- [Scientific Python maintenance](trixie/base/docs/lab314-maintenance.md)
- [rpi-share usage](trixie/base/docs/rpi-share.md) and [catalog editing](trixie/base/docs/rpi-share-catalog.md)
- [Scientific Imaging integration and ownership](trixie/base/docs/unified-setup.md#optional-scientific-imaging)
