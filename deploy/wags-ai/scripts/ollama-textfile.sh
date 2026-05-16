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

  # /api/show — capabilities + architecture details Sigil/Vercel SDK never see.
  # Cheap call (~5ms each) but we cache per-model in a state file to skip cold models.
  echo "# HELP ollama_model_capability 1 when this loaded model advertises the capability"
  echo "# TYPE ollama_model_capability gauge"
  echo "# HELP ollama_model_context_length Maximum context length supported by the model"
  echo "# TYPE ollama_model_context_length gauge"
  echo "# HELP ollama_model_embedding_length Hidden / embedding dimensionality"
  echo "# TYPE ollama_model_embedding_length gauge"
  echo "# HELP ollama_model_block_count Transformer block / layer count"
  echo "# TYPE ollama_model_block_count gauge"
  echo "# HELP ollama_model_attention_head_count Self-attention head count"
  echo "# TYPE ollama_model_attention_head_count gauge"
  echo "# HELP ollama_model_attention_head_count_kv KV-attention head count (GQA group size for KV)"
  echo "# TYPE ollama_model_attention_head_count_kv gauge"
  echo "# HELP ollama_model_parameter_count Reported parameter count from model_info"
  echo "# TYPE ollama_model_parameter_count gauge"
  echo "# HELP ollama_model_vocab_size Tokenizer vocabulary size"
  echo "# TYPE ollama_model_vocab_size gauge"
  echo "# HELP ollama_model_has_system_prompt 1 if a system prompt is baked into the modelfile"
  echo "# TYPE ollama_model_has_system_prompt gauge"
  echo "# HELP ollama_model_has_template 1 if the modelfile sets a chat template"
  echo "# TYPE ollama_model_has_template gauge"

  if [ -n "${PS}" ]; then
    echo "${PS}" | jq -r '.models[]?.name' | while read -r mname; do
      [ -z "${mname}" ] && continue
      SHOW=$(curl -sS -m 3 -X POST "${OLLAMA_URL}/api/show" -d "{\"name\":\"${mname}\"}" 2>/dev/null) || continue
      # Capabilities (array of strings)
      echo "${SHOW}" | jq -r --arg m "${mname}" '
        (.capabilities // [])[] | "ollama_model_capability{model=\"" + $m + "\",capability=\"" + . + "\"} 1"
      '
      # Architecture-dependent keys (llama.*, qwen2.*, gemma2.*, phi3.*, ...)
      echo "${SHOW}" | jq -r --arg m "${mname}" '
        (.model_info // {}) as $mi |
        ($mi | keys[] | select(test("\\.context_length$"))) as $k | $k | select(. != null) |
        "ollama_model_context_length{model=\"" + $m + "\"} \($mi[.])"
      '
      echo "${SHOW}" | jq -r --arg m "${mname}" '
        (.model_info // {}) as $mi |
        ($mi | keys[] | select(test("\\.embedding_length$"))) as $k | $k | select(. != null) |
        "ollama_model_embedding_length{model=\"" + $m + "\"} \($mi[.])"
      '
      echo "${SHOW}" | jq -r --arg m "${mname}" '
        (.model_info // {}) as $mi |
        ($mi | keys[] | select(test("\\.block_count$"))) as $k | $k | select(. != null) |
        "ollama_model_block_count{model=\"" + $m + "\"} \($mi[.])"
      '
      echo "${SHOW}" | jq -r --arg m "${mname}" '
        (.model_info // {}) as $mi |
        ($mi | keys[] | select(test("\\.attention\\.head_count$"))) as $k | $k | select(. != null) |
        "ollama_model_attention_head_count{model=\"" + $m + "\"} \($mi[.])"
      '
      echo "${SHOW}" | jq -r --arg m "${mname}" '
        (.model_info // {}) as $mi |
        ($mi | keys[] | select(test("\\.attention\\.head_count_kv$"))) as $k | $k | select(. != null) |
        "ollama_model_attention_head_count_kv{model=\"" + $m + "\"} \($mi[.])"
      '
      echo "${SHOW}" | jq -r --arg m "${mname}" '
        (.model_info // {}) as $mi |
        ($mi | keys[] | select(test("\\.vocab_size$"))) as $k | $k | select(. != null) |
        "ollama_model_vocab_size{model=\"" + $m + "\"} \($mi[.])"
      '
      # general.parameter_count from model_info is the real-deal count
      echo "${SHOW}" | jq -r --arg m "${mname}" '
        (.model_info // {})["general.parameter_count"] // empty |
        "ollama_model_parameter_count{model=\"" + $m + "\"} \(.)"
      '
      # System prompt / template presence (booleans → 0/1)
      hs=$(echo "${SHOW}" | jq -r '(.system // "") | length > 0 | if . then 1 else 0 end')
      ht=$(echo "${SHOW}" | jq -r '(.template // "") | length > 0 | if . then 1 else 0 end')
      echo "ollama_model_has_system_prompt{model=\"${mname}\"} ${hs}"
      echo "ollama_model_has_template{model=\"${mname}\"} ${ht}"
    done
  fi

  # Runner subprocess → model mapping. Lets per-process GPU memory chart
  # display model names instead of opaque PIDs.
  # The runner cmdline references the BLOB digest, but /api/ps returns the
  # MANIFEST digest. Bridge with the on-disk manifest files (one per model).
  echo "# HELP ollama_runner_info Maps an ollama runner subprocess PID to its model"
  echo "# TYPE ollama_runner_info gauge"

  MANIFEST_ROOT="${OLLAMA_MANIFEST_ROOT:-/usr/share/ollama/.ollama/models/manifests/registry.ollama.ai/library}"

  # Build blob_digest_prefix → "model:tag" lookup from manifests
  BLOB_MAP=""
  if [ -d "${MANIFEST_ROOT}" ]; then
    BLOB_MAP=$(
      find "${MANIFEST_ROOT}" -mindepth 2 -maxdepth 2 -type f 2>/dev/null | while read -r mf; do
        model=$(basename "$(dirname "${mf}")")
        tag=$(basename "${mf}")
        blob=$(jq -r '.layers[] | select(.mediaType == "application/vnd.ollama.image.model") | .digest' "${mf}" 2>/dev/null | head -1)
        blob="${blob#sha256:}"
        [ -z "${blob}" ] && continue
        printf '%s\t%s:%s\n' "${blob:0:12}" "${model}" "${tag}"
      done
    )
  fi

  for pid_dir in /proc/[0-9]*/; do
    pid=$(basename "${pid_dir}")
    cmdline=$(tr '\0' ' ' < "${pid_dir}cmdline" 2>/dev/null || continue)
    case "${cmdline}" in
      *"ollama runner --model"*)
        digest_full=$(echo "${cmdline}" | sed -n 's/.*sha256-\([0-9a-f]*\).*/\1/p')
        [ -z "${digest_full}" ] && continue
        digest_prefix="${digest_full:0:12}"
        model_name=$(echo "${BLOB_MAP}" | awk -v d="${digest_prefix}" -F'\t' '$1 == d { print $2; exit }')
        [ -z "${model_name}" ] && model_name="unknown"
        echo "ollama_runner_info{pid=\"${pid}\",model=\"${model_name}\",digest=\"${digest_prefix}\"} 1"
        ;;
    esac
  done

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
