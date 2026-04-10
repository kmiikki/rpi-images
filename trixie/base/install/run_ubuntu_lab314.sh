#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/install_ubuntu_base.sh"
bash "$SCRIPT_DIR/setup_lab314_ubuntu.sh"
bash "$SCRIPT_DIR/verify_lab314_ubuntu.sh"