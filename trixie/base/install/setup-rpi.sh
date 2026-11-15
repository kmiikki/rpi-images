#!/usr/bin/env bash
# One initial-provisioning interface; component installers remain independent.
set -euo pipefail
[[ $- != *x* ]] || { echo 'Disable tracing before account provisioning' >&2; exit 2; }
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export PYTHONDONTWRITEBYTECODE=1
exec /usr/bin/python3 -B "$here/setup_rpi.py" "$@"
