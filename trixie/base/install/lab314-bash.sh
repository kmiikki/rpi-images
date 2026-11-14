# Bash-only interactive startup fragment, installed system-wide.
[[ $- == *i* ]] || return 0

__lab314_register_prompt() {
    local command
    local -a preserved=()
    # A scalar retains its complete shell syntax as one array element.
    for command in "${PROMPT_COMMAND[@]}"; do
        [[ $command == __lab314_before_prompt || -z $command ]] || preserved+=("$command")
    done
    PROMPT_COMMAND=("${preserved[@]}" __lab314_before_prompt)
}

__lab314_before_prompt() {
    local status=$?
    # Bootstrap is over. Leave any trap installed by the user intact.
    if [[ $(trap -p RETURN) == "trap -- '__lab314_register_prompt' RETURN" ]]; then
        trap - RETURN
    fi
    if [[ ${__lab314_initialized:-0} == 0 ]]; then
        __lab314_initialized=1
        if [[ -r /etc/profile.d/sci-path.sh ]]; then . /etc/profile.d/sci-path.sh; fi
        if [[ ! -r /opt/conda/etc/profile.d/conda.sh ]]; then return "$status"; fi
        . /opt/conda/etc/profile.d/conda.sh
        # Apply the same Conda label policy to later manual activations in
        # this shell; do not write user or system condarc files.
        export CONDA_CHANGEPS1=true
        export CONDA_ENV_PROMPT='({name}) '
        if [[ -z ${CONDA_PREFIX:-} ]]; then
            CONDA_CHANGEPS1=true CONDA_ENV_PROMPT='({name}) ' conda activate /opt/lab314 ||
                printf '%s\n' 'Could not activate /opt/lab314' >&2
        else
            # An inherited or user-selected environment is retained.
            CONDA_CHANGEPS1=true __conda_reactivate
        fi
    fi
    # A user prompt function may reconstruct PS1 for every prompt. Ask Conda
    # to recalculate its modifier only when that modifier was overwritten.
    if [[ -n ${CONDA_PREFIX:-} && -n ${CONDA_PROMPT_MODIFIER:-} &&
          $PS1 != "$CONDA_PROMPT_MODIFIER"* ]]; then
        CONDA_CHANGEPS1=true __conda_reactivate
    fi
    # Conda versions can strip the configured trailing separator.
    if [[ -n ${CONDA_PREFIX:-} && -n ${CONDA_PROMPT_MODIFIER:-} &&
          $CONDA_PROMPT_MODIFIER != *' ' && $PS1 == "$CONDA_PROMPT_MODIFIER"* ]]; then
        PS1="$CONDA_PROMPT_MODIFIER ${PS1#"$CONDA_PROMPT_MODIFIER"}"
        CONDA_PROMPT_MODIFIER+=' '
    fi
    return "$status"
}

__lab314_register_prompt
# Reattach after subsequently sourced user startup files have assigned their
# own PROMPT_COMMAND. This temporary trap ends before the first prompt hook.
if [[ -z $(trap -p RETURN) ]]; then
    trap '__lab314_register_prompt' RETURN
fi
