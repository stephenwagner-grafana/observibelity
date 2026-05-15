"""Build 3 demo-focused dashboards: model matrix, finops, shift-left.

Each lives at /workspace/observibelity/dashboards/<uid>.json. Pinned to
the canonical grafanacloud-{prom,logs} datasources.
"""
import json
from pathlib import Path

DASHBOARDS = Path("/workspace/observibelity/dashboards")


def base_dashboard(uid: str, title: str, tags: list[str], panels: list[dict]) -> dict:
    return {
        "uid": uid,
        "title": title,
        "tags": tags,
        "schemaVersion": 39,
        "timezone": "browser",
        "refresh": "30s",
        "time": {"from": "now-1h", "to": "now"},
        "templating": {
            "list": [
                {
                    "name": "datasource_prom",
                    "label": "Prometheus",
                    "type": "datasource",
                    "query": "prometheus",
                    "current": {"selected": True, "text": "grafanacloud-stephenwagner-prom", "value": "grafanacloud-prom"},
                    "hide": 0, "includeAll": False, "multi": False, "options": [], "refresh": 1, "regex": "", "skipUrlSync": False,
                },
                {
                    "name": "datasource_loki",
                    "label": "Loki",
                    "type": "datasource",
                    "query": "loki",
                    "current": {"selected": True, "text": "grafanacloud-stephenwagner-logs", "value": "grafanacloud-logs"},
                    "hide": 0, "includeAll": False, "multi": False, "options": [], "refresh": 1, "regex": "", "skipUrlSync": False,
                },
            ],
        },
        "annotations": {"list": []},
        "panels": panels,
    }


def stat(id, title, x, y, w, h, expr, unit="short", desc="", decimals=2, color_mode="value"):
    return {
        "id": id, "type": "stat", "title": title, "description": desc,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": {"type": "prometheus", "uid": "${datasource_prom}"},
        "targets": [{"refId": "A", "datasource": {"type": "prometheus", "uid": "${datasource_prom}"}, "expr": expr, "instant": True}],
        "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals, "color": {"mode": "thresholds"}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": color_mode, "graphMode": "area", "textMode": "auto"},
    }


