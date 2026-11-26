#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
options=()
for option in "$@"; do
    case $option in
        -h|--help) printf '%s\n' 'Usage: uninstall_optional_wolfram.sh [--dry-run] [--yes]'; exit 0 ;;
        -n|--dry-run) options+=(--plan) ;;
        -y|--yes) options+=(--confirm REMOVE) ;;
        -v|--verbose) ;; # The lifecycle command always prints the removal plan.
        *) printf 'Unknown option: %s\n' "$option" >&2; exit 2 ;;
    esac
done
exec bash "$here/setup-rpi.sh" --manage --action remove --component wolfram "${options[@]}"
