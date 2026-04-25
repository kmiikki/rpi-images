#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"

AUTO_YES=0
DRY_RUN=0
VERBOSE=0

usage() {
    cat <<EOF
Usage: $SCRIPT_NAME [OPTIONS]

Optional installation: Wolfram Engine for Raspberry Pi OS

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

is_raspberry_pi_os() {
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        vlog "os-release: ID='${ID:-}', ID_LIKE='${ID_LIKE:-}', PRETTY_NAME='${PRETTY_NAME:-}'"

        if [[ "${ID:-}" == "raspbian" || "${ID_LIKE:-}" == *"raspbian"* ]]; then
            return 0
        fi
    fi

    if grep -qi "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
        vlog "Detected Raspberry Pi via /proc/cpuinfo fallback."
        return 0
    fi

    return 1
}

get_mem_mb() {
    awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo
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

    log "Optional installation: Wolfram Engine for Raspberry Pi OS"
    log

    if [[ "$DRY_RUN" -eq 1 ]]; then
        log "Dry-run mode enabled: no changes will be made."
        log
    fi

    if ! is_raspberry_pi_os; then
        die "This script is intended for Raspberry Pi OS only."
    fi

    local mem_mb
    mem_mb="$(get_mem_mb)"

    log "System check"
    log "  OS  : Raspberry Pi OS"
    log "  RAM : ${mem_mb} MB"
    log

    log "Important notice"
    log "  - Wolfram Engine is intentionally not included in the base image."
    log "  - It uses a significant amount of disk space."
    log "  - It may be impractical on low-memory systems."
    log "  - Raspberry Pi Wolfram licensing may limit commercial use."
    log "  - You are responsible for ensuring that your use complies with"
    log "    the applicable license terms."
    log

    if [[ "$mem_mb" -lt 2000 ]]; then
        warn "Detected less than 2000 MB RAM."
        warn "Wolfram Engine may be too heavy for practical use on this system."
        log
    fi

    if command -v wolframscript >/dev/null 2>&1; then
        log "wolframscript is already available in PATH."
        if ! confirm "Reinstall/upgrade via apt anyway? [y/N] "; then
            log "Cancelled."
            exit 0
        fi
    else
        if ! confirm "Continue with Wolfram Engine installation? [y/N] "; then
            log "Cancelled."
            exit 0
        fi
    fi

    run_cmd sudo apt update
    run_cmd sudo apt install -y wolfram-engine

    log
    log "Verifying installation..."

    if [[ "$DRY_RUN" -eq 1 ]]; then
        log "[dry-run] Would verify that 'wolframscript' is available in PATH."
        log "[dry-run] Would run: wolframscript -code 2+2"
        log
        log "Dry-run complete."
        exit 0
    fi

    if ! command -v wolframscript >/dev/null 2>&1; then
        die "Installation finished, but 'wolframscript' was not found in PATH."
    fi

    if wolframscript -code "2+2" >/dev/null 2>&1; then
        log "Success: wolframscript is working."
    else
        warn "wolframscript was found, but the test command did not complete cleanly."
        warn "Please test manually."
    fi

    log
    log "Done."
}

main "$@"
