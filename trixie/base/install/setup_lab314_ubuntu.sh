#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="lab314"
PYTHON_VERSION="3.14"

command -v micromamba >/dev/null 2>&1 || {
    echo "micromamba not found in PATH" >&2
    exit 1
}

micromamba create -y -n "$ENV_NAME" -c conda-forge \
    "python=${PYTHON_VERSION}" \
    spyder-kernels \
    ipykernel \
    numpy \
    pandas \
    matplotlib \
    scipy \
    scikit-image \
    opencv \
    pillow \
    imageio \
    tifffile \
    openpyxl \
    seaborn \
    pyarrow \
    h5py