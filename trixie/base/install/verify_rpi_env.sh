#!/usr/bin/env bash
set -euo pipefail

ENV_PREFIX="/opt/rpi"

if [[ ! -x "${ENV_PREFIX}/bin/python" ]]; then
    echo "ERROR: ${ENV_PREFIX}/bin/python not found or not executable" >&2
    exit 1
fi

echo "==> Verifying rpi environment: ${ENV_PREFIX}"

"${ENV_PREFIX}/bin/python" - <<'EOF'
import sys

print("Executable:", sys.executable)
print("Python:", sys.version.split()[0])
print("System dist-packages visible:", "/usr/lib/python3/dist-packages" in sys.path)

import spyder_kernels
import numpy
import pandas
import matplotlib
import scipy
import cv2
import serial
from picamera2 import Picamera2

print("spyder-kernels:", spyder_kernels.__version__)
print("numpy:", numpy.__version__)
print("pandas:", pandas.__version__)
print("matplotlib:", matplotlib.__version__)
print("scipy:", scipy.__version__)
print("cv2:", cv2.__version__)
print("cv2 file:", cv2.__file__)
print("serial:", serial.VERSION)
print("serial file:", serial.__file__)
print("picamera2 OK:", Picamera2)
EOF

echo
echo "==> Camera quick checks"
if command -v rpicam-hello >/dev/null 2>&1; then
    rpicam-hello --list-cameras || true
else
    echo "WARNING: rpicam-hello not found"
fi

echo
echo "==> envrun quick check"
if command -v envrun >/dev/null 2>&1; then
    tmp_script="$(mktemp --suffix=.py)"
    cat >"$tmp_script" <<'EOF'
import sys
print("envrun executable:", sys.executable)
EOF
    envrun rpi "$tmp_script"
    rm -f "$tmp_script"
else
    echo "WARNING: envrun not found in PATH"
fi

echo
echo "rpi environment verification complete."
