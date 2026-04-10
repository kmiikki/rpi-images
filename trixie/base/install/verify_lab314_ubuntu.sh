#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="lab314"

command -v micromamba >/dev/null 2>&1 || {
    echo "micromamba not found in PATH" >&2
    exit 1
}

micromamba run -n "$ENV_NAME" python - <<'EOF'
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