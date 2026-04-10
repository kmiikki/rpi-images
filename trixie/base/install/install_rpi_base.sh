#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="${SCRIPT_DIR}/packages"
DO_APT_UPGRADE="${DO_APT_UPGRADE:-1}"

need_root() {
    [[ "${EUID}" -eq 0 ]] || { echo "Run as root: sudo $0" >&2; exit 1; }
}

check_rpi_os() {
    source /etc/os-release
    case "${ID:-}:${VERSION_CODENAME:-}" in
        raspbian:*|debian:trixie) : ;;
        *) echo "WARNING: Expected Raspberry Pi OS / Debian Trixie, got ${PRETTY_NAME:-unknown}" ;;
    esac
}

install_apt_list() {
    local listfile="$1"
    mapfile -t pkgs < <(grep -v '^[[:space:]]*#' "$listfile" | grep -v '^[[:space:]]*$')
    [[ ${#pkgs[@]} -gt 0 ]] && apt-get install -y "${pkgs[@]}"
}

setup_lab_dirs_and_path() {
    mkdir -p /opt/lab/bin /opt/lab/share /opt/lab/apps /opt/lab/install /opt/lab/logs
    chmod 755 /opt/lab /opt/lab/bin /opt/lab/share /opt/lab/apps /opt/lab/install /opt/lab/logs

    cat >/etc/profile.d/lab-path.sh <<'EOF'
if [ -d /opt/lab/bin ]; then
  case ":$PATH:" in
    *":/opt/lab/bin:"*) ;;
    *) PATH="/opt/lab/bin:$PATH" ;;
  esac
fi
export PATH
EOF
    chmod 644 /etc/profile.d/lab-path.sh
}

main() {
    need_root
    check_rpi_os
    apt-get update
    if [[ "$DO_APT_UPGRADE" -eq 1 ]]; then
        apt-get full-upgrade -y
    fi
    install_apt_list "${PKG_DIR}/common-apt.txt"
    install_apt_list "${PKG_DIR}/rpi-apt.txt"
    setup_lab_dirs_and_path
    echo "RPi base install complete."
}

main "$@"