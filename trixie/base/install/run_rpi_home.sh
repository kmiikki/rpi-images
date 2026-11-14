#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Usage: run_rpi_home.sh [--with-cam-imgcheck SCIENTIFIC_IMAGING]
app_source=
if (($#)); then
    if [[ $# != 2 || $1 != --with-cam-imgcheck || ! -f $2/apps/capture/rpi/cam-imgcheck/cam-imgcheck.py ]]; then
        echo "Usage: $0 [--with-cam-imgcheck SCIENTIFIC_IMAGING]" >&2; exit 2
    fi
    app_source=$(realpath -e -- "$2")
    printf 'Include cam-imgcheck from %s using /opt/rpi in this base installation.\n' "$app_source"
fi

bash "$SCRIPT_DIR/pre_home.sh"
bash "$SCRIPT_DIR/install_rpi_base.sh"
bash "$SCRIPT_DIR/install_conda_base.sh"
bash "$SCRIPT_DIR/create_lab314_env.sh"
if [[ -n $app_source && ! -d /opt/rpi ]]; then bash "$SCRIPT_DIR/create_rpi_env.sh"; fi
bash "$SCRIPT_DIR/enable_lab314_autoactivate_rpi.sh"
bash "$SCRIPT_DIR/install_envrun.sh"
if [[ -n $app_source ]]; then
    bash "$SCRIPT_DIR/install_sci_apps.sh" --source "$app_source" --approve cam-imgcheck
fi
bash "$SCRIPT_DIR/verify_rpi_lab314.sh"
if [[ -n $app_source ]]; then
    bash "$SCRIPT_DIR/verify_rpi_env.sh"
    bash "$SCRIPT_DIR/verify_sci_apps.sh"
fi
