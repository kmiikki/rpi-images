#!/usr/bin/env bash
set -euo pipefail

need_root() {
    [[ "${EUID}" -eq 0 ]] || { echo "Run as root: sudo $0" >&2; exit 1; }
}

need_root

if [[ -f /etc/bash.bashrc ]]; then
    sed -i '/# >>> LAB314 BEGIN >>>/,/# <<< LAB314 END <<</d' /etc/bash.bashrc
fi

echo "RPi autoactivation removed."