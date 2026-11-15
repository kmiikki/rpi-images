#!/usr/bin/env bash
# Install software and generic examples only; never overwrite user/site catalogs.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
base=$(cd -- "$here/.." && pwd)
prefix=/usr/local
plan=0
while (($#)); do
    case $1 in
        --prefix) prefix=$2; shift 2 ;;
        --plan) plan=1; shift ;;
        --help) echo 'Usage: install_rpi_share.sh [--prefix ABSOLUTE_PREFIX] [--plan]'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
[[ $prefix == /* && $(realpath -m -- "$prefix") == "$prefix" && $prefix != / ]] || { echo 'Canonical absolute prefix required' >&2; exit 2; }
for path in "$prefix" "$prefix/bin" "$prefix/share" "$prefix/share/rpi-share" "$prefix/share/rpi-share/examples"; do
    [[ ! -L $path ]] || { echo "Symlinked install directory refused: $path" >&2; exit 1; }
done
for name in rpi-share rpi-share-builder.py rpi_share_catalog.py; do
    [[ -f $base/bin/$name && ! -L $base/bin/$name ]] || exit 1
    [[ ! -L $prefix/bin/$name ]] || { echo 'Refusing foreign symlink' >&2; exit 1; }
    echo "INSTALL $prefix/bin/$name"
done
((!plan)) || exit 0
install -d -m 755 "$prefix/bin" "$prefix/share/rpi-share/examples"
install -m 755 "$base/bin/rpi-share" "$base/bin/rpi-share-builder.py" "$prefix/bin/"
install -m 644 "$base/bin/rpi_share_catalog.py" "$prefix/bin/"
for path in "$base"/config/rpi-share.example.* "$base/config/rpi-share.schema.json"; do
    [[ -f $path ]] || continue
    destination="$prefix/share/rpi-share/examples/$(basename -- "$path")"
    [[ ! -L $destination ]] || { echo 'Symlinked example refused' >&2; exit 1; }
    install -m 644 "$path" "$destination"
done
echo 'Software installed. Choose an existing JSON, local CSV, explicit example, or configure later.'
