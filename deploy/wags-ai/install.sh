#!/usr/bin/env bash
# install.sh — deploy the full Alloy + GPU/Ollama textfile stack to wags-ai (.240).
# Idempotent. Run as a user with passwordless or interactive sudo.
#
# Usage on .240:
#   curl -sSL https://raw.githubusercontent.com/stephenwagner-grafana/observibelity/main/deploy/wags-ai/install.sh | sudo bash
# Or from a clone:
#   sudo ./deploy/wags-ai/install.sh

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "this script must run as root (use sudo)"; exit 1
fi

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "→ source dir: ${SRC_DIR}"

# --- 1. apt: alloy + jq + curl (already present, but be safe) ---
if ! command -v alloy >/dev/null; then
  echo "→ installing alloy from packages.grafana.com"
  mkdir -p /etc/apt/keyrings
  wget -qO - https://apt.grafana.com/gpg.key | gpg --dearmor > /etc/apt/keyrings/grafana.gpg
  echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" > /etc/apt/sources.list.d/grafana.list
  apt-get update
  apt-get install -y alloy
fi
apt-get install -y --no-install-recommends jq curl

# --- 2. textfile collector dir + scripts ---
install -d -o alloy -g alloy -m 0775 /var/lib/alloy/textfile
install -m 0755 "${SRC_DIR}/scripts/nvidia-textfile.sh" /usr/local/bin/nvidia-textfile.sh
install -m 0755 "${SRC_DIR}/scripts/ollama-textfile.sh" /usr/local/bin/ollama-textfile.sh

# --- 2b. retire any pre-existing legacy collectors (older Claude sessions) ---
for legacy in nvidia-metrics; do
  if systemctl list-unit-files | grep -q "^${legacy}.timer"; then
    echo "→ retiring legacy ${legacy}.timer"
    systemctl disable --now "${legacy}.timer" "${legacy}.service" 2>/dev/null || true
    rm -f "/etc/systemd/system/${legacy}.timer" "/etc/systemd/system/${legacy}.service" "/usr/local/bin/${legacy}.sh"
  fi
done
rm -f /var/lib/alloy/textfile/nvidia_gpu.prom /var/lib/alloy/textfile/nvidia_gpu.prom.tmp
# Orphan tmp files from earlier non-atomic versions of scripts
rm -f /var/lib/alloy/textfile/*.prom.[0-9]*

# --- 3. systemd timers + services ---
install -m 0644 "${SRC_DIR}/systemd/nvidia-textfile.service" /etc/systemd/system/nvidia-textfile.service
install -m 0644 "${SRC_DIR}/systemd/nvidia-textfile.timer"   /etc/systemd/system/nvidia-textfile.timer
install -m 0644 "${SRC_DIR}/systemd/ollama-textfile.service" /etc/systemd/system/ollama-textfile.service
install -m 0644 "${SRC_DIR}/systemd/ollama-textfile.timer"   /etc/systemd/system/ollama-textfile.timer

# --- 4. Alloy config + env ---
install -m 0644 "${SRC_DIR}/config.alloy" /etc/alloy/config.alloy

# /etc/default/alloy is NOT in this repo (contains Grafana Cloud tokens).
# It must already exist with GCLOUD_PROM_*, GCLOUD_LOKI_*, GCLOUD_OTLP_* set.
# See etc-default-alloy.env.example for the schema. Bootstrap with bootstrap-env.sh.
if ! grep -q "^GCLOUD_OTLP_USER=" /etc/default/alloy 2>/dev/null; then
  echo "ERROR: /etc/default/alloy is missing GCLOUD_* credentials."
  echo "       Run bootstrap-env.sh first, or hand-create from etc-default-alloy.env.example."
  exit 1
fi

# --- 5. enable + start ---
systemctl daemon-reload
systemctl enable --now nvidia-textfile.timer ollama-textfile.timer
# Restart Alloy to pick up new config + env
systemctl restart alloy.service

# --- 6. tail status ---
echo
echo "=== alloy.service ==="
systemctl --no-pager --lines=5 status alloy.service || true
echo
echo "=== nvidia-textfile.timer ==="
systemctl --no-pager --lines=3 status nvidia-textfile.timer || true
echo
echo "=== ollama-textfile.timer ==="
systemctl --no-pager --lines=3 status ollama-textfile.timer || true
echo
echo "=== first textfile output ==="
sleep 12
ls -la /var/lib/alloy/textfile/
echo "--- nvidia.prom (head) ---"
head -20 /var/lib/alloy/textfile/nvidia.prom 2>/dev/null || echo "(not yet)"
echo "--- ollama.prom (head) ---"
head -20 /var/lib/alloy/textfile/ollama.prom 2>/dev/null || echo "(not yet)"
