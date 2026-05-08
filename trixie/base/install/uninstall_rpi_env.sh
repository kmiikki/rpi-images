#!/usr/bin/env bash
set -euo pipefail

ENV_PREFIX="/opt/rpi"

if [[ ! -d "$ENV_PREFIX" ]]; then
    echo "Nothing to remove: $ENV_PREFIX does not exist."
    exit 0
fi

echo "This will remove:"
echo "  $ENV_PREFIX"
read -r -p "Continue? [y/N] " ans || true

case "$ans" in
    y|Y|yes|YES)
        sudo rm -rf "$ENV_PREFIX"
        echo "Removed $ENV_PREFIX"
        ;;
    *)
        echo "Cancelled."
        ;;
esac
