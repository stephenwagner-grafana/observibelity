#!/usr/bin/env bash
# nvidia-textfile.sh — write NVIDIA GPU metrics in Prometheus textfile format.
# Picked up by Alloy's prometheus.exporter.unix textfile collector.
# Runs every 10s via nvidia-textfile.timer.

set -euo pipefail

DEST_DIR="/var/lib/alloy/textfile"
DEST_FILE="${DEST_DIR}/nvidia.prom"
TMP_FILE="${DEST_FILE}.$$"

mkdir -p "${DEST_DIR}"

# Single nvidia-smi call (cheaper than many) → CSV → Prom lines.
# Columns chosen to cover the VRAM-thrash demo + general GPU health.
QUERY="index,uuid,name,driver_version,pstate,\
utilization.gpu,utilization.memory,utilization.encoder,utilization.decoder,\
memory.total,memory.used,memory.free,\
temperature.gpu,temperature.memory,\
power.draw,power.limit,enforced.power.limit,\
clocks.current.graphics,clocks.current.memory,clocks.current.sm,\
fan.speed,pcie.link.gen.current,pcie.link.width.current,\
encoder.stats.sessionCount,encoder.stats.averageFps,\
ecc.errors.uncorrected.volatile.total"

{
  echo "# HELP nvidia_smi_collector_up 1 when nvidia-smi succeeded"
  echo "# TYPE nvidia_smi_collector_up gauge"

  if ! OUT=$(nvidia-smi --query-gpu="${QUERY}" --format=csv,noheader,nounits 2>/dev/null); then
    echo "nvidia_smi_collector_up 0"
    exit 0
  fi
  echo "nvidia_smi_collector_up 1"

  # Per-GPU rows
  # n2n: emit metric only when value is a number (handles "N/A" / "[Not Supported]")
  n2n() { case "$1" in ''|*[!0-9.-]*) return 1 ;; *) printf '%s' "$1" ;; esac; }

  while IFS=',' read -r idx uuid name driver pstate \
      util_gpu util_mem util_enc util_dec \
      mem_total mem_used mem_free \
      temp_gpu temp_mem \
      power_draw power_limit power_enforced \
      clk_graphics clk_memory clk_sm \
      fan_speed pcie_gen pcie_width \
      enc_sessions enc_avg_fps \
      ecc_uncorr_vol; do
    # trim whitespace from each field
    for var in idx uuid name driver pstate util_gpu util_mem util_enc util_dec \
               mem_total mem_used mem_free temp_gpu temp_mem \
               power_draw power_limit power_enforced \
               clk_graphics clk_memory clk_sm fan_speed pcie_gen pcie_width \
               enc_sessions enc_avg_fps ecc_uncorr_vol; do
      eval "$var=\"\${$var## }\""
      eval "$var=\"\${$var%% }\""
    done
    L="gpu=\"${idx}\",uuid=\"${uuid}\",name=\"${name// /_}\""
    echo "nvidia_gpu_driver_info{${L},driver_version=\"${driver}\"} 1"
    v=$(n2n "${pstate//P/}") && echo "nvidia_gpu_pstate{${L}} $v"
    v=$(n2n "${util_gpu}") && echo "nvidia_gpu_utilization_gpu_ratio{${L}} $(awk -v v="$v" 'BEGIN{print v/100}')"
    v=$(n2n "${util_mem}") && echo "nvidia_gpu_utilization_memory_ratio{${L}} $(awk -v v="$v" 'BEGIN{print v/100}')"
    v=$(n2n "${util_enc}") && echo "nvidia_gpu_utilization_encoder_ratio{${L}} $(awk -v v="$v" 'BEGIN{print v/100}')"
    v=$(n2n "${util_dec}") && echo "nvidia_gpu_utilization_decoder_ratio{${L}} $(awk -v v="$v" 'BEGIN{print v/100}')"
    v=$(n2n "${mem_total}") && echo "nvidia_gpu_memory_total_bytes{${L}} $((v * 1048576))"
    v=$(n2n "${mem_used}")  && echo "nvidia_gpu_memory_used_bytes{${L}} $((v * 1048576))"
    v=$(n2n "${mem_free}")  && echo "nvidia_gpu_memory_free_bytes{${L}} $((v * 1048576))"
    v=$(n2n "${temp_gpu}")  && echo "nvidia_gpu_temperature_gpu_celsius{${L}} $v"
    v=$(n2n "${temp_mem}")  && echo "nvidia_gpu_temperature_memory_celsius{${L}} $v"
    v=$(n2n "${power_draw}") && echo "nvidia_gpu_power_draw_watts{${L}} $v"
    v=$(n2n "${power_limit}") && echo "nvidia_gpu_power_limit_watts{${L}} $v"
    v=$(n2n "${power_enforced}") && echo "nvidia_gpu_power_enforced_limit_watts{${L}} $v"
    v=$(n2n "${clk_graphics}") && echo "nvidia_gpu_clock_graphics_hz{${L}} $((v * 1000000))"
    v=$(n2n "${clk_memory}")   && echo "nvidia_gpu_clock_memory_hz{${L}} $((v * 1000000))"
    v=$(n2n "${clk_sm}")       && echo "nvidia_gpu_clock_sm_hz{${L}} $((v * 1000000))"
    v=$(n2n "${fan_speed}") && echo "nvidia_gpu_fan_speed_ratio{${L}} $(awk -v v="$v" 'BEGIN{print v/100}')"
    v=$(n2n "${pcie_gen}") && echo "nvidia_gpu_pcie_link_gen_current{${L}} $v"
    v=$(n2n "${pcie_width}") && echo "nvidia_gpu_pcie_link_width_current{${L}} $v"
    v=$(n2n "${enc_sessions}") && echo "nvidia_gpu_encoder_sessions{${L}} $v"
    v=$(n2n "${enc_avg_fps}") && echo "nvidia_gpu_encoder_average_fps{${L}} $v"
    v=$(n2n "${ecc_uncorr_vol}") && echo "nvidia_gpu_ecc_errors_uncorrected_volatile_total{${L}} $v"
  done <<< "${OUT}"

  # Per-process GPU usage (key for AI-justifies-AI demo: shows ollama owning all VRAM)
  echo "# HELP nvidia_gpu_process_used_memory_bytes Per-process GPU memory used"
  echo "# TYPE nvidia_gpu_process_used_memory_bytes gauge"
  if PROC=$(nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader,nounits 2>/dev/null); then
    while IFS=',' read -r uuid pid pname mem; do
      [ -z "${uuid// /}" ] && continue
      uuid="${uuid# }"; pname="${pname# }"; pid="${pid// /}"; mem="${mem// /}"
      echo "nvidia_gpu_process_used_memory_bytes{uuid=\"${uuid}\",pid=\"${pid}\",process_name=\"${pname// /_}\"} $((mem * 1048576))"
    done <<< "${PROC}"
  fi
} > "${TMP_FILE}"

mv -f "${TMP_FILE}" "${DEST_FILE}"
