#!/usr/bin/env bash
# Legacy AALTO entrypoint: validate the shared CHEM policy before any host changes.
set -euo pipefail
(($# == 0)) || { echo 'Usage: pre_aalto.sh (account overrides use PRIMARY_USER and EXTRA_SUDO_USERS)' >&2; exit 2; }
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
policy=$(/usr/bin/python3 -B - "$here" <<'PY_POLICY'
import os
import sys
sys.path.insert(0,sys.argv[1])
from rpi_accounts import aalto_account_plan
try:
    raw=os.environ.get('EXTRA_SUDO_USERS')
    plan=aalto_account_plan(os.environ.get('PRIMARY_USER'),None if raw is None else raw.split())
except ValueError as exc:
    sys.exit('Error: '+str(exc))
print(plan['primary'])
print(' '.join(plan['additional']))
PY_POLICY
)
mapfile -t policy_lines <<< "$policy"
export PRIMARY_USER="${policy_lines[0]}"
export EXTRA_SUDO_USERS="${policy_lines[1]}"
export NTP_PRIMARY="${NTP_PRIMARY:-ntp.aalto.fi}"
export SSH_POLICY="${SSH_POLICY:-keep}"
exec bash "$here/pre_profile.sh" AALTO
