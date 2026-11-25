#!/usr/bin/env bash
# Shared profile policy. No account removal or password resets.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[[ $EUID == 0 && $# == 1 ]] || { echo 'Run through sudo with GENERAL, HOME or AALTO' >&2; exit 2; }
case $1 in
    GENERAL) default_ntp='pool.ntp.org time.cloudflare.com' ;;
    HOME) default_ntp='time.mikes.fi' ;;
    AALTO) default_ntp='ntp.aalto.fi' ;;
    *) echo 'Unknown profile' >&2; exit 2 ;;
esac
primary=${PRIMARY_USER:-${SUDO_USER:-}}
[[ $primary =~ ^[a-z_][a-z0-9_-]*$ && $primary != root ]] || { echo 'Set PRIMARY_USER to the intended local user' >&2; exit 2; }
ntp=${NTP_PRIMARY:-$default_ntp}
[[ $ntp =~ ^[A-Za-z0-9.\ :_-]+$ ]] || { echo 'Invalid NTP servers' >&2; exit 2; }
if [[ ${PRE_ACCOUNTS_MANAGED:-0} != 1 ]]; then
    /usr/bin/python3 -B "$here/rpi-accounts.py" --create "$primary" --admin --apply
    read -ra extras <<< "${EXTRA_SUDO_USERS:-}"
    for user in "${extras[@]}"; do
        /usr/bin/python3 -B "$here/rpi-accounts.py" --create "$user" --admin --apply
    done
fi
if [[ ${RPI_PROFILE_CONFIG_MANAGED:-0} != 1 ]]; then
    install -d -m 755 /etc/systemd/timesyncd.conf.d
    printf '[Time]\nNTP=%s\nFallbackNTP=time.cloudflare.com pool.ntp.org\n' "$ntp" > /etc/systemd/timesyncd.conf.d/60-rpi-scientific.conf
fi
# Keep the existing bounded clock-readiness wait before HTTPS/APT bootstrap.
wait_for_time_sync() {
    local attempt
    for ((attempt=0; attempt<60; attempt++)); do
        if [[ $(timedatectl show -p NTPSynchronized --value 2>/dev/null) == yes ]]; then
            echo 'Time synchronization: OK'
            return 0
        fi
        sleep 1
    done
    echo 'WARNING: Time synchronization is still pending after 60 seconds.' >&2
    return 1
}
if [[ ${RPI_PROFILE_RESTART_NTP:-1} == 1 ]]; then
    systemctl restart systemd-timesyncd
    timedatectl set-ntp true
    wait_for_time_sync || true
fi
case ${SSH_POLICY:-keep} in
    keep) echo 'KEEP existing SSH policy' ;;
    enable)
        if [[ ${RPI_PROFILE_CONFIG_MANAGED:-0} != 1 ]]; then
            apt-get -o Dpkg::Use-Pty=0 -o Dpkg::Progress-Fancy=0 update
            apt-get -o Dpkg::Use-Pty=0 -o Dpkg::Progress-Fancy=0 install -y openssh-server
        fi
        systemctl enable --now ssh
        ;;
    disable) systemctl disable --now ssh ;;
    *) echo 'SSH_POLICY must be keep, enable or disable' >&2; exit 2 ;;
esac
echo "$1 PRE complete. No OS upgrade requested by this stage."
