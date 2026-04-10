#!/usr/bin/env bash
set -euo pipefail

REMOVE_APT=0
PURGE=0
for arg in "$@"; do
    case "$arg" in
        --remove-apt) REMOVE_APT=1 ;;
        --purge) PURGE=1 ;;
        *) echo "Unknown argument: $arg" >&2; exit 2 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$SCRIPT_DIR/packages"

sudo bash "$SCRIPT_DIR/uninstall_rpi_autoactivate.sh"
sudo bash "$SCRIPT_DIR/uninstall_lab314_env.sh"
sudo bash "$SCRIPT_DIR/uninstall_conda_base.sh"

if [[ "$REMOVE_APT" -eq 1 ]]; then
    mapfile -t pkgs < <(cat "$PKG_DIR/common-apt.txt" "$PKG_DIR/rpi-apt.txt" | grep -v '^[[:space:]]*#' | grep -v '^[[:space:]]*$')
    [[ ${#pkgs[@]} -gt 0 ]] && sudo apt-get remove -y "${pkgs[@]}" || true
fi

if [[ "$PURGE" -eq 1 ]]; then
    sudo rm -f /etc/profile.d/lab-path.sh
    sudo rm -rf /opt/lab
fi

echo "RPi AALTO uninstall complete. Open a new shell or run: exec bash -l"