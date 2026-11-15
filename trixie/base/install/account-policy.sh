#!/usr/bin/env bash
# Reused by base provisioning and explicit primary-account recovery.
set -euo pipefail
configure_passwordless_sudo_user() {
    local target_user=$1 sudoers_file desired_content tmp_file
    [[ $target_user =~ ^[a-z_][a-z0-9_-]*$ && $target_user != root ]] || return 1
    id "$target_user" >/dev/null 2>&1 || return 1
    sudoers_file="/etc/sudoers.d/010_${target_user}-nopasswd"
    desired_content="${target_user} ALL=(ALL) NOPASSWD: ALL"
    [[ ! -L $sudoers_file ]] || { echo 'Symlinked sudo policy refused' >&2; return 1; }
    if [[ -f $sudoers_file && $(cat "$sudoers_file") == "$desired_content" ]]; then return 0; fi
    tmp_file=$(mktemp /etc/sudoers.d/.rpi-policy.XXXXXXXX)
    printf '%s\n' "$desired_content" > "$tmp_file"
    chmod 0440 "$tmp_file"
    if ! visudo -cf "$tmp_file" >/dev/null; then rm -f -- "$tmp_file"; return 1; fi
    mv -T -- "$tmp_file" "$sudoers_file"
    visudo -c >/dev/null
}
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    [[ $EUID == 0 && $# == 1 ]] || { echo 'Usage: sudo bash account-policy.sh PRIMARY_USER' >&2; exit 2; }
    configure_passwordless_sudo_user "$1"
fi
