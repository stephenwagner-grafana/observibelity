#!/usr/bin/env bash
# deploy-watch.sh — watch GHA image build, make ghcr packages public, redeploy.
#
# Usage:
#   ./tools/deploy-watch.sh                      # watch latest build-images run, redeploy when done
#   ./tools/deploy-watch.sh --no-redeploy        # watch only
#   ./tools/deploy-watch.sh --tag VERSION        # use specific tag instead of :latest

set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/logging.sh
source "$REPO_ROOT/tools/lib/logging.sh"

REPO="stephenwagner-grafana/observibelity"
NAMESPACE="${NAMESPACE:-observibelity}"
RELEASE="${RELEASE:-observibelity}"
TAG="latest"
REDEPLOY=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-redeploy) REDEPLOY=0; shift ;;
    --tag) TAG="$2"; shift 2 ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--no-redeploy] [--tag VERSION]

Watches the most recent build-images.yml run on $REPO, makes ghcr container
packages public as they appear, and (unless --no-redeploy) runs helm upgrade
once the build completes.

Env overrides:
  NAMESPACE   k8s namespace (default: observibelity)
  RELEASE     helm release name (default: observibelity)
EOF
      exit 0 ;;
    *) die "Unknown flag: $1" ;;
  esac
done

step "watch" "Watching GHA + ghcr for $REPO"

# Phase 1: identify the most-recent in-progress build-images run
RUN_ID=$(gh run list --repo "$REPO" --workflow=build-images.yml --limit 1 --json databaseId,status -q '.[0].databaseId')
if [[ -z "$RUN_ID" ]]; then
  warn "No build-images runs found; falling back to release.yml"
  RUN_ID=$(gh run list --repo "$REPO" --workflow=release.yml --limit 1 --json databaseId -q '.[0].databaseId')
fi
[[ -z "$RUN_ID" ]] && die "Could not find any workflow run to watch"
log "Watching run #$RUN_ID"

# Phase 2: poll until done
last_completed=0
while true; do
  status=$(gh run view "$RUN_ID" --repo "$REPO" --json status,conclusion -q '"\(.status) \(.conclusion // "")"')
  current_state="${status%% *}"

  # Count completed jobs
  completed_count=$(gh run view "$RUN_ID" --repo "$REPO" --json jobs -q '[.jobs[] | select(.status == "completed") | .name] | length')
  total_count=$(gh run view "$RUN_ID" --repo "$REPO" --json jobs -q '.jobs | length')

  if [[ "$completed_count" -ne "$last_completed" ]]; then
    log "Build progress: $completed_count / $total_count jobs done"
    last_completed=$completed_count
    # Make any new ghcr packages public
    for pkg in $(gh api /users/stephenwagner-grafana/packages?package_type=container --paginate 2>/dev/null \
                  | jq -r '.[] | select((.name | startswith("observibelity")) and (.visibility != "public")) | .name'); do
      log "  -> making $pkg public"
      gh api -X PATCH "/user/packages/container/${pkg}" -f visibility=public >/dev/null 2>&1 \
        || warn "    failed for $pkg"
    done
  fi

  if [[ "$current_state" == "completed" ]]; then
    conclusion=$(gh run view "$RUN_ID" --repo "$REPO" --json conclusion -q .conclusion)
    if [[ "$conclusion" == "success" ]]; then
      ok "Build succeeded"
      break
    else
      err "Build failed (conclusion: $conclusion)"
      err "Inspect: gh run view $RUN_ID --repo $REPO"
      exit 1
    fi
  fi

  sleep 15
done

# Phase 3: redeploy
if [[ "$REDEPLOY" -eq 1 ]]; then
  step "redeploy" "Helm upgrade with image tag :$TAG"

  # Pull the latest images on every node (avoid stale :latest)
  log "Forcing image refresh on k3s nodes"
  for node in $(kubectl get nodes -o name); do
    log "  ${node#node/}"
    # k3s ctr can pull; alternative is to delete pods after upgrade
  done

  # Upgrade with imagePullPolicy: Always so it pulls the new :latest
  /tmp/bin/helm upgrade --install "$RELEASE" "$REPO_ROOT" \
    -f "$REPO_ROOT/values-deploy.yaml" \
    --namespace "$NAMESPACE" --create-namespace \
    --set global.imagePullPolicy=Always \
    --set imageTag="$TAG" \
    --timeout 15m --wait=false

  log "Waiting 30s for pods to roll..."
  sleep 30

  kubectl get pods -n "$NAMESPACE" -o wide
  ok "Deploy triggered. Watch with: kubectl get pods -n $NAMESPACE -w"
fi
