#!/usr/bin/env bash
set -euo pipefail

CONDA_BIN="/opt/conda/bin/conda"
ENV_PREFIX="/opt/rpi"
ENV_NAME="rpi"

if [[ ! -x "$CONDA_BIN" ]]; then
    echo "ERROR: conda not found: $CONDA_BIN" >&2
    exit 1
fi

PY_MINOR="$(/usr/bin/python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

echo "System Python minor version: $PY_MINOR"
echo "Target environment: $ENV_PREFIX"

echo
echo "Installing required Raspberry Pi system Python packages..."
sudo apt-get update
sudo apt-get install -y \
    python3-opencv \
    python3-picamera2 \
    python3-libcamera \
    python3-serial

if [[ -d "$ENV_PREFIX" ]]; then
    echo "ERROR: environment already exists: $ENV_PREFIX" >&2
    echo "Remove it manually if you really want to recreate it:" >&2
    echo "  sudo rm -rf $ENV_PREFIX" >&2
    exit 1
fi

sudo "$CONDA_BIN" create -y -p "$ENV_PREFIX" \
    "python=$PY_MINOR" \
    pip \
    spyder-kernels \
    numpy \
    pandas \
    matplotlib \
    scipy \
    pillow \
    imageio \
    tifffile \
    openpyxl \
    pyserial

SITE_PACKAGES="$ENV_PREFIX/lib/python$PY_MINOR/site-packages"
PTH_FILE="$SITE_PACKAGES/aalto-system-dist-packages.pth"

if [[ ! -d "$SITE_PACKAGES" ]]; then
    echo "ERROR: site-packages directory not found: $SITE_PACKAGES" >&2
    exit 1
fi

echo "/usr/lib/python3/dist-packages" | sudo tee "$PTH_FILE" >/dev/null

echo
echo "Created $ENV_NAME environment:"
echo "  $ENV_PREFIX"
echo
echo "Testing rpi environment..."

"$ENV_PREFIX/bin/python" - <<'EOF'
import sys

print("Executable:", sys.executable)
print("Python:", sys.version.split()[0])
print("System dist-packages visible:", "/usr/lib/python3/dist-packages" in sys.path)

import numpy
import pandas
import matplotlib
import scipy
import cv2
import serial
import spyder_kernels
from picamera2 import Picamera2

print("numpy:", numpy.__version__)
print("pandas:", pandas.__version__)
print("matplotlib:", matplotlib.__version__)
print("scipy:", scipy.__version__)
print("cv2:", cv2.__version__)
print("cv2 file:", cv2.__file__)
print("serial:", serial.VERSION)
print("serial file:", serial.__file__)
print("spyder-kernels:", spyder_kernels.__version__)
print("picamera2 OK:", Picamera2)
EOF

echo
echo "Done."
