#!/usr/bin/env bash
set -euo pipefail

MINIFORGE_URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh"
INSTALLER="/tmp/Miniforge3-Linux-aarch64.sh"
CONDA_ROOT="/opt/conda"

wget -O "$INSTALLER" "$MINIFORGE_URL"
chmod +x "$INSTALLER"
sudo bash "$INSTALLER" -b -p "$CONDA_ROOT"

sudo ln -sf "$CONDA_ROOT/bin/conda" /usr/local/bin/conda
sudo ln -sf "$CONDA_ROOT/bin/mamba" /usr/local/bin/mamba

echo 'export PATH=/opt/conda/bin:$PATH' | sudo tee /etc/profile.d/conda-path.sh >/dev/null