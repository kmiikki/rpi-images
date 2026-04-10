#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF' | sudo tee -a /etc/bash.bashrc >/dev/null
# >>> LAB314 BEGIN >>>
if [ -f /opt/conda/etc/profile.d/conda.sh ]; then
    . /opt/conda/etc/profile.d/conda.sh
    conda activate /opt/lab314 >/dev/null 2>&1 || true
fi

__lab314_prompt() {
    case "$PS1" in
        "(lab314) "*) ;;
        *) PS1="(lab314) $PS1" ;;
    esac
}

if [[ -z "${PROMPT_COMMAND:-}" ]]; then
    PROMPT_COMMAND="__lab314_prompt"
else
    PROMPT_COMMAND="__lab314_prompt; $PROMPT_COMMAND"
fi
# <<< LAB314 END <<<
EOF