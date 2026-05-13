#!/usr/bin/env bash
# build-images.sh - build container images for Phase 1+.
# Phase 0: prints "no images to build yet"
# Phase 1+: builds each image declared in IMAGES array

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/tools/lib/logging.sh"

REGISTRY="${REGISTRY:-ghcr.io/stephenwagner-grafana}"
VERSION="${VERSION:-$(awk '/^version:/ {print $2; exit}' "$REPO_ROOT/Chart.yaml")}"
PLATFORM="${PLATFORM:-linux/amd64}"
PUSH=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push) PUSH=1; shift ;;
    --platform) PLATFORM="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --registry) REGISTRY="$2"; shift 2 ;;
    --filter) FILTER="$2"; shift 2 ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--push] [--platform PLAT] [--version VER] [--registry REG] [--filter REGEX]
Defaults: VERSION=$VERSION, PLATFORM=$PLATFORM, REGISTRY=$REGISTRY
EOF
      exit 0 ;;
    *) die "Unknown flag: $1" ;;
  esac
done

# Image manifest: name -> src/path/to/dir (or src/path/to/Dockerfile)
declare -a IMAGES=(
  "specialist-base:src/specialists/.Dockerfile.shared"
  "tool-base:src/tools/.Dockerfile.shared"
  "neoncart:src/neoncart"
  "llm-gateway:src/llm-gateway"
  "nc-chatbot:src/specialists/nc-chatbot"
  "nc-fraud-detector:src/specialists/nc-fraud-detector"
  "nc-fulfillment-orchestrator:src/specialists/nc-fulfillment-orchestrator"
  "search_products:src/tools/search_products"
  "get_product:src/tools/get_product"
  "get_order_history:src/tools/get_order_history"
  "geo_lookup:src/tools/geo_lookup"
  "get_inventory:src/tools/get_inventory"
  "place_order:src/tools/place_order"
)

# Phase 0 short-circuit
BUILDABLE=0
for entry in "${IMAGES[@]}"; do
  name="${entry%%:*}"
  path="${entry##*:}"
  if [[ -f "$REPO_ROOT/$path/Dockerfile" ]] || [[ -f "$REPO_ROOT/$path" ]]; then
    BUILDABLE=$((BUILDABLE+1))
  fi
done

if [[ "$BUILDABLE" -eq 0 ]]; then
  step "build-images" "Phase 0 stub"
  log "No Dockerfiles found yet."
  log "Phase 1 fills these in. Run again once Phase 1 lands."
  exit 0
fi

# Phase 1+ build loop
step "build-images" "Building $BUILDABLE images at $REGISTRY (v$VERSION)"

BUILT=0 SKIPPED=0 FAILED=0
for entry in "${IMAGES[@]}"; do
  name="${entry%%:*}"
  path="${entry##*:}"

  if [[ -n "${FILTER:-}" ]] && ! echo "$name" | grep -qE "$FILTER"; then
    continue
  fi

  dockerfile="$REPO_ROOT/$path"
  if [[ ! -f "$dockerfile" ]]; then
    dockerfile="$REPO_ROOT/$path/Dockerfile"
  fi
  context="$(dirname "$dockerfile")"

  if [[ ! -f "$dockerfile" ]]; then
    warn "skip $name: $dockerfile missing"
    SKIPPED=$((SKIPPED+1))
    continue
  fi

  tag="$REGISTRY/observibelity-$name:$VERSION"
  log "build $tag"

  buildx_args=(--platform "$PLATFORM" -t "$tag" -f "$dockerfile" "$context")
  if [[ "$PUSH" -eq 1 ]]; then
    buildx_args+=(--push)
  else
    buildx_args+=(--load)
  fi

  if docker buildx build "${buildx_args[@]}" 2>&1 | tee -a "$REPO_ROOT/.build.log"; then
    ok "$tag"
    BUILT=$((BUILT+1))
  else
    err "$tag failed"
    FAILED=$((FAILED+1))
  fi
done

log "Built: $BUILT . Skipped: $SKIPPED . Failed: $FAILED"
[[ "$FAILED" -eq 0 ]] || exit 1
