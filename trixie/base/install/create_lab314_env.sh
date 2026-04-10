#!/usr/bin/env bash
set -euo pipefail

ENV_PREFIX="/opt/lab314"

sudo /opt/conda/bin/conda create -y -p "$ENV_PREFIX" python=3.14

sudo "$ENV_PREFIX/bin/python" -m pip install --upgrade pip

sudo "$ENV_PREFIX/bin/python" -m pip install \
    spyder-kernels==3.0.5 \
    numpy pandas matplotlib scipy scikit-image \
    opencv-python pillow imageio tifffile \
    openpyxl seaborn pyarrow h5py ipykernel \
    PySimpleGUI

sudo tee "$ENV_PREFIX/lib/python3.14/site-packages/sitecustomize.py" >/dev/null <<'EOF'
import os
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
EOF

CV2_QT_DIR="$ENV_PREFIX/lib/python3.14/site-packages/cv2/qt"
sudo mkdir -p "$CV2_QT_DIR/fonts"

sudo ln -sf /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf \
    "$CV2_QT_DIR/fonts/DejaVuSans.ttf"
sudo ln -sf /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf \
    "$CV2_QT_DIR/fonts/DejaVuSans-Bold.ttf"