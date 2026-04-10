# lab-install README

## Purpose

This package creates and removes a standard laboratory Python environment called `lab314`.

Goals:

* one common environment for researchers
* Python 3.14
* Spyder stays outside the environment
* only `spyder-kernels` is installed into the environment
* `/opt/lab/bin` is first in PATH
* Raspberry Pi automatically activates `lab314`
* Ubuntu does not autoactivate `lab314`

---

# Directory Structure

```text
install/
├── packages/
│   ├── common-apt.txt
│   ├── rpi-apt.txt
│   └── ubuntu-apt.txt
├── pre_home.sh
├── pre_aalto.sh
├── install_rpi_base.sh
├── install_ubuntu_base.sh
├── install_conda_base.sh
├── create_lab314_env.sh
├── enable_lab314_autoactivate_rpi.sh
├── verify_rpi_lab314.sh
├── setup_lab314_ubuntu.sh
├── verify_lab314_ubuntu.sh
├── run_rpi_home.sh
├── run_rpi_aalto.sh
├── run_ubuntu_lab314.sh
├── uninstall_lab314_env.sh
├── uninstall_conda_base.sh
├── uninstall_rpi_autoactivate.sh
├── run_uninstall_rpi_home.sh
├── run_uninstall_rpi_aalto.sh
└── run_uninstall_ubuntu_lab314.sh
```

---

# Raspberry Pi Home Installation

For a normal Raspberry Pi home installation:

```bash
cd install
sudo ./run_rpi_home.sh
```

This runs, in order:

1. `pre_home.sh`
2. `install_rpi_base.sh`
3. `install_conda_base.sh`
4. `create_lab314_env.sh`
5. `enable_lab314_autoactivate_rpi.sh`
6. `verify_rpi_lab314.sh`

After installation:

```bash
exec bash -l
```

The terminal prompt should become:

```text
(lab314)
```

---

# Raspberry Pi Aalto Installation

For an Aalto laboratory or work environment:

```bash
cd install
sudo ./run_rpi_aalto.sh
```

This is similar to the home version, but uses `pre_aalto.sh`.

---

# Ubuntu Installation

Ubuntu assumes that `micromamba` already exists.

Run:

```bash
cd install
./run_ubuntu_lab314.sh
```

This runs:

1. `install_ubuntu_base.sh`
2. `setup_lab314_ubuntu.sh`
3. `verify_lab314_ubuntu.sh`

Ubuntu does not autoactivate `lab314`.

Use it manually:

```bash
micromamba activate lab314
```

---

# Installed Python Packages in lab314

The environment contains at least:

```text
python 3.14
spyder-kernels 3.0.5
numpy
pandas
matplotlib
scipy
scikit-image
opencv-python
pillow
imageio
tifffile
openpyxl
seaborn
pyarrow
h5py
ipykernel
```

On Raspberry Pi, OpenCV Qt font support is fixed automatically by creating:

```text
/opt/lab314/lib/python3.14/site-packages/cv2/qt/fonts
```

and linking DejaVu fonts there.

---

# PATH

The following directory is added to the beginning of PATH:

```text
/opt/lab/bin
```

Place your own scripts there if you want them globally available.

Examples:

```text
/opt/lab/bin/filesampler.py
/opt/lab/bin/csvmerge.py
```

Larger projects should have their own directories under:

```text
/opt/lab/apps
```

Example:

```text
/opt/lab/apps/dpslogger
```

---

# Uninstall

## Raspberry Pi

Remove only the environment and conda:

```bash
sudo ./run_uninstall_rpi_home.sh
```

or

```bash
sudo ./run_uninstall_rpi_aalto.sh
```

Remove also apt packages:

```bash
sudo ./run_uninstall_rpi_home.sh --remove-apt
```

Remove everything including `/opt/lab`:

```bash
sudo ./run_uninstall_rpi_home.sh --remove-apt --purge
```

---

## Ubuntu

```bash
./run_uninstall_ubuntu_lab314.sh
```

Optional:

```bash
./run_uninstall_ubuntu_lab314.sh --remove-apt --purge
```

---

# Logs

The run scripts save logs under:

```text
/opt/lab/logs
```

Examples:

```text
/opt/lab/logs/run_rpi_home_20260406-183000.log
/opt/lab/logs/run_ubuntu_lab314_20260406-184500.log
```

---

# Recommended Test After Installation

```bash
python - <<'EOF'
import numpy, pandas, matplotlib, scipy, skimage, cv2, spyder_kernels
print("Everything OK")
EOF
```

Then test in Spyder by selecting:

```text
/opt/lab314/bin/python
```

as the interpreter.
