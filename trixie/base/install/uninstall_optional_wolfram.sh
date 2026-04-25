#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"

AUTO_YES=0
DRY_RUN=0
VERBOSE=0

usage() {
    cat <<EOF
Usage: $SCRIPT_NAME [OPTIONS]

Optional removal: Wolfram Engine

Options:
  -y, --yes       Run non-interactively, auto-confirm prompts
  -n, --dry-run   Show what would be done, but do not make changes
  -v, --verbose   Enable verbose output
  -h, --help      Show this help

Examples:
  $SCRIPT_NAME
  $SCRIPT_NAME --yes
  $SCRIPT_NAME --dry-run
  $SCRIPT_NAME --yes --verbose
EOF
}

log() {
    printf '%s\n' "$*"
}

vlog() {
    if [[ "$VERBOSE" -eq 1 ]]; then
        printf '%s\n' "$*"
    fi
}

warn() {
    printf 'WARNING: %s\n' "$*" >&2
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -y|--yes)
                AUTO_YES=1
                ;;
            -n|--dry-run)
                DRY_RUN=1
                ;;
            -v|--verbose)
                VERBOSE=1
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                die "Unknown option: $1"
                ;;
        esac
        shift
    done
}

confirm() {
    local prompt="${1:-Continue? [y/N] }"

    if [[ "$AUTO_YES" -eq 1 ]]; then
        log "Auto-confirm enabled (--yes), continuing..."
        return 0
    fi

    local reply
    read -r -p "$prompt" reply || true
    case "$reply" in
        y|Y|yes|YES)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

run_cmd() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        log "[dry-run] $*"
        return 0
    fi

    vlog "+ $*"
    "$@"
}

main() {
    parse_args "$@"

    log "Optional removal: Wolfram Engine"
    log

    if [[ "$DRY_RUN" -eq 1 ]]; then
        log "Dry-run mode enabled: no changes will be made."
        log
    fi

    if ! dpkg -s wolfram-engine >/dev/null 2>&1; then
        log "wolfram-engine is not installed."
        exit 0
    fi

    vlog "Detected installed package: wolfram-engine"

    if ! confirm "Remove wolfram-engine and run autoremove? [y/N] "; then
        log "Cancelled."
        exit 0
    fi

    run_cmd sudo apt remove -y wolfram-engine
    run_cmd sudo apt autoremove -y

    log
    if [[ "$DRY_RUN" -eq 1 ]]; then
        log "Dry-run complete."
    else
        log "Done."
    fi
}

main "$@"
