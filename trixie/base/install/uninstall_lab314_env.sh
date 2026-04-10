#!/usr/bin/env bash
set -euo pipefail

need_root() {
    [[ "${EUID}" -eq 0 ]] || { echo "Run as root: sudo $0" >&2; exit 1; }
}

need_root

if [[ -d /opt/lab314 ]]; then
    echo "Removing /opt/lab314"
    rm -rf /opt/lab314
else
    echo "/opt/lab314 not present"
fi