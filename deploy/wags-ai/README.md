# wags-ai (.240) — bare-metal OTel bundle

Grafana Alloy + textfile exporters for **192.168.2.240** (wags-ai, Ubuntu 24.04, RTX 5090, bare-metal Ollama).

Sends to the same Grafana Cloud stack (1372178) as the rest of ObserVIBElity.

## What ships

| Signal | Source | Where it lands |
|---|---|---|
| Linux host metrics | `prometheus.exporter.unix` (node_exporter) | Mimir (`job=integrations/linux-node`) |
| OTel host metrics | `otelcol.receiver.hostmetrics` (system.* semconv) | Mimir via OTLP |
| NVIDIA GPU metrics | `nvidia-smi` → textfile (10s) | Mimir (`nvidia_gpu_*`) |
| Per-process GPU mem | `nvidia-smi --query-compute-apps` → textfile | Mimir (`nvidia_gpu_process_used_memory_bytes`) |
| Ollama state | `/api/ps` + `/api/tags` → textfile (10s) | Mimir (`ollama_*`) |
| Ollama process | `prometheus.exporter.process` matcher=ollama | Mimir (`namedprocess_namegroup_*`) |
| Systemd unit states | `node_exporter` systemd collector | Mimir (`node_systemd_unit_state`) |
| Journal logs | `loki.source.journal` (all units) | Loki (`host=wags-ai`) |
| App OTLP | `otelcol.receiver.otlp` on `:4317` / `:4318` | Grafana Cloud OTLP gateway |

## Install

**First run** (one-time, fetches Grafana Cloud tokens from the k3s secret):
```bash
sudo ./deploy/wags-ai/bootstrap-env.sh
```

**Then** (idempotent — re-run after any change in this directory):
```bash
sudo ./deploy/wags-ai/install.sh
```

`/etc/default/alloy` contains Grafana Cloud tokens and is **not** in this repo. The bootstrap script reads them from the `observibelity/otel-grafanacloud-creds` k8s secret. See `etc-default-alloy.env.example` for the schema.

## Files

| Path | Installed to |
|---|---|
| `config.alloy` | `/etc/alloy/config.alloy` |
| `bootstrap-env.sh` | run once → `/etc/default/alloy` |
| `etc-default-alloy.env.example` | template, schema reference |
| `scripts/nvidia-textfile.sh` | `/usr/local/bin/nvidia-textfile.sh` |
| `scripts/ollama-textfile.sh` | `/usr/local/bin/ollama-textfile.sh` |
| `systemd/nvidia-textfile.{service,timer}` | `/etc/systemd/system/` |
| `systemd/ollama-textfile.{service,timer}` | `/etc/systemd/system/` |

## Querying in Grafana Cloud

Filter everything by `host="wags-ai"`. Useful starts:

```promql
# VRAM used (the AI-justifies-AI signal)
nvidia_gpu_memory_used_bytes{host="wags-ai"} / nvidia_gpu_memory_total_bytes{host="wags-ai"}

# Which model is currently loaded
ollama_loaded_model_size_vram_bytes{host="wags-ai"} > 0

# Model load/eviction events from journal
{host="wags-ai", unit="ollama.service"} |= "load model"
```

## Why the textfile detour (vs DCGM / a real exporter)

DCGM exporter targets data-center GPUs; the 5090 is a workstation card and a chunky binary is overkill. The textfile pattern adds ~30 lines of bash, costs ~50ms every 10s, and gives us every signal we need for the demo.

## Persistence rule (ObserVIBElity)

Anything that runs on .240 lives in this directory. Don't change `/etc/alloy/config.alloy` on the host without updating `deploy/wags-ai/config.alloy` and re-running `install.sh`.
