# Using Claude Code with ObserVIBElity

This guide covers how to use Anthropic's Claude Code CLI with your ObserVIBElity deployment for diagnosis, vibe-editing, and live exploration of your AI observability stack.

You don't need Claude Code to use ObserVIBElity — `make dev`, `tools/deploy-doctor.sh`, and the dashboards in Grafana Cloud all work standalone. Claude Code adds a richer conversational layer on top.

## Quick start

```bash
# Install Claude Code
curl -fsSL https://claude.ai/install.sh | sh   # or `brew install claude-code`

# In the observibelity repo
cd /path/to/observibelity
claude

# Claude Code auto-discovers .claude/skills/ in the repo
```

## What you get out of the box

### The `diagnose-deploy` skill

Lives at `.claude/skills/diagnose-deploy/SKILL.md`. Triggers when you say "the deploy is broken", "pods aren't healthy", "observibelity isn't working", or similar.

What it does:
1. Runs `./tools/deploy-doctor.sh --collect-only` to bundle diagnostics
2. Reads kubectl events, helm status, pod logs, OTel collector logs
3. Cross-references the planner spec + docs/TROUBLESHOOTING.md
4. Returns: symptom + root cause + concrete fix commands + confidence rating
5. Never auto-applies destructive operations — always confirms first

### Vibe-editing (Phase 2)

ObserVIBElity will ship 6 skills in Phase 2 for fast iteration on the demo:

| skill | does |
|---|---|
| `build-app` | scaffold a new frontend app (`src/<app>/`, manifests, dashboards) |
| `build-use-case` | add a use case to an existing app (loadgen scenarios, judges, dashboards, alerts) |
| `add-use-case` | add evaluator + dashboard panels + alert + scenarios for a UC |
| `add-specialist` | scaffold a new specialist (`src/specialists/<name>/`) |
| `add-tool` | scaffold a new tool (`src/tools/<verb>_<noun>/`) |
| `add-evaluator` | add a Grafana Sigil evaluator spec |
| `add-scenario` | add a k6 traffic scenario |

These let you describe what you want in English, and Claude generates the code + manifests + tests for you.

## MCP servers — talk to your deployed stack

[Model Context Protocol (MCP)](https://modelcontextprotocol.io/) servers let Claude Code talk to your running infrastructure. Two are particularly useful with ObserVIBElity:

### Grafana MCP server

Lets Claude query your Grafana Cloud Mimir/Loki/Tempo/Pyroscope/Sigil directly.

Install via Claude Code's MCP config (`~/.claude/mcp.json` or repo-local `.mcp.json`):

```json
{
  "mcpServers": {
    "grafana": {
      "command": "uvx",
      "args": ["mcp-grafana"],
      "env": {
        "GRAFANA_URL": "https://your-stack.grafana.net",
        "GRAFANA_API_KEY": "${GRAFANA_API_KEY}"
      }
    }
  }
}
```

What you can now ask Claude:
- "Show me the last 100 traces from neoncart"
- "What's the p95 latency on the chat endpoint?"
- "Are there any Sigil generation events with PII flags from today?"
- "Compare error rates between yesterday and today"

The MCP server provides: dashboards, query_prometheus, query_loki_logs, get_traces, list_oncall_users, etc. See [grafana-mcp on GitHub](https://github.com/grafana/mcp-grafana).

### Kubernetes MCP server (optional)

Lets Claude run kubectl commands. For example: "Why is the neoncart pod not starting?"

```json
{
  "mcpServers": {
    "kubernetes": {
      "command": "uvx",
      "args": ["mcp-kubernetes"]
    }
  }
}
```

ObserVIBElity's diagnose-deploy skill primarily uses `Bash`-based kubectl commands, not MCP. But MCP is useful if you want Claude to do read-only cluster exploration without the skill's scaffolded prompts.

## Common workflows

### Diagnose a failing deploy

```bash
make dev
# ... pods stuck in CrashLoopBackOff ...
claude
# > the deploy is failing, pods are crashing
# (Claude triggers diagnose-deploy skill; reads tarball; suggests fix)
```

### Customize the demo for a specific industry

In Phase 2 (after vibe-edit skills land):

```
claude
# > rebrand neoncart to look like a luxury watch store called "TempusCarta",
#   change the catalog seed to 50 watches, update the chatbot persona to be
#   formal and concierge-like
# (Claude reads values.yaml, src/neoncart/, registry/personas.yaml, makes
#  changes, runs `make dev` to redeploy, verifies the chatbot output)
```

### Add a new use case

In Phase 2:

```
claude
# > i want a use case where the fraud detector returns false positives for
#   purchases over $500 from a specific persona. trigger it via a scenario
#   that places those orders. add evaluators that detect when fraud
#   classification disagrees with manual review.
# (Claude triggers add-use-case skill: writes evaluator specs, dashboard
#  panels, alert rule, k6 scenario, updates registry/use_cases.yaml)
```

### Explore live traffic

With Grafana MCP installed:

```
claude
# > show me the slowest 5 specialists in the last hour
# (Claude queries Tempo via MCP; returns table with p99 latencies; suggests
#  next steps if any look anomalous)
```

## Authoring your own skills

Skills live in `.claude/skills/<name>/SKILL.md`. The repo's skills are git-tracked, so your fork can add custom skills for your customer demos. Pattern:

```yaml
---
name: my-custom-skill
description: When to use this skill. Be specific so Claude triggers it appropriately.
allowed-tools: Read, Bash, Edit, Grep
---

# Skill body
What to do, in what order, with what guard rails.
```

See [Anthropic's skill docs](https://docs.claude.com/en/docs/agents-and-tools/skills) for the full spec.

## What Claude Code WON'T do

The diagnose-deploy skill is explicitly defensive:

- Never auto-applies `kubectl delete`, `helm uninstall`, `helm rollback`, `kubectl drain`
- Never reads or echoes raw API keys (`.env` content)
- Never pushes to remote git repos
- Never modifies `tests/snapshots/default.golden.yaml` to "make CI pass"
- Never bypasses preflight failures

You can override with explicit instructions ("yes, run kubectl delete pod neoncart-abc"), but the default is read-only investigation.

## Cost considerations

Claude Code calls the Claude API. Approximate costs per session:

- Diagnose-deploy on a small failure: ~$0.05 (Haiku) to ~$0.25 (Sonnet)
- A 20-minute vibe-edit session: ~$2-5 (Sonnet)
- An hour of MCP-driven exploration: ~$5-15

Set a budget alert at https://console.anthropic.com/settings/limits.

You can also use a local Ollama model with Claude Code (via the OpenAI-compatible endpoint shim), trading API costs for inference latency.

## Troubleshooting

- **Skill doesn't trigger:** check `.claude/skills/<name>/SKILL.md` exists, frontmatter is valid YAML, description matches what you said
- **MCP server fails:** check `~/.claude/mcp.json`, run `claude mcp list` to see configured servers + status
- **Claude won't run a kubectl command:** the `allowed-tools` field in SKILL.md may not include `Bash`. Check the frontmatter.

## See also
- [docs/DEVELOPMENT.md](DEVELOPMENT.md) — the 4-loop iteration design
- [Live planner § 13 Vibe-editing](https://claude.wombatwags.com/planner/ai-o11y/#vibe-editing)
- [`.claude/skills/diagnose-deploy/SKILL.md`](../.claude/skills/diagnose-deploy/SKILL.md) — the source of the included skill
- [Anthropic skill docs](https://docs.claude.com/en/docs/agents-and-tools/skills)
- [MCP spec](https://modelcontextprotocol.io/)
