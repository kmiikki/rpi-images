#!/usr/bin/env bash
set -euo pipefail

if [[ -e /usr/local/bin/envrun ]]; then
    sudo rm -f /usr/local/bin/envrun
    echo "Removed /usr/local/bin/envrun"
else
    echo "/usr/local/bin/envrun not present"
fi
