#!/usr/bin/env bash
# Phase 0 smoke test. Designed for CI (GitHub Actions).
# Creates an ephemeral k3d cluster, runs install.sh against it, and asserts
# Phase 0 deploy behaviors.
set -euo pipefail

CLUSTER="obs-test-$$"
trap "k3d cluster delete $CLUSTER >/dev/null 2>&1 || true" EXIT

k3d cluster create "$CLUSTER" --wait --port "8080:80@loadbalancer"
export KUBECONFIG="$(k3d kubeconfig write "$CLUSTER")"

cd /workspace/observibelity

# Phase 0 stub .env with fake credentials. Phase 1 will swap to real secrets.
cat > .env <<EOF
ANTHROPIC_API_KEY=sk-ant-test
GRAFANA_CLOUD_INSTANCE_ID=0
GRAFANA_CLOUD_API_TOKEN=glc-test
GRAFANA_CLOUD_OTLP_ENDPOINT=otlp-gateway-prod-us-east-0.grafana.net/otlp
GITHUB_TOKEN=ghp-test
PHASE=0
EOF

# In Phase 0 we expect preflight credential validation to fail (these are fake creds).
# The assertion: install.sh --auto preflight exits non-zero with a clear error.
if OBSERVIBELITY_NO_INSTALL=1 OBSERVIBELITY_NO_FORK=1 ./install.sh --auto preflight; then
    echo "ERROR: preflight should have failed with fake creds"
    exit 1
else
    echo "OK: preflight correctly rejected fake creds"
fi

# Deploy phase: skip preflight + wizard so we don't gate on credentials.
# The real `helm upgrade --install --atomic --wait` runs the Namespace +
# test-connection helm-test pod. No upstream creds needed for the helm op itself.
if ! OBSERVIBELITY_NO_INSTALL=1 OBSERVIBELITY_NO_FORK=1 \
     ./install.sh --auto --skip preflight --skip wizard deploy; then
    echo "ERROR: deploy should have succeeded"
    exit 1
fi
echo "OK: deploy succeeded"

# Assert helm release is in "deployed" status (replaces the old "scaffolding only" string check).
status=$(helm status observibelity -n observibelity -o json | jq -r '.info.status')
if [[ "$status" != "deployed" ]]; then
    echo "ERROR: expected helm status 'deployed', got '$status'"
    exit 1
fi
echo "OK: helm status=deployed"

# Verify phase should pass (verify_namespace passes; Phase 1 components are skipped).
if ! ./install.sh verify; then
    echo "ERROR: verify should have succeeded"
    exit 1
fi
echo "OK: verify passed"

# Optional: run `helm test` against the Phase 0 test-connection pod (just echoes + exits 0).
if ! helm test observibelity -n observibelity; then
    echo "ERROR: helm test should have passed (Phase 0 pod just echoes + exits 0)"
    exit 1
fi
echo "OK: helm test passed"

echo "Phase 0 smoke test passed"
