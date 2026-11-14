#!/usr/bin/env bash
# Optional application step, independent of APT and Conda provisioning.
set -euo pipefail
umask 022
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
profile="$here/../config/cam-imgcheck.json"
target=/opt/sci
source_dir=
approval=
mode=install
usage() {
    echo "Usage: $0 [--source SCIENTIFIC_IMAGING] [--target ABSOLUTE_PREFIX] [--profile JSON]"
    echo '       [--plan | --verify | --remove] [--approve APPLICATION]'
}
while (($#)); do
    case "$1" in
        --source) source_dir=$2; shift 2 ;;
        --target) target=$2; shift 2 ;;
        --profile) profile=$2; shift 2 ;;
        --approve) approval=$2; shift 2 ;;
        --plan|--verify|--remove)
            [[ $mode == install ]] || { usage >&2; exit 2; }
            mode=${1#--}; shift ;;
        --help) usage; exit 0 ;;
        --version) echo 'rpi-images sci installer 0.1.0'; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done
fail() { echo "ERROR: $*" >&2; exit 1; }
export PYTHONDONTWRITEBYTECODE=1
payload() { /usr/bin/python3 -IB "$here/sci_payload.py" "$1" "$profile" "${source_dir:-/}" "${@:2}"; }
fields=$(payload fields)
mapfile -t spec <<< "$fields"
name=${spec[0]}
entry=${spec[3]}
[[ -z $approval || $approval == "$name" ]] || fail 'approval does not match application'
[[ $target == /* && $target != / && $(realpath -m -- "$target") == "$target" ]] || fail 'target must be a canonical absolute path'
parent=$(dirname -- "$target")
[[ -d $parent ]] || fail "missing parent $parent"
if [[ $mode == install || $mode == plan ]]; then
    [[ -d $source_dir ]] || fail '--source requires the trusted source checkout'
    source_dir=$(realpath -e -- "$source_dir")
    [[ $target != "$source_dir" && $target != "$source_dir/"* && $source_dir != "$target/"* ]] || fail 'overlapping source and target'
fi
# Coordinate bootstrap, publish and rollback, even before the prefix exists.
exec {lock}<"$parent"
flock -x "$lock"
for path in "$target" "$target/bin" "$target/bin-rpi" "$target/lib"; do
    [[ ! -L $path && ( ! -e $path || -d $path ) ]] || fail "conflicting path: $path"
done
payload target "$target"
release="$name-${spec[1]}"
runtime="$target/lib/$release"
link="$target/${spec[2]}/$name"
relative="../lib/$release/$entry"
present=0
if [[ -L $link || -e $link || -e $runtime || -L $runtime ]]; then
    [[ -L $link && $(readlink -- "$link") == "$relative" && -d $runtime && ! -L $runtime ]] || fail "conflicting or incomplete installation: $link / $runtime"
    present=1
fi
verify() { payload verify "$runtime" "$link"; }
if [[ $mode == verify ]]; then
    ((present)) || fail "missing $link"
    verify
    exit 0
fi
if [[ $mode != remove ]]; then
    payload preflight
fi
if ((present)); then
    if [[ $mode == remove ]]; then
        payload tree "$runtime"
    else
        verify; echo "KEEP $link"; exit 0
    fi
elif [[ $mode == remove ]]; then
    echo "Already absent: $name"; exit 0
fi

echo "$mode $name ${spec[1]} | ${spec[4]} | #!${spec[5]}"
echo "  Profile: $profile"
echo "  Source: $source_dir"
echo "  Runtime: $runtime"
echo "  Command: $link -> $relative"
echo "  Directories: $target/{bin,bin-rpi,lib}"
[[ $mode != plan ]] || exit 0
if [[ -z $approval ]]; then
    [[ -t 0 ]] || fail "supply --approve $name for unattended installation"
    read -r -p 'Apply this plan? [y/N] ' answer || exit 1
    [[ ${answer,,} == y ]] || exit 1
fi
if [[ $mode == remove ]]; then
    # Remove only this exact release; verify rejected foreign files above.
    rm -- "$link"
    rm -r -- "$runtime"
    exit 0
fi

made=()
stage=
published=0
linked=0
cleanup() {
    local rc=$?
    trap - EXIT INT TERM HUP
    if ((rc != 0)); then
        if ((linked)) && [[ -L $link && $(stat -c %d:%i "$link") == "$(stat -c %d:%i "$stage/command")" ]]; then rm -- "$link"; fi
        if ((published)) && [[ ! -e $stage/$release && -d $runtime ]]; then rm -r -- "$runtime"; fi
    fi
    if [[ -n $stage ]]; then rm -rf -- "$stage"; fi
    if ((rc != 0)); then
        for ((i=${#made[@]}-1; i>=0; i--)); do rmdir -- "${made[i]}" || :; done
    fi
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
for path in "$target" "$target/bin" "$target/bin-rpi" "$target/lib"; do
    if [[ ! -d $path ]]; then mkdir -m 755 -- "$path"; made+=("$path"); fi
done
stage=$(mktemp -d -- "$target/lib/.install-$name.XXXXXXXX")
payload stage "$stage/$release" "$stage/shebang.json"
tool=(/usr/bin/python3 -IB "$here/../tools/set-python-shebang.py" --manifest "$stage/shebang.json" --target "$stage/$release")
"${tool[@]}" --dry-run
"${tool[@]}" --apply --non-interactive --approved-profile "$name"
payload verify "$stage/$release"
published=1
mv -T -- "$stage/$release" "$runtime"
ln -s -- "$relative" "$stage/command"
linked=1
ln -PT -- "$stage/command" "$link"
verify
echo "Installed $link"
