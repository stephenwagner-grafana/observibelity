# shellcheck shell=bash
# ObserVIBElity shared lib: structured stderr logging (log/ok/warn/err/die/step).

source "$(dirname "${BASH_SOURCE[0]}")/colors.sh"

# log <msg> — informational. Cyan "[OBS]" prefix.
log() {
    printf '%s[OBS]%s %s\n' "${COLOR_CYAN}" "${COLOR_RESET}" "$1" >&2
}

# ok <msg> — success. Green checkmark prefix.
ok() {
    printf '%s\xe2\x9c\x93%s %s\n' "${COLOR_GREEN}" "${COLOR_RESET}" "$1" >&2
}

# warn <msg> — warning. Yellow ! prefix.
warn() {
    printf '%s!%s %s\n' "${COLOR_YELLOW}" "${COLOR_RESET}" "$1" >&2
}

# err <msg> — error. Red x prefix.
err() {
    printf '%s\xe2\x9c\x97%s %s\n' "${COLOR_RED}" "${COLOR_RESET}" "$1" >&2
}

# die <msg> — error then exit 1.
die() {
    err "$1"
    exit 1
}

# step <name> <msg> — section header. Blank line + bold cyan triangle name,
# then dim sub-message.
step() {
    printf '\n%s%s\xe2\x96\xb8 %s%s\n' "${COLOR_BOLD}" "${COLOR_CYAN}" "$1" "${COLOR_RESET}" >&2
    printf '%s  %s%s\n' "${COLOR_DIM}" "$2" "${COLOR_RESET}" >&2
}
