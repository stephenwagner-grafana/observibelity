#!/usr/bin/env bash
# check-scaffold.sh — audit the ObserVIBElity scaffold for internal consistency.
#
# Runs read-only checks; exits 0 if everything passes, 1 otherwise.

set -uo pipefail  # NB: no -e, we want to collect all failures

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/tools/lib/logging.sh"

FAIL=0
TOTAL_CHECKS=0
declare -a FAILURES=()

check() {
  local label="$1"
  TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
  if "${@:2}" >/dev/null 2>&1; then
    ok "$label"
  else
    err "$label"
    FAILURES+=("$label")
    FAIL=$((FAIL + 1))
  fi
}

step "verify-repo" "Auditing $REPO_ROOT"

# ── 1. Executable bits ──────────────────────────────────────────────────────
log "1. Executable scripts"
EXEC_SCRIPTS=(
  install.sh
  uninstall.sh
  tools/wizard.sh
  tools/bootstrap-cluster.sh
  tools/deploy-doctor.sh
  tools/verify.sh
  tools/evaluators-sync.sh
  tools/backup.sh
  tools/restore.sh
  tools/bump-version.sh
  tools/build-images.sh
  tools/check-scaffold.sh
  tools/preflight/main.sh
  tools/preflight/detect-os.sh
  tools/preflight/check-binaries.sh
  tools/preflight/check-cluster.sh
  tools/preflight/check-credentials.sh
  tools/preflight/install-tool.sh
  tests/e2e/smoke-k3d.sh
)
for s in "${EXEC_SCRIPTS[@]}"; do
  if [[ -x "$REPO_ROOT/$s" ]]; then
    ok "  +x $s"
  else
    if [[ -f "$REPO_ROOT/$s" ]]; then
      err "  $s exists but not chmod +x"
      FAILURES+=("not executable: $s")
      FAIL=$((FAIL + 1))
    else
      warn "  $s missing"
    fi
  fi
done

# ── 2. Bash sourcing ────────────────────────────────────────────────────────
log "2. Bash 'source' references"
while IFS= read -r script; do
  while IFS= read -r line; do
    sourced=$(echo "$line" | sed -E 's/.*source[ \t]+"?([^" ]+)"?.*/\1/' | sed "s|\$REPO_ROOT|$REPO_ROOT|g")
    # Skip if the path still contains unexpanded shell substitution ($ or $()).
    # Those resolve at runtime; we can't statically verify them.
    if [[ "$sourced" == *'$'* ]] || [[ "$sourced" == *'('* ]]; then
      continue
    fi
    # try to resolve relative to script's dir
    script_dir="$(dirname "$REPO_ROOT/$script")"
    resolved=""
    if [[ -f "$sourced" ]]; then resolved="$sourced"; fi
    if [[ -f "$script_dir/$sourced" ]]; then resolved="$script_dir/$sourced"; fi
    if [[ -z "$resolved" ]]; then
      err "  $script sources missing: $sourced"
      FAILURES+=("broken source: $script -> $sourced")
      FAIL=$((FAIL + 1))
    fi
  done < <(grep -E '^[[:space:]]*source[[:space:]]+' "$REPO_ROOT/$script" 2>/dev/null | grep -v '^[[:space:]]*#')
done < <(find "$REPO_ROOT" -type f \( -name "*.sh" -o -name "*.bats" \) -not -path "*/.venv/*" -not -path "*/.git/*" -not -path "*/node_modules/*" -printf "%P\n")

# ── 3. Python module imports ────────────────────────────────────────────────
log "3. Python imports (deploy_doctor)"
if command -v python3 >/dev/null 2>&1; then
  for pyfile in $(find "$REPO_ROOT/tools/deploy_doctor" -name "*.py" 2>/dev/null); do
    if python3 -c "import ast; ast.parse(open('$pyfile').read())" 2>/dev/null; then
      ok "  parses: ${pyfile#$REPO_ROOT/}"
    else
      err "  fails to parse: ${pyfile#$REPO_ROOT/}"
      FAILURES+=("parse fail: ${pyfile#$REPO_ROOT/}")
      FAIL=$((FAIL + 1))
    fi
  done
else
  warn "  python3 not available; skipping parse checks"
fi

