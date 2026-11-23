#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=
if [[ ${1:-} == --root && $# == 2 && $2 == /* ]]; then
    root=${2%/}
elif (($#)); then
    echo "Usage: $0 [--root STAGING_ROOT]" >&2; exit 2
fi
# --root prepares a filesystem tree. It never selects or modifies a user home.
if [[ -z $root && $EUID != 0 ]]; then
    exec sudo bash "$0" "$@"
fi
bashrc="$root/etc/bash.bashrc"
[[ -f $bashrc && ! -L $bashrc ]] || { echo "Missing regular $bashrc" >&2; exit 1; }
install -d -m 755 "$root/etc/profile.d"
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
sed '/# >>> LAB314 BEGIN >>>/,/# <<< LAB314 END <<</d' "$bashrc" > "$stage/bashrc"
cat "$here/lab314-bashrc-block.sh" >> "$stage/bashrc"
bash -n "$stage/bashrc"
# Preserve an exact pre-change backup, including original owner and attributes.
if ! cmp -s "$stage/bashrc" "$bashrc"; then
    backup=$(mktemp "$bashrc.lab314-before.XXXXXXXX")
    cp --preserve=all "$bashrc" "$backup"
    cat "$stage/bashrc" > "$bashrc"
fi
if ! cmp -s "$here/lab314-bash.sh" "$root/etc/profile.d/lab314-bash.sh"; then
    if [[ -f $root/etc/profile.d/lab314-bash.sh ]]; then
        backup=$(mktemp "$root/etc/profile.d/lab314-bash.sh.lab314-before.XXXXXXXX")
        cp --preserve=all "$root/etc/profile.d/lab314-bash.sh" "$backup"
    fi
    install -m 644 "$here/lab314-bash.sh" "$root/etc/profile.d/lab314-bash.sh"
fi
# Remove only the known legacy PATH override. Other administrator settings
# require review and are never replaced by this step.
legacy="$root/etc/profile.d/conda-path.sh"
if [[ -f $legacy && $(cat "$legacy") == 'export PATH=/opt/conda/bin:$PATH' ]]; then
    backup=$(mktemp "$legacy.lab314-before.XXXXXXXX")
    cp --preserve=all "$legacy" "$backup"
    printf '%s\n' '# Conda is available through /usr/local/bin.' > "$legacy"
fi
