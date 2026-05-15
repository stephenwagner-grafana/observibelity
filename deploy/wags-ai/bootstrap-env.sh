#!/usr/bin/env bash
# bootstrap-env.sh — create /etc/default/alloy from the k3s Grafana Cloud secret.
# Run this once on .240 before install.sh. Requires kubectl with access to the
# cluster running ObserVIBElity (or run from your laptop and scp the output).
#
# Usage:
#   sudo ./bootstrap-env.sh                              # uses default ns/secret
#   sudo NS=observibelity SECRET=otel-grafanacloud-creds ./bootstrap-env.sh

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "must run as root (use sudo)"; exit 1
fi

NS="${NS:-observibelity}"
SECRET="${SECRET:-otel-grafanacloud-creds}"

if ! command -v kubectl >/dev/null; then
  echo "kubectl not found. Either install kubectl or hand-create /etc/default/alloy"
  echo "from etc-default-alloy.env.example."
  exit 1
fi

echo "→ fetching ${NS}/${SECRET}"
OTLP_URL=$(kubectl get secret -n "${NS}" "${SECRET}" -o jsonpath='{.data.GRAFANA_CLOUD_OTLP_ENDPOINT}' | base64 -d)
OTLP_ID=$(kubectl  get secret -n "${NS}" "${SECRET}" -o jsonpath='{.data.GRAFANA_CLOUD_INSTANCE_ID}'   | base64 -d)
OTLP_TOK=$(kubectl get secret -n "${NS}" "${SECRET}" -o jsonpath='{.data.GRAFANA_CLOUD_API_TOKEN}'     | base64 -d)

if [ -z "${OTLP_URL}" ] || [ -z "${OTLP_TOK}" ]; then
  echo "secret didn't have the OTLP keys"; exit 1
fi

# Prom + Loki integration tokens are *not* in the k3s secret — pulled from the
# /etc/alloy/config.alloy currently on disk if already configured, otherwise
# you'll need to supply them by env: GCLOUD_PROM_* and GCLOUD_LOKI_*
PROM_URL="${GCLOUD_PROM_URL:-}"
PROM_USER="${GCLOUD_PROM_USER:-}"
PROM_PASS="${GCLOUD_PROM_PASS:-}"
LOKI_URL="${GCLOUD_LOKI_URL:-}"
LOKI_USER="${GCLOUD_LOKI_USER:-}"
LOKI_PASS="${GCLOUD_LOKI_PASS:-}"

if [ -f /etc/default/alloy ]; then
  echo "→ preserving existing PROM/LOKI tokens from /etc/default/alloy if present"
  PROM_URL=${PROM_URL:-$(grep -oP '(?<=^GCLOUD_PROM_URL=").+(?="$)' /etc/default/alloy || true)}
  PROM_USER=${PROM_USER:-$(grep -oP '(?<=^GCLOUD_PROM_USER=").+(?="$)' /etc/default/alloy || true)}
  PROM_PASS=${PROM_PASS:-$(grep -oP '(?<=^GCLOUD_PROM_PASS=").+(?="$)' /etc/default/alloy || true)}
  LOKI_URL=${LOKI_URL:-$(grep -oP '(?<=^GCLOUD_LOKI_URL=").+(?="$)' /etc/default/alloy || true)}
  LOKI_USER=${LOKI_USER:-$(grep -oP '(?<=^GCLOUD_LOKI_USER=").+(?="$)' /etc/default/alloy || true)}
  LOKI_PASS=${LOKI_PASS:-$(grep -oP '(?<=^GCLOUD_LOKI_PASS=").+(?="$)' /etc/default/alloy || true)}
fi

if [ -z "${PROM_URL}" ] || [ -z "${LOKI_URL}" ]; then
  echo "ERROR: missing Prom/Loki integration tokens. Set GCLOUD_PROM_* and GCLOUD_LOKI_*"
  echo "       env vars and re-run, or copy from cluster k8s integration manifest."
  exit 1
fi

cat > /etc/default/alloy <<EOF
## Path:        /etc/default/alloy
## Managed by:  bootstrap-env.sh from observibelity/deploy/wags-ai/
##              Last bootstrapped: $(date -Is)

CONFIG_FILE="/etc/alloy/config.alloy"
CUSTOM_ARGS=""
RESTART_ON_UPGRADE=true

GCLOUD_PROM_URL="${PROM_URL}"
GCLOUD_PROM_USER="${PROM_USER}"
GCLOUD_PROM_PASS="${PROM_PASS}"

GCLOUD_LOKI_URL="${LOKI_URL}"
GCLOUD_LOKI_USER="${LOKI_USER}"
GCLOUD_LOKI_PASS="${LOKI_PASS}"

GCLOUD_OTLP_URL="${OTLP_URL}"
GCLOUD_OTLP_USER="${OTLP_ID}"
GCLOUD_OTLP_PASS="${OTLP_TOK}"
EOF
chmod 0640 /etc/default/alloy
chown root:alloy /etc/default/alloy
echo "→ wrote /etc/default/alloy"
