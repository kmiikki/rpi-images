#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

SRC="$BASE_DIR/bin/envrun"
DST="/usr/local/bin/envrun"

if [[ ! -f "$SRC" ]]; then
    echo "ERROR: envrun source not found: $SRC" >&2
    exit 1
fi

sudo install -m 755 "$SRC" "$DST"

echo "Installed envrun:"
echo "  $DST"
echo
"$DST" --help
