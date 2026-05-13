#!/usr/bin/env bash
# k3s-import-images.sh — build images locally + import into k3s containerd.
# Removes the need for an external registry on single-node or air-gapped k3s.
#
# Usage:
#   ./tools/k3s-import-images.sh                  # build all + import
#   ./tools/k3s-import-images.sh --no-build       # import already-built local images
#   ./tools/k3s-import-images.sh --filter neoncart # only specific images
#   ./tools/k3s-import-images.sh --remote HOST    # ssh to remote k3s node

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/tools/lib/logging.sh"
source "$REPO_ROOT/tools/lib/prompt.sh"

VERSION="$(awk '/^version:/ {print $2; exit}' "$REPO_ROOT/Chart.yaml")"
PREFIX="${IMAGE_PREFIX:-ghcr.io/stephenwagner-grafana/observibelity}"
REGISTRY_PREFIX="ghcr.io/stephenwagner-grafana"
NO_BUILD=0
FILTER=""
REMOTE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build) NO_BUILD=1; shift ;;
    --filter) FILTER="$2"; shift 2 ;;
    --remote) REMOTE="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--no-build] [--filter REGEX] [--remote HOST] [--version VER]
Builds images locally and imports them into k3s containerd directly.

Default: builds ALL images and imports.
  --no-build       skip docker build; use existing local images
  --filter REGEX   limit to images matching REGEX
  --remote HOST    ssh to a remote k3s node (requires passwordless sudo)
  --version VER    image version tag (default: from Chart.yaml)
EOF
      exit 0 ;;
    *) die "Unknown flag: $1" ;;
  esac
done

# Image manifest (mirrors release.yml)
declare -a IMAGES=(
  "specialist-base:src/specialists:src/specialists/.Dockerfile.shared::"
  "tool-base:src/tools:src/tools/.Dockerfile.shared::"
  "neoncart:src/neoncart:src/neoncart/Dockerfile::"
  "llm-gateway:src/llm-gateway:src/llm-gateway/Dockerfile::"
  "nc-chatbot:src/specialists/nc-chatbot:src/specialists/nc-chatbot/Dockerfile:SPECIALIST_BASE=${PREFIX}-specialist-base:${VERSION}"
  "nc-fraud-detector:src/specialists/nc-fraud-detector:src/specialists/nc-fraud-detector/Dockerfile:SPECIALIST_BASE=${PREFIX}-specialist-base:${VERSION}"
  "nc-fulfillment-orchestrator:src/specialists/nc-fulfillment-orchestrator:src/specialists/nc-fulfillment-orchestrator/Dockerfile:SPECIALIST_BASE=${PREFIX}-specialist-base:${VERSION}"
  "search_products:src/tools/search_products:src/tools/search_products/Dockerfile:TOOL_BASE=${PREFIX}-tool-base:${VERSION}"
  "get_product:src/tools/get_product:src/tools/get_product/Dockerfile:TOOL_BASE=${PREFIX}-tool-base:${VERSION}"
  "get_order_history:src/tools/get_order_history:src/tools/get_order_history/Dockerfile:TOOL_BASE=${PREFIX}-tool-base:${VERSION}"
  "geo_lookup:src/tools/geo_lookup:src/tools/geo_lookup/Dockerfile:TOOL_BASE=${PREFIX}-tool-base:${VERSION}"
  "get_inventory:src/tools/get_inventory:src/tools/get_inventory/Dockerfile:TOOL_BASE=${PREFIX}-tool-base:${VERSION}"
  "place_order:src/tools/place_order:src/tools/place_order/Dockerfile:TOOL_BASE=${PREFIX}-tool-base:${VERSION}"
)

command -v docker >/dev/null || die "docker required"

# Build phase
if [[ "$NO_BUILD" -ne 1 ]]; then
  step "build" "Building $((${#IMAGES[@]})) images at v$VERSION"
  for entry in "${IMAGES[@]}"; do
    IFS=':' read -r name context dockerfile build_arg <<< "$entry"
    [[ -n "$FILTER" ]] && ! echo "$name" | grep -qE "$FILTER" && continue
    tag="${PREFIX}-${name}:${VERSION}"
    args=()
    [[ -n "$build_arg" ]] && args+=(--build-arg "$build_arg")
    log "  build $name → $tag"
    docker build "${args[@]}" -t "$tag" -t "${PREFIX}-${name}:latest" -f "$REPO_ROOT/$dockerfile" "$REPO_ROOT/$context"
  done
  ok "all images built"
fi

# Import phase
step "import" "Importing into k3s containerd"
TMPDIR="$(mktemp -d)"
trap "rm -rf $TMPDIR" EXIT

for entry in "${IMAGES[@]}"; do
  IFS=':' read -r name context dockerfile build_arg <<< "$entry"
  [[ -n "$FILTER" ]] && ! echo "$name" | grep -qE "$FILTER" && continue
  tag="${PREFIX}-${name}:${VERSION}"
  tarfile="$TMPDIR/${name}.tar"
  log "  save $tag"
  docker save "$tag" "${PREFIX}-${name}:latest" -o "$tarfile"
  if [[ -n "$REMOTE" ]]; then
    log "  scp to $REMOTE"
    scp -q "$tarfile" "$REMOTE:/tmp/$(basename "$tarfile")"
    ssh "$REMOTE" "sudo k3s ctr images import /tmp/$(basename "$tarfile") && rm -f /tmp/$(basename "$tarfile")"
  else
    sudo k3s ctr images import "$tarfile"
  fi
  rm -f "$tarfile"
done
ok "all images imported"

# Verify
step "verify" "Listing imported images in k3s"
if [[ -n "$REMOTE" ]]; then
  ssh "$REMOTE" "sudo k3s ctr images ls | grep observibelity | awk '{print \"  \", \$1}'"
else
  sudo k3s ctr images ls | grep observibelity | awk '{print "  ", $1}'
fi
ok "done. Run: make dev IMAGE_PULL_POLICY=IfNotPresent"
