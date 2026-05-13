# shellcheck shell=bash
# ObserVIBElity shared lib: interactive prompts (ask/ask_secret/ask_yn/ask_choice). Honors OBSERVIBELITY_AUTO=1.

source "$(dirname "${BASH_SOURCE[0]}")/logging.sh"

# ask <prompt> [default] — read a line. Empty input falls back to default.
# Echo the answer to stdout (so callers can capture it via $(...)).
ask() {
    local prompt="$1"
    local default="${2:-}"
    local display="${prompt}"
    if [[ -n "${default}" ]]; then
        display="${prompt} (default: ${default})"
    fi

    if [[ "${OBSERVIBELITY_AUTO:-0}" == "1" ]]; then
        if [[ -z "${default}" ]]; then
            die "ask: OBSERVIBELITY_AUTO=1 set but no default for prompt: ${prompt}"
        fi
        printf '%s' "${default}"
        return 0
    fi

    local answer
    printf '%s: ' "${display}" >&2
    IFS= read -r answer
    if [[ -z "${answer}" ]]; then
        answer="${default}"
    fi
    printf '%s' "${answer}"
}

# ask_secret <prompt> — silent read (no echo). Newline after. No default.
ask_secret() {
    local prompt="$1"

    if [[ "${OBSERVIBELITY_AUTO:-0}" == "1" ]]; then
        die "ask_secret: OBSERVIBELITY_AUTO=1 set but no default support for secrets: ${prompt}"
    fi

    local answer
    printf '%s: ' "${prompt}" >&2
    IFS= read -rs answer
    printf '\n' >&2
    printf '%s' "${answer}"
}

# ask_yn <prompt> [Y|N] — yes/no with default. Returns 0 for yes, 1 for no.
ask_yn() {
    local prompt="$1"
    local default="${2:-N}"
    local hint
    case "${default}" in
        Y|y) hint="[Y/n]" ;;
        N|n) hint="[y/N]" ;;
        *)   die "ask_yn: default must be Y or N, got '${default}'" ;;
    esac

    if [[ "${OBSERVIBELITY_AUTO:-0}" == "1" ]]; then
        case "${default}" in
            Y|y) return 0 ;;
            N|n) return 1 ;;
        esac
    fi

    local answer
    while true; do
        printf '%s %s: ' "${prompt}" "${hint}" >&2
        IFS= read -r answer
        if [[ -z "${answer}" ]]; then
            case "${default}" in
                Y|y) return 0 ;;
                N|n) return 1 ;;
            esac
        fi
        case "${answer}" in
            y|Y|yes|YES|Yes) return 0 ;;
            n|N|no|NO|No)    return 1 ;;
            *) warn "Please answer y or n." ;;
        esac
    done
}

# ask_choice <prompt> [--echo-value] <opt1> <opt2> ...
#   Prints a numbered menu, reads selection. Echoes 1-based index to stdout,
#   or the chosen option string if --echo-value is given as the first arg after
#   prompt. Loops on invalid input.
ask_choice() {
    local prompt="$1"
    shift
    local echo_value=0
    if [[ "${1:-}" == "--echo-value" ]]; then
        echo_value=1
        shift
    fi

    local options=("$@")
    local n=${#options[@]}
    if (( n == 0 )); then
        die "ask_choice: no options provided"
    fi

    if [[ "${OBSERVIBELITY_AUTO:-0}" == "1" ]]; then
        if (( echo_value == 1 )); then
            printf '%s' "${options[0]}"
        else
            printf '%s' "1"
        fi
        return 0
    fi

    printf '%s\n' "${prompt}" >&2
    local i
    for (( i=0; i<n; i++ )); do
        printf '  (%d) %s\n' "$((i+1))" "${options[i]}" >&2
    done

    local answer
    while true; do
        printf 'Select [1-%d]: ' "${n}" >&2
        IFS= read -r answer
        if [[ "${answer}" =~ ^[0-9]+$ ]] && (( answer >= 1 && answer <= n )); then
            if (( echo_value == 1 )); then
                printf '%s' "${options[$((answer-1))]}"
            else
                printf '%s' "${answer}"
            fi
            return 0
        fi
        warn "Please enter a number between 1 and ${n}."
    done
}
