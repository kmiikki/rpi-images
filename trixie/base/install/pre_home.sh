#!/usr/bin/env bash
# Standalone HOME provisioning; Imager supplies the normal primary account.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export PRIMARY_USER="${PRIMARY_USER:-${SUDO_USER:-}}"
export NTP_PRIMARY="${NTP_PRIMARY:-time.mikes.fi}"
export SSH_POLICY="${SSH_POLICY:-$([[ ${ENABLE_SSH_SERVER:-0} == 1 ]] && echo enable || echo keep)}"
exec bash "$here/pre_profile.sh" HOME
