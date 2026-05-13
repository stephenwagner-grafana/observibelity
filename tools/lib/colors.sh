# shellcheck shell=bash
# ObserVIBElity shared lib: ANSI color codes. Honors NO_COLOR + TTY + FORCE_COLOR.

# Idempotent source guard — readonly vars below would error on re-source.
if [[ -n "${_OBSERVIBELITY_COLORS_LOADED:-}" ]]; then
    return 0 2>/dev/null || true
fi
_OBSERVIBELITY_COLORS_LOADED=1

# Decide whether to emit ANSI escapes. Honor NO_COLOR (any non-empty value
# disables color, per https://no-color.org/). Otherwise require stderr to be a
# TTY, unless FORCE_COLOR=1 overrides.
if [[ -n "${NO_COLOR:-}" ]]; then
    _obs_use_color=0
elif [[ "${FORCE_COLOR:-}" == "1" ]]; then
    _obs_use_color=1
elif [[ -t 2 ]]; then
    _obs_use_color=1
else
    _obs_use_color=0
fi

if [[ "${_obs_use_color}" == "1" ]]; then
    readonly COLOR_RESET=$'\033[0m'
    readonly COLOR_RED=$'\033[31m'
    readonly COLOR_GREEN=$'\033[32m'
    readonly COLOR_YELLOW=$'\033[33m'
    readonly COLOR_BLUE=$'\033[34m'
    readonly COLOR_MAGENTA=$'\033[35m'
    readonly COLOR_CYAN=$'\033[36m'
    readonly COLOR_BOLD=$'\033[1m'
    readonly COLOR_DIM=$'\033[2m'
else
    readonly COLOR_RESET=""
    readonly COLOR_RED=""
    readonly COLOR_GREEN=""
    readonly COLOR_YELLOW=""
    readonly COLOR_BLUE=""
    readonly COLOR_MAGENTA=""
    readonly COLOR_CYAN=""
    readonly COLOR_BOLD=""
    readonly COLOR_DIM=""
fi

unset _obs_use_color
