#!/usr/bin/env bats
# Tests for tools/preflight/* scripts.
# Each test sets up an isolated temp dir with lib/ + preflight/ symlinked in.

setup() {
    SRC_REPO="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    export SRC_REPO

    # Build an isolated repo layout for this test
    mkdir -p "${BATS_TEST_TMPDIR}/tools/lib"
    mkdir -p "${BATS_TEST_TMPDIR}/tools/preflight"

    # Symlink (or copy if symlinks are unavailable) lib + preflight contents
    if [ -d "${SRC_REPO}/tools/lib" ]; then
        for f in "${SRC_REPO}/tools/lib/"*.sh; do
            [ -f "$f" ] && ln -sf "$f" "${BATS_TEST_TMPDIR}/tools/lib/$(basename "$f")"
        done
    fi
    if [ -d "${SRC_REPO}/tools/preflight" ]; then
        for f in "${SRC_REPO}/tools/preflight/"*.sh; do
            [ -f "$f" ] && ln -sf "$f" "${BATS_TEST_TMPDIR}/tools/preflight/$(basename "$f")"
        done
    fi

    cd "${BATS_TEST_TMPDIR}"
    export REPO_ROOT="${PWD}"
    export OBSERVIBELITY_STATE_DIR="${BATS_TEST_TMPDIR}/.observibelity-state"
    mkdir -p "${OBSERVIBELITY_STATE_DIR}"
}

teardown() {
    cd "${BATS_TEST_DIRNAME}"
}

# Helper: install a shim binary in a dir that is on PATH
_shim() {
    local name="$1"
    local script="$2"
    local dir="${BATS_TEST_TMPDIR}/shimbin"
    mkdir -p "$dir"
    printf '#!/usr/bin/env bash\n%s\n' "$script" > "$dir/$name"
    chmod +x "$dir/$name"
    export PATH="$dir:$PATH"
}

@test "detect-os.sh exits 0 and writes preflight.os in state" {
    if [ ! -f "${BATS_TEST_TMPDIR}/tools/preflight/detect-os.sh" ]; then
        skip "preflight/detect-os.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    run bash "${BATS_TEST_TMPDIR}/tools/preflight/detect-os.sh"
    [[ "$status" -eq 0 ]]
    # State file should contain an os key after the script runs
    [ -f "${OBSERVIBELITY_STATE_DIR}/state.json" ]
    run grep -q '"os"' "${OBSERVIBELITY_STATE_DIR}/state.json"
    [[ "$status" -eq 0 ]]
}

@test "check-binaries.sh detects missing kubectl when PATH is sparse" {
    if [ ! -f "${BATS_TEST_TMPDIR}/tools/preflight/check-binaries.sh" ]; then
        skip "preflight/check-binaries.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    # We want only system binaries (bash, jq, sed) on PATH — no kubectl/helm.
    # Hand-pick a directory that contains the basics but not k8s tools.
    minpath="/usr/bin:/bin"
    # Force OBSERVIBELITY_NO_INSTALL so the script exits without prompting.
    run env PATH="$minpath" OBSERVIBELITY_NO_INSTALL=1 \
        bash "${BATS_TEST_TMPDIR}/tools/preflight/check-binaries.sh"
    [[ "$status" -ne 0 ]]
    [[ "$output" =~ kubectl ]]
}

@test "check-cluster.sh fails when kubectl not configured (KUBECONFIG=/nonexistent)" {
    if [ ! -f "${BATS_TEST_TMPDIR}/tools/preflight/check-cluster.sh" ]; then
        skip "preflight/check-cluster.sh not yet implemented (Phase 0 scaffold not present)"
    fi
    # Provide a kubectl shim that fails like the real one when KUBECONFIG is bogus
    _shim kubectl 'echo "error: unable to read kubeconfig" >&2; exit 1'
    # OBSERVIBELITY_AUTO=1 skips the interactive "how would you like to
    # proceed?" prompt in check-cluster.sh — without it the prompt hangs
    # forever when stdin is closed (as it is in CI).
    run env KUBECONFIG="/nonexistent" OBSERVIBELITY_AUTO=1 \
        bash "${BATS_TEST_TMPDIR}/tools/preflight/check-cluster.sh"
    [[ "$status" -ne 0 ]]
}
