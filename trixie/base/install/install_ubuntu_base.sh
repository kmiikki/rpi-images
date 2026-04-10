#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="${SCRIPT_DIR}/packages"
DO_APT_UPGRADE="${DO_APT_UPGRADE:-1}"

need_root() {
    [[ "${EUID}" -eq 0 ]] || { echo "Run as root: sudo $0" >&2; exit 1; }
}

check_ubuntu() {
    source /etc/os-release
    [[ "${ID:-}" == "ubuntu" ]] || { echo "Expected Ubuntu, got ${PRETTY_NAME:-unknown}" >&2; exit 1; }
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
    check_ubuntu
    apt-get update
    if [[ "$DO_APT_UPGRADE" -eq 1 ]]; then
        apt-get full-upgrade -y
    fi
    install_apt_list "${PKG_DIR}/common-apt.txt"
    install_apt_list "${PKG_DIR}/ubuntu-apt.txt"
    setup_lab_dirs_and_path
    echo "Ubuntu base install complete."
}

main "$@"