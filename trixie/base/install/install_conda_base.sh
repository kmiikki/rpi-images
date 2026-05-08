#!/usr/bin/env bash
set -euo pipefail

ARCH="$(uname -m)"

case "$ARCH" in
    aarch64|arm64)
        MINIFORGE_ARCH="aarch64"
        ;;
    x86_64|amd64)
        MINIFORGE_ARCH="x86_64"
        ;;
    *)
        echo "ERROR: unsupported architecture: $ARCH" >&2
        exit 1
        ;;
esac

MINIFORGE_URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-${MINIFORGE_ARCH}.sh"
INSTALLER="/tmp/Miniforge3-Linux-${MINIFORGE_ARCH}.sh"
CONDA_ROOT="/opt/conda"

wget -O "$INSTALLER" "$MINIFORGE_URL"
chmod +x "$INSTALLER"
sudo bash "$INSTALLER" -b -p "$CONDA_ROOT"

sudo ln -sf "$CONDA_ROOT/bin/conda" /usr/local/bin/conda
sudo ln -sf "$CONDA_ROOT/bin/mamba" /usr/local/bin/mamba

echo 'export PATH=/opt/conda/bin:$PATH' | sudo tee /etc/profile.d/conda-path.sh >/dev/null