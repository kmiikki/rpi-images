#!/usr/bin/env bash
set -euo pipefail

PRIMARY_USER="${PRIMARY_USER:-chem}"
EXTRA_SUDO_USERS=("chem-it")
NTP_PRIMARY="ntp.aalto.fi"
NTP_SECONDARY="time.mikes.fi"
NTP_FALLBACK="time.cloudflare.com pool.ntp.org"

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

ensure_user_exists() {
    local user="$1"
    if id -u "$user" >/dev/null 2>&1; then
        echo "User exists: $user"
    else
        adduser --gecos "" "$user"
    fi
}

ensure_user_is_sudo() {
    local user="$1"
    if id -u "$user" >/dev/null 2>&1; then
        usermod -aG sudo "$user"
    else
        echo "WARNING: user not found: $user"
    fi
}

main() {
    need_root
    configure_timesyncd
    wait_for_time_sync || true
    ensure_user_exists "$PRIMARY_USER"
    ensure_user_is_sudo "$PRIMARY_USER"
    for u in "${EXTRA_SUDO_USERS[@]}"; do
        ensure_user_exists "$u"
        ensure_user_is_sudo "$u"
    done
    echo
    echo "AALTO PRE complete."
    echo "No SSH server was installed."
}

main "$@"