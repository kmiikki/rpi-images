#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="${SCRIPT_DIR}/packages"
DO_APT_UPGRADE="${DO_APT_UPGRADE:-0}"

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
    install -d -m 755 /opt/sci /opt/sci/bin /opt/sci/bin-rpi /opt/sci/lib
    # Existing /opt/lab and its profile snippet may still serve older tools.
    install -m 644 "$SCRIPT_DIR/sci-path.sh" /etc/profile.d/sci-path.sh
}

setup_passwordless_sudo_for_invoking_user() {
    local target_user="${SUDO_USER:-}"
    if [[ -z $target_user || $target_user == root ]]; then
        echo "WARNING: Cannot determine invoking user; skipping passwordless sudo setup."
        return 0
    fi
    # Preserve the approved invoking-user policy, shared with explicit recovery.
    source "$SCRIPT_DIR/account-policy.sh"
    configure_passwordless_sudo_user "$target_user"
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
    setup_passwordless_sudo_for_invoking_user
    echo "RPi base install complete."
}

main "$@"