def timeseries(id, title, x, y, w, h, targets, unit="short", desc="", stack=False):
    return {
        "id": id, "type": "timeseries", "title": title, "description": desc,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": {"type": "prometheus", "uid": "${datasource_prom}"},
        "targets": [{"refId": chr(65+i), "datasource": {"type": "prometheus", "uid": "${datasource_prom}"}, **t} for i, t in enumerate(targets)],
        "fieldConfig": {"defaults": {"unit": unit, "color": {"mode": "palette-classic"}, "custom": {"fillOpacity": 30 if stack else 0, "stacking": {"mode": "normal"} if stack else {}}}, "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "right", "calcs": ["mean", "max", "lastNotNull"]}, "tooltip": {"mode": "multi", "sort": "desc"}},
    }


def table(id, title, x, y, w, h, expr, desc=""):
    return {
        "id": id, "type": "table", "title": title, "description": desc,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": {"type": "prometheus", "uid": "${datasource_prom}"},
        "targets": [{"refId": "A", "datasource": {"type": "prometheus", "uid": "${datasource_prom}"}, "expr": expr, "instant": True, "format": "table"}],
        "fieldConfig": {"defaults": {"custom": {"align": "auto"}}, "overrides": []},
        "options": {"showHeader": True},
        "transformations": [{"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True, "instance": True, "job": True, "service_name": True, "service_namespace": True, "deployment_environment": True}}}],
    }


def text(id, title, x, y, w, h, md):
    return {
        "id": id, "type": "text", "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "options": {"mode": "markdown", "content": md},
    }


def row(id, title, y, collapsed=False):
    return {
        "id": id, "type": "row", "title": title, "collapsed": collapsed,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
        "panels": [],
    }


# ----------------------------------------------------------------------
# Dashboard 1 — Model Matrix (which LLM fits which specialist)
# ----------------------------------------------------------------------
matrix_panels = [
    text(1, "", 0, 0, 24, 3,
         "# 🎯 Model Matrix — which LLM is best for each specialist\n\n"
         "Pairs every specialist (nc-chatbot, sb-router, nc-gift-finder, ...) against every model in the "
         "rotation to surface the **right model per job** by throughput, cost, and quality."),

    row(100, "📊 Throughput — output tokens/sec per (specialist × model)", 3),
    timeseries(2, "Output tokens/sec — by specialist × model",
        0, 4, 24, 10,
        [{"expr": "sum by (ai_o11y_specialist, gen_ai_response_model) (rate(gen_ai_client_token_usage_total{gen_ai_token_type=\"output\"}[5m]))", "legendFormat": "{{ai_o11y_specialist}} · {{gen_ai_response_model}}"}],
        "short", "Output token generation rate. Higher = more throughput on this specialist+model pair."),

    row(101, "💰 Cost per 1k calls by pair", 14),
    table(3, "Cost per 1k calls (USD) — by specialist × model",
        0, 15, 12, 10,
        "1000 * sum by (ai_o11y_specialist, gen_ai_response_model) (increase(gen_ai_client_cost_USD_total[1h])) / clamp_min(sum by (ai_o11y_specialist, gen_ai_response_model) (increase(gen_ai_client_token_usage_total{gen_ai_token_type=\"output\"}[1h]) / 60), 1)",
        "Lower is better. Computed from last 1h. Excludes pairs with no traffic."),
    table(4, "Avg output tokens per call — by specialist × model",
        12, 15, 12, 10,
        "sum by (ai_o11y_specialist, gen_ai_response_model) (increase(gen_ai_client_token_usage_total{gen_ai_token_type=\"output\"}[1h])) / clamp_min(sum by (ai_o11y_specialist, gen_ai_response_model) (increase(gen_ai_client_token_usage_total{gen_ai_token_type=\"input\"}[1h]) > 0) * 1, 1)",
        "How verbose each model is per specialist. Useful to spot models that ramble or are too terse."),

    row(102, "✅ Evaluator pass-rate by (specialist × model)", 25),
    table(5, "Eval pass rate — by specialist × model",
        0, 26, 12, 10,
        "sum by (gen_ai_agent_name, gen_ai_request_model) (rate(sigil_eval_executions_total{status=\"success\"}[1h])) / clamp_min(sum by (gen_ai_agent_name, gen_ai_request_model) (rate(sigil_eval_executions_total[1h])), 0.001)",
        "Fraction of LLM-judge evaluations that passed for each pair. Combine with throughput + cost to pick a model."),
    table(6, "Eval runs per specialist + model (last 1h)",
        12, 26, 12, 10,
        "sum by (gen_ai_agent_name, gen_ai_request_model, evaluator) (increase(sigil_eval_executions_total[1h]))",
        "Volume of LLM-judge evaluations. Low counts = unreliable pass-rate."),
]
matrix = base_dashboard("ai-obs-model-matrix", "AI o11y — Model Matrix (which LLM fits which specialist)", ["ai-o11y", "models"], matrix_panels)
(DASHBOARDS / "ai-obs-model-matrix.json").write_text(json.dumps(matrix, indent=2))


# ----------------------------------------------------------------------
# Dashboard 2 — FinOps + 450× local headline
# ----------------------------------------------------------------------
# Avg Haiku cost per 1k tokens (430 in / 60 out)
# input 430 × $1/M + output 60 × $5/M = $0.00073 per call
# Per-Anthropic-call equivalent if everything moved to Haiku
finops_panels = [
    text(1, "", 0, 0, 24, 3,
         "# 💵 AI FinOps — total spend & the 450× local advantage\n\n"
         "Three spend channels: **Anthropic API** (real, Sigil-computed), **Bedrock eval judges** "
         "(Sigil), and **Ollama on the 5090** (GPU-amortized estimate + electricity). The headline "
         "panel surfaces what you'd be paying if every call rode Claude."),

    # Headline row
    stat(2, "💸 Today: Anthropic spend rate", 0, 3, 6, 5,
         "(sum(rate(gen_ai_client_cost_USD_total{gen_ai_response_model=~\"claude.*\"}[5m]))) * 86400",
         "currencyUSD", "Projected $/day at the current rate (5-min window)."),
    stat(3, "🤖 Today: Bedrock eval rate", 6, 3, 6, 5,
         "(sum(rate(sigil_eval_judge_tokens_total{direction=\"input\", provider=\"bedrock\"}[5m])) * 1.0 + sum(rate(sigil_eval_judge_tokens_total{direction=\"output\", provider=\"bedrock\"}[5m])) * 5.0) * 86400 / 1e6",
         "currencyUSD", "Projected $/day for Sigil's Bedrock LLM-judge calls."),
    stat(4, "⚡ Today: Ollama electricity (5090)", 12, 3, 6, 5,
         "0.3 * 24 * 0.15",
         "currencyUSD", "Whole desktop @ ~0.3 kW avg × 24h × $0.15/kWh = ~$1.08/day. Static estimate."),
    stat(5, "🏆 If we ran it ALL on Haiku", 18, 3, 6, 5,
         "(sum(rate(gen_ai_client_cost_USD_total{gen_ai_response_model=~\"claude.*\"}[5m])) + 0.00073 * sum(rate(gen_ai_client_token_usage_total{gen_ai_token_type=\"output\", gen_ai_system=\"ollama\"}[5m]) / 60)) * 86400",
         "currencyUSD", "Counterfactual: your current Anthropic spend PLUS the Ollama call volume priced at Haiku rates. Shows what local saves you."),

    row(100, "📈 Spend trend (last 6h)", 8),
    timeseries(6, "USD/hr by channel",
        0, 9, 24, 10,
        [
            {"expr": "sum(rate(gen_ai_client_cost_USD_total{gen_ai_response_model=~\"claude.*\"}[5m])) * 3600", "legendFormat": "Anthropic API"},
            {"expr": "(sum(rate(sigil_eval_judge_tokens_total{direction=\"input\", provider=\"bedrock\"}[5m])) * 1.0 + sum(rate(sigil_eval_judge_tokens_total{direction=\"output\", provider=\"bedrock\"}[5m])) * 5.0) * 3600 / 1e6", "legendFormat": "Bedrock evals"},
            {"expr": "sum(rate(gen_ai_client_cost_USD_total{gen_ai_response_model!~\"claude.*\"}[5m])) * 3600", "legendFormat": "Ollama (GPU amortized)"},
            {"expr": "vector(0.045)", "legendFormat": "Ollama electricity (5090 ~avg)"},
        ],
        "currencyUSD", "All three real spend channels + the estimated 5090 electricity baseline.", stack=True),

    row(101, "🎯 Top spenders right now", 19),
    table(7, "Top 10 spend per specialist (USD/hr)",
        0, 20, 12, 10,
        "topk(10, sum by (ai_o11y_specialist) (rate(gen_ai_client_cost_USD_total[5m])) * 3600)",
        "Which specialist is driving the bill."),
    table(8, "Top 10 spend per user (USD/hr)",
        12, 20, 12, 10,
        "topk(10, sum by (user_id) (rate(gen_ai_client_cost_USD_total[5m])) * 3600)",
        "Per-employee/-shopper attribution. Drill-down for finops conversations."),

    row(102, "🌱 The 450× local-vs-cloud comparison", 30),
    text(9, "",
        0, 31, 24, 6,
        "## Why running local on a 5090 is ~450× cheaper than Claude Haiku\n\n"
        "At current load (~7.6 ollama gens/sec, ~657k calls/day):\n\n"
        "| Backend | $/day at this volume | Per-call cost |\n"
        "|---|---|---|\n"
        "| **Ollama on RTX 5090** | **~$1.08** (whole desktop @ avg US kWh) | $0.0000016 |\n"
        "| Claude Haiku 4.5 | ~$480 | $0.00073 |\n"
        "| Claude Sonnet 4.6 | ~$2,400 | $0.00365 |\n"
        "| Claude Opus 4.7 | ~$36,000 | $0.0547 |\n\n"
        "The shift-left story lands here: **run dev/test/explore on local; reserve Claude for production paths where quality + freshness justify the cost.**\n\n"
        "5090 @ 575W TDP, currently ~295W during inference. 1 kWh of inference produces ~92,500 Haiku-equivalent generations."),
]
finops = base_dashboard("ai-obs-finops", "AI o11y — FinOps + 450× local win", ["ai-o11y", "cost", "finops"], finops_panels)
(DASHBOARDS / "ai-obs-finops.json").write_text(json.dumps(finops, indent=2))


# ----------------------------------------------------------------------
# Dashboard 3 — Shift-Left Demo Agenda
# ----------------------------------------------------------------------
shift_panels = [
    text(1, "", 0, 0, 24, 4,
         "# 🔄 Shift-Left — the demo agenda\n\n"
         "Production on the right (deterministic, monitored, Claude-quality). "
         "Dev/test on the left (stochastic, exploratory, local Ollama). "
         "Each row maps a use case to where it lives on that axis."),

    row(100, "🎯 PROD — deterministic, observable, automated RCA", 4),
    text(2, "Use case anchors (prod)",
        0, 5, 8, 8,
        "**🐭 mice-rca** — \"show me mice\" classic. NeonCart query → fan-out to specialists → "
        "OTel trace tells the whole story. **Start the demo here**: it's the deterministic, "
        "production-quality flow and the OTel stack reads like a debugger.\n\n"
        "**📨 email-cascade** — cascade pattern, easy to spot on the trace fan-out.\n\n"
        "**💰 cost-anomaly-per-user** — Priya's verbose pastes. Lights up the per-user cost panel."),
    timeseries(3, "Production traffic (claude-* models)", 8, 5, 16, 8,
        [{"expr": "sum by (gen_ai_response_model) (rate(gen_ai_client_token_usage_total{gen_ai_token_type=\"output\", gen_ai_response_model=~\"claude.*\"}[5m]))", "legendFormat": "{{gen_ai_response_model}}"}],
        "short", "Output tokens/sec for the Claude side of the bus. This is where prod-quality replies come from."),

    row(101, "🧪 DEV — stochastic, model-quality probing, AI FinOps", 13),
    text(4, "Use case anchors (dev/test)",
        0, 14, 8, 8,
        "**🎯 model-winner** — every Ollama model in the rotation gets the same gift-finder prompt. "
        "Quality vs cost head-to-head on the leaderboard.\n\n"
        "**📊 ai-quality-score / quality-trend** — eval judges over time.\n\n"
        "**🤖 hallucination-product-price** — does the model just make up prices?\n\n"
        "**🎨 brand-voice-drift** — tone integrity.\n\n"
        "**🔐 pii-echo / sensitive-data-leaks** — what gets through guardrails?"),
    timeseries(5, "Dev traffic (ollama rotation)", 8, 14, 16, 8,
        [{"expr": "sum by (gen_ai_response_model) (rate(gen_ai_client_token_usage_total{gen_ai_token_type=\"output\", gen_ai_system=\"ollama\"}[5m]))", "legendFormat": "{{gen_ai_response_model}}"}],
        "short", "Output tokens/sec across the 10 Ollama rotation slots. Each spike is a 5-min slot lighting up."),

    row(102, "📦 Use-case traffic right now", 22),
    timeseries(6, "Use case spend velocity (USD/hr)",
        0, 23, 24, 10,
        [{"expr": "sum by (ai_o11y_usecase) (rate(gen_ai_client_cost_USD_total[5m])) * 3600", "legendFormat": "{{ai_o11y_usecase}}"}],
        "currencyUSD", "Which use case is most expensive to run continuously. Use this to pick which ones survive into prod and which stay in the local-only dev tier.", stack=True),

    row(103, "🏁 Conversations per hour, by app", 33),
    timeseries(7, "Convos/hr — NeonCart vs SupportBot",
        0, 34, 24, 8,
        [
            {"expr": "sum(rate(gen_ai_client_token_usage_total{ai_o11y_specialist=~\"nc-.*\", gen_ai_token_type=\"output\"}[5m]) > 0) * 60", "legendFormat": "NeonCart specialists"},
            {"expr": "sum(rate(gen_ai_client_token_usage_total{ai_o11y_specialist=~\"sb-.*\", gen_ai_token_type=\"output\"}[5m]) > 0) * 60", "legendFormat": "SupportBot specialists"},
        ],
        "short", "Active specialist count × per-min = rough convos/hr per app."),
]
shift = base_dashboard("ai-obs-shift-left", "AI o11y — Shift-Left Demo Agenda", ["ai-o11y", "demo"], shift_panels)
(DASHBOARDS / "ai-obs-shift-left.json").write_text(json.dumps(shift, indent=2))


print("wrote 3 dashboards:")
for d in ("ai-obs-model-matrix", "ai-obs-finops", "ai-obs-shift-left"):
    p = DASHBOARDS / f"{d}.json"
    print(f"  {p} ({p.stat().st_size:,} bytes, {json.loads(p.read_text())['panels'].__len__()} panels)")
