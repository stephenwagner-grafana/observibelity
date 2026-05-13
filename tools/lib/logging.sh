# shellcheck shell=bash
# ObserVIBElity shared lib: structured stderr logging (log/ok/warn/err/die/step).

# Tolerate a missing colors.sh — tests sometimes copy only logging.sh+state.sh
# into an isolated tempdir. Set unset-only fallbacks (using ${VAR-} below) so
# we never reassign readonly vars that colors.sh may have already declared.
# shellcheck disable=SC1091
_logging_dir="$(dirname "${BASH_SOURCE[0]}")"
if [[ -f "$_logging_dir/colors.sh" ]]; then
    # shellcheck disable=SC1091
    source "$_logging_dir/colors.sh"
fi
# Only declare fallbacks when the variable is *unset* — `${COLOR_RESET+x}` is
# empty iff unset; we check that and `declare` so the value is empty string.
for _c in COLOR_RESET COLOR_RED COLOR_GREEN COLOR_YELLOW COLOR_CYAN COLOR_BOLD COLOR_DIM; do
    if ! declare -p "$_c" >/dev/null 2>&1; then
        declare -g -- "$_c="
    fi
done
unset _c

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
