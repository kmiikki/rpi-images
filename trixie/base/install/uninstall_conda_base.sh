#!/usr/bin/env bash
set -euo pipefail

need_root() {
    [[ "${EUID}" -eq 0 ]] || { echo "Run as root: sudo $0" >&2; exit 1; }
}

need_root
rm -f /usr/local/bin/conda
rm -f /usr/local/bin/mamba
rm -f /etc/profile.d/conda-path.sh
rm -rf /opt/conda

echo "Conda base removed."