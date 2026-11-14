#!/usr/bin/env bash
set -euo pipefail
root=
if [[ ${1:-} == --root && $# == 2 && $2 == /* ]]; then root=${2%/}
elif (($#)); then echo "Usage: $0 [--root STAGING_ROOT]" >&2; exit 2; fi
if [[ -z $root && $EUID != 0 ]]; then echo "Run as root: sudo $0" >&2; exit 1; fi
if [[ -f $root/etc/bash.bashrc ]]; then
    sed -i '/# >>> LAB314 BEGIN >>>/,/# <<< LAB314 END <<</d' "$root/etc/bash.bashrc"
fi
rm -f -- "$root/etc/profile.d/lab314-bash.sh"
echo 'RPi autoactivation removed for new shells. Retained backups can restore the previous settings.'
