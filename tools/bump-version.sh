#!/usr/bin/env bash
# bump-version.sh — atomically bump version in Chart.yaml + pyproject.toml + CHANGELOG.md
#
# Usage:
#   ./tools/bump-version.sh <new-version>
#   ./tools/bump-version.sh 0.2.0
#
# Validates semver. Moves [Unreleased] entries into [new-version] section
# with today's date. Inserts a new empty [Unreleased] section above.
# Prints diff at the end. Does NOT git commit (do that yourself).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/tools/lib/logging.sh"

NEW_VERSION="${1:-}"
if [[ -z "$NEW_VERSION" ]]; then
  die "Usage: $0 <new-version>  (e.g. $0 0.2.0)"
fi

# semver validation
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
  die "Not a valid semver: $NEW_VERSION  (expect MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-prerelease)"
fi

CURRENT_VERSION="$(awk '/^version:/ {print $2; exit}' "$REPO_ROOT/Chart.yaml")"
[[ -n "$CURRENT_VERSION" ]] || die "Could not read current version from Chart.yaml"

step "bump-version" "Bumping $CURRENT_VERSION -> $NEW_VERSION"

# Use a temp dir for atomicity
TMPDIR="$(mktemp -d)"
trap "rm -rf $TMPDIR" EXIT

# Detect sed flavor
sed_inplace() {
  if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' "$@"
  else
    sed -i "$@"
  fi
}

# 1. Chart.yaml: bump version + appVersion
cp "$REPO_ROOT/Chart.yaml" "$TMPDIR/Chart.yaml"
sed_inplace "s/^version: .*/version: $NEW_VERSION/" "$TMPDIR/Chart.yaml"
sed_inplace "s/^appVersion: .*/appVersion: $NEW_VERSION/" "$TMPDIR/Chart.yaml"

# 2. tools/pyproject.toml: bump version
cp "$REPO_ROOT/tools/pyproject.toml" "$TMPDIR/pyproject.toml"
sed_inplace "s/^version = \".*\"/version = \"$NEW_VERSION\"/" "$TMPDIR/pyproject.toml"

# 3. CHANGELOG.md: move [Unreleased] to [new-version] with today's date
cp "$REPO_ROOT/CHANGELOG.md" "$TMPDIR/CHANGELOG.md.bak"
TODAY="$(date +%Y-%m-%d)"
awk -v new="$NEW_VERSION" -v today="$TODAY" '
  /^## \[Unreleased\]/ {
    print "## [Unreleased]"
    print ""
    print "## [" new "] - " today
    next
  }
  { print }
' "$TMPDIR/CHANGELOG.md.bak" > "$TMPDIR/CHANGELOG.md"

# Add the new compare link at the bottom (after the last existing link)
if grep -q "^\[Unreleased\]:" "$TMPDIR/CHANGELOG.md"; then
  sed_inplace "s|^\[Unreleased\]: .*|[Unreleased]: https://github.com/stephenwagner-grafana/observibelity/compare/v${NEW_VERSION}...HEAD|" "$TMPDIR/CHANGELOG.md"
  # Insert the new tag link right after [Unreleased]
  awk -v new="$NEW_VERSION" -v current="$CURRENT_VERSION" '
    /^\[Unreleased\]:/ {
      print
      print "[" new "]: https://github.com/stephenwagner-grafana/observibelity/compare/v" current "...v" new
      next
    }
    { print }
  ' "$TMPDIR/CHANGELOG.md" > "$TMPDIR/CHANGELOG.md.new"
  mv "$TMPDIR/CHANGELOG.md.new" "$TMPDIR/CHANGELOG.md"
fi

# Atomic move
mv "$TMPDIR/Chart.yaml" "$REPO_ROOT/Chart.yaml"
mv "$TMPDIR/pyproject.toml" "$REPO_ROOT/tools/pyproject.toml"
mv "$TMPDIR/CHANGELOG.md" "$REPO_ROOT/CHANGELOG.md"

ok "Bumped to $NEW_VERSION across Chart.yaml + tools/pyproject.toml + CHANGELOG.md"
log "Next: git diff && git commit -am \"Release v$NEW_VERSION\" && git tag v$NEW_VERSION && git push --tags"
