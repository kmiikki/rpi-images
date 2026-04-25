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

setup_passwordless_sudo_for_invoking_user() {
    local target_user="${SUDO_USER:-}"

    if [[ -z "$target_user" || "$target_user" == "root" ]]; then
        echo "WARNING: Cannot determine invoking user; skipping passwordless sudo setup."
        return 0
    fi

    if ! id "$target_user" >/dev/null 2>&1; then
        echo "WARNING: User does not exist: $target_user; skipping passwordless sudo setup."
        return 0
    fi

    local sudoers_file="/etc/sudoers.d/010_${target_user}-nopasswd"
    local desired_content="${target_user} ALL=(ALL) NOPASSWD: ALL"
    local tmp_file

    if [[ -f "$sudoers_file" ]] && [[ "$(cat "$sudoers_file")" == "$desired_content" ]]; then
        echo "Passwordless sudo already configured for user: $target_user"
        return 0
    fi

    tmp_file="$(mktemp)"
    echo "$desired_content" > "$tmp_file"

    if ! visudo -cf "$tmp_file" >/dev/null; then
        echo "ERROR: Invalid sudoers content, aborting." >&2
        rm -f "$tmp_file"
        return 1
    fi

    install -m 0440 "$tmp_file" "$sudoers_file"
    rm -f "$tmp_file"

    visudo -c >/dev/null
    echo "Passwordless sudo enabled for user: $target_user"
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
