#!/usr/bin/env bash
set -euo pipefail

ENV_PREFIX="/opt/lab314"

"${ENV_PREFIX}/bin/python" - <<'EOF'
import sys
import spyder_kernels
import numpy
import pandas
import matplotlib
import scipy
import skimage
import cv2

print("Executable:", sys.executable)
print("Python:", sys.version.split()[0])
print("spyder-kernels:", spyder_kernels.__version__)
print("numpy:", numpy.__version__)
print("pandas:", pandas.__version__)
print("matplotlib:", matplotlib.__version__)
print("scipy:", scipy.__version__)
print("skimage:", skimage.__version__)
print("cv2:", cv2.__version__)
EOF

echo "==> Camera quick checks"
rpicam-hello --list-cameras || true
/usr/bin/python3 - <<'EOF'
try:
    from picamera2 import Picamera2
    print("picamera2 OK")
except Exception as e:
    print("picamera2 check failed:", e)
EOF