#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/pre_home.sh"
bash "$SCRIPT_DIR/install_rpi_base.sh"
bash "$SCRIPT_DIR/install_conda_base.sh"
bash "$SCRIPT_DIR/create_lab314_env.sh"
bash "$SCRIPT_DIR/enable_lab314_autoactivate_rpi.sh"
bash "$SCRIPT_DIR/verify_rpi_lab314.sh"