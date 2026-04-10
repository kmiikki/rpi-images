#!/usr/bin/env bash
set -euo pipefail

PRIMARY_USER="${PRIMARY_USER:-kim}"
NTP_PRIMARY="ntp.aalto.fi"
NTP_SECONDARY="time.mikes.fi"
NTP_FALLBACK="time.cloudflare.com pool.ntp.org"
ENABLE_SSH_SERVER="${ENABLE_SSH_SERVER:-1}"

need_root() {
    [[ "${EUID}" -eq 0 ]] || { echo "Run as root: sudo $0" >&2; exit 1; }
}

configure_timesyncd() {
    cat >/etc/systemd/timesyncd.conf <<EOF
[Time]
NTP=${NTP_PRIMARY} ${NTP_SECONDARY}
FallbackNTP=${NTP_FALLBACK}
EOF
    systemctl restart systemd-timesyncd || true
    timedatectl set-ntp true || true
}

wait_for_time_sync() {
    echo "==> Waiting for time sync (max 60s)"
    for _ in $(seq 1 60); do
        if timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -qx "yes"; then
            echo "Time synchronization: OK"
            timedatectl | sed -n '1,8p'
            return 0
        fi
        sleep 1
    done
    echo "WARNING: Time does not appear synchronized yet."
    timedatectl || true
    return 1
}

enable_ssh_server() {
    [[ "${ENABLE_SSH_SERVER}" -eq 1 ]] || return 0
    apt-get update
    apt-get install -y openssh-server
    systemctl enable --now ssh
}

ensure_primary_sudo() {
    if id -u "$PRIMARY_USER" >/dev/null 2>&1; then
        usermod -aG sudo "$PRIMARY_USER"
    else
        echo "WARNING: primary user '$PRIMARY_USER' not found."
    fi
}

main() {
    need_root
    configure_timesyncd
    wait_for_time_sync || true
    enable_ssh_server
    ensure_primary_sudo
    echo
    echo "HOME PRE complete."
}

main "$@"