#!/usr/bin/env bash
# ollama-textfile.sh — poll Ollama's API and write metrics in Prometheus textfile format.
# Captures loaded-model state which is central to the AI-justifies-AI VRAM-thrash demo.
# Runs every 10s via ollama-textfile.timer.

set -euo pipefail

DEST_DIR="/var/lib/alloy/textfile"
DEST_FILE="${DEST_DIR}/ollama.prom"
TMP_FILE="${DEST_FILE}.$$"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"

mkdir -p "${DEST_DIR}"

now_epoch=$(date +%s)

{
  echo "# HELP ollama_collector_up 1 when Ollama API responded"
  echo "# TYPE ollama_collector_up gauge"

  if ! VER=$(curl -sS -m 3 "${OLLAMA_URL}/api/version" 2>/dev/null); then
    echo "ollama_collector_up 0"
    exit 0
  fi
  echo "ollama_collector_up 1"

  version=$(echo "${VER}" | jq -r '.version // "unknown"')
  echo "# HELP ollama_build_info Ollama build/version info"
  echo "# TYPE ollama_build_info gauge"
  echo "ollama_build_info{version=\"${version}\"} 1"

  # /api/ps — currently loaded models (the key signal for VRAM thrash)
  echo "# HELP ollama_loaded_models Number of models currently loaded in VRAM"
  echo "# TYPE ollama_loaded_models gauge"
  echo "# HELP ollama_loaded_model_size_bytes Size of a loaded model in VRAM"
  echo "# TYPE ollama_loaded_model_size_bytes gauge"
  echo "# HELP ollama_loaded_model_size_vram_bytes Portion of model resident in VRAM"
  echo "# TYPE ollama_loaded_model_size_vram_bytes gauge"
  echo "# HELP ollama_loaded_model_expires_seconds Seconds until idle eviction"
  echo "# TYPE ollama_loaded_model_expires_seconds gauge"
  echo "# HELP ollama_loaded_model_info Static labels for a loaded model"
  echo "# TYPE ollama_loaded_model_info gauge"

  if PS=$(curl -sS -m 3 "${OLLAMA_URL}/api/ps" 2>/dev/null); then
    count=$(echo "${PS}" | jq '.models | length')
    echo "ollama_loaded_models ${count}"

    # jq can't parse Ollama's "-04:00" tz offset via fromdateiso8601; emit raw
    # expires_at and compute remaining seconds in bash via `date -d`.
    echo "${PS}" | jq -r '
      .models[]? |
      [.name,
       (.digest // "")[0:12],
       (.details.family // "unknown"),
       (.details.parameter_size // "unknown"),
       (.details.quantization_level // "unknown"),
       (.size // 0),
       (.size_vram // 0),
       (.expires_at // "")
      ] | @tsv
    ' | while IFS=$'\t' read -r name digest family psize quant size vram expires_at; do
        if [ -n "${expires_at}" ]; then
          exp_epoch=$(date -d "${expires_at}" +%s 2>/dev/null || echo "0")
          remaining=$(( exp_epoch - now_epoch ))
        else
          remaining=0
        fi
        L="model=\"${name}\",digest=\"${digest}\",family=\"${family}\",parameter_size=\"${psize}\",quantization=\"${quant}\""
        echo "ollama_loaded_model_info{${L}} 1"
        echo "ollama_loaded_model_size_bytes{model=\"${name}\"} ${size}"
        echo "ollama_loaded_model_size_vram_bytes{model=\"${name}\"} ${vram}"
        echo "ollama_loaded_model_expires_seconds{model=\"${name}\"} ${remaining}"
      done
  else
    echo "ollama_loaded_models 0"
  fi

  # /api/tags — every model installed on disk
  echo "# HELP ollama_installed_model_info Static info for an installed model"
  echo "# TYPE ollama_installed_model_info gauge"
  echo "# HELP ollama_installed_model_size_bytes Disk size of an installed model"
  echo "# TYPE ollama_installed_model_size_bytes gauge"
  echo "# HELP ollama_installed_models Total models installed on this host"
  echo "# TYPE ollama_installed_models gauge"

  if TAGS=$(curl -sS -m 5 "${OLLAMA_URL}/api/tags" 2>/dev/null); then
    total=$(echo "${TAGS}" | jq '.models | length')
    echo "ollama_installed_models ${total}"
    echo "${TAGS}" | jq -r '
      .models[]? |
      [.name,
       (.digest // "")[0:12],
       (.details.family // "unknown"),
       (.details.parameter_size // "unknown"),
       (.details.quantization_level // "unknown"),
       (.size // 0)
      ] | @tsv
    ' | while IFS=$'\t' read -r name digest family psize quant size; do
        L="model=\"${name}\",digest=\"${digest}\",family=\"${family}\",parameter_size=\"${psize}\",quantization=\"${quant}\""
        echo "ollama_installed_model_info{${L}} 1"
        echo "ollama_installed_model_size_bytes{model=\"${name}\"} ${size}"
      done
  fi
} > "${TMP_FILE}"

mv -f "${TMP_FILE}" "${DEST_FILE}"