# ── 4. Markdown internal links ──────────────────────────────────────────────
log "4. Markdown internal links"
broken_links=0
while IFS= read -r mdfile; do
  while IFS= read -r link_target; do
    # skip external (http://, https://, mailto:, #anchor)
    [[ "$link_target" =~ ^(https?|mailto|#) ]] && continue
    # strip trailing #anchor
    link_path="${link_target%%#*}"
    [[ -z "$link_path" ]] && continue
    md_dir="$(dirname "$REPO_ROOT/$mdfile")"
    # resolve relative
    resolved="$md_dir/$link_path"
    if [[ -e "$resolved" ]]; then continue; fi
    if [[ -e "$REPO_ROOT/$link_path" ]]; then continue; fi
    # GitHub Wiki link convention: [Title](Page-Name) → wiki/Page-Name.md.
    # If we're inside wiki/, treat extensionless links as wiki page refs.
    if [[ "$mdfile" == wiki/* ]] && [[ "$link_path" != *.* ]] && [[ "$link_path" != */* ]]; then
      if [[ -e "$REPO_ROOT/wiki/$link_path.md" ]]; then continue; fi
    fi
    # CONSISTENCY_REPORT.md may also reference wiki page names; allow.
    if [[ "$link_path" != *.* ]] && [[ "$link_path" != */* ]]; then
      if [[ -e "$REPO_ROOT/wiki/$link_path.md" ]]; then continue; fi
    fi
    # Auto-synced wiki pages: docs/*.md → wiki/*.md via wiki-sync.yml workflow.
    # Listed pages exist only in CI/published wiki; locally we have them as docs/*.
    case "$link_path" in
      Install|Architecture|Troubleshooting|Providers|Development|Gitops|Claude-Code|Quick-Start)
        continue ;;
    esac
    err "  $mdfile -> $link_target (missing)"
    FAILURES+=("broken link: $mdfile -> $link_target")
    FAIL=$((FAIL + 1))
    broken_links=$((broken_links + 1))
  done < <(grep -oE '\]\([^)]+\)' "$REPO_ROOT/$mdfile" 2>/dev/null | sed -E 's/^\]\(([^)]+)\)$/\1/')
done < <(find "$REPO_ROOT" -name "*.md" -not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/.venv/*" -printf "%P\n")
[[ "$broken_links" -eq 0 ]] && ok "  all internal links resolve"

# ── 5. Required top-level files ─────────────────────────────────────────────
log "5. Required files"
REQUIRED=(
  Chart.yaml values.yaml install.sh uninstall.sh Makefile README.md LICENSE
  .gitignore .editorconfig CHANGELOG.md CONTRIBUTING.md SECURITY.md
  templates/_helpers.tpl
  tests/snapshots/default.golden.yaml
)
for f in "${REQUIRED[@]}"; do
  if [[ -f "$REPO_ROOT/$f" ]]; then
    ok "  $f"
  else
    err "  $f missing"
    FAILURES+=("required file missing: $f")
    FAIL=$((FAIL + 1))
  fi
done

# ── 6. Helm template snapshot freshness ─────────────────────────────────────
log "6. Helm template snapshot"
if command -v helm >/dev/null 2>&1; then
  if helm template obs "$REPO_ROOT" --namespace observibelity > /tmp/scaffold-check-rendered.yaml 2>/dev/null; then
    # Strip the snapshot's documentation preamble (lines before first `---`).
    awk 'flag || /^---$/ {flag=1; print}' "$REPO_ROOT/tests/snapshots/default.golden.yaml" > /tmp/scaffold-golden.body
    awk 'flag || /^---$/ {flag=1; print}' /tmp/scaffold-check-rendered.yaml > /tmp/scaffold-rendered.body
    if diff -q /tmp/scaffold-golden.body /tmp/scaffold-rendered.body >/dev/null 2>&1; then
      ok "  snapshot matches helm template output"
    else
      err "  snapshot drift — run 'make snapshot' to regenerate"
      FAILURES+=("snapshot drift")
      FAIL=$((FAIL + 1))
    fi
    rm -f /tmp/scaffold-check-rendered.yaml /tmp/scaffold-golden.body /tmp/scaffold-rendered.body
  else
    warn "  helm template failed; skipping"
  fi
else
  warn "  helm not available; skipping snapshot check"
fi

# ── 7. .gitignore coverage ──────────────────────────────────────────────────
log "7. .gitignore patterns"
REQUIRED_IGNORES=(
  ".env"
  ".observibelity-state"
  "tools/bin/"
  "tools/.venv/"
  "observibelity-failure-*.tar.gz"
  "__pycache__"
)
for pattern in "${REQUIRED_IGNORES[@]}"; do
  if grep -qF "$pattern" "$REPO_ROOT/.gitignore" 2>/dev/null; then
    ok "  ignores $pattern"
  else
    err "  .gitignore missing: $pattern"
    FAILURES+=("gitignore missing: $pattern")
    FAIL=$((FAIL + 1))
  fi
done

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
log "Summary: $((TOTAL_CHECKS - FAIL))/$TOTAL_CHECKS checks would pass"
if [[ "$FAIL" -eq 0 ]]; then
  ok "✓ scaffold consistency verified"
  exit 0
else
  err "✗ $FAIL issue(s):"
  for f in "${FAILURES[@]}"; do
    echo "    - $f" >&2
  done
  exit 1
fi
