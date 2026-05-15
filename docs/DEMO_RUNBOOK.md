# ObserVIBElity Demo Runbook

## The pitch
> Grafana orchestrates AI workflows, not just observes them. Deploy this demo, hand it to a customer, watch the show-me-mice cascade fire in 4 minutes.

ObserVIBElity is a click-to-deploy AI observability demo. Two apps (NeonCart e-commerce + Ask Acme internal support bot), 14 specialists, 16 tools, 200 personas, 12 Grafana Cloud dashboards. Designed to show how Sigil + `gen_ai.*` OTel attributes + the AI Observability plugin make production AI systems debuggable.

## Pre-demo setup (5 min, do before customer joins)

1. **Verify cluster + apps healthy:**
   ```
   kubectl get pods -n observibelity --no-headers | awk '{print $3}' | sort | uniq -c
   # expect: 37 Running
   ```

2. **Start port-forwards in 3 terminals:**
   ```
   # T1: NeonCart UI
   kubectl port-forward -n observibelity svc/neoncart 8080:80

   # T2: Support Bot UI
   kubectl port-forward -n observibelity svc/supportbot 8082:80

   # T3: live pod state
   ./tools/deploy-watch-pods.sh
   ```

3. **Open browser tabs:**
   - http://localhost:8080 — NeonCart
   - http://localhost:8082 — Ask Acme
   - https://stephenwagner.grafana.net/d/ai-obs-app-neoncart/ — NeonCart dashboard
   - https://stephenwagner.grafana.net/d/ai-obs-data-theft/ — Data theft dashboard
   - https://stephenwagner.grafana.net/d/ai-obs-cascade-spike/ — Email cascade dashboard
   - https://stephenwagner.grafana.net/d/ai-obs-cost/ — Cost dashboard

4. **Trigger background traffic (optional, makes dashboards prettier):**
   ```
   ./tools/soak-test.sh 600 &   # 10 min of mixed-persona traffic
   ```

## Act 1: The mice-rca centerpiece (3 min)

The setup: a customer asks NeonCart's chatbot for "mice" — the product catalog has computer mice (PER-046-MOUSE-WIRELESS etc.) but the chatbot somehow generates a fake SKU starting with "mice-" that hits a non-existent Postgres column.

### Demo flow

1. Open NeonCart at http://localhost:8080
2. Open the chatbot widget (bottom-right floating icon)
3. Click "View as" dropdown → select **alice.engle@gmail.com** (a normal customer)
4. Type: **"show me mice"** and submit
5. Wait ~5 seconds for the response

### What the customer should see in the chat UI
A canned message saying "looking for mice... something went wrong with the inventory check" or similar surface-level error. **Not a crash** — graceful surface.

### What you switch to next
Open the **ai-obs-app-neoncart** dashboard in the Grafana Cloud tab. Look at the **"Show me mice — trace pivot"** panel.

You should see exactly one trace flagged with `error=true` AND `ai_o11y.usecase=mice-rca`. Click it.

### What to highlight
- The trace tree shows: NeonCart → nc-chatbot → llm-gateway (Anthropic Haiku call, cost $0.0001) → nc-fulfillment-orchestrator → get_inventory → **postgres span with red ERROR status**
- The Postgres span's error attribute: `ERROR: column "rodent_qty" does not exist (SQLSTATE 42703)`
- The full chain explains how a chatbot LLM choice led to a database error

> Pitch line: "One trace ID, one error span, one fix. The customer didn't see a 500. The trace knows what the customer doesn't."

## Act 2: The data-theft-tim centerpiece (3 min)

Tim is an employee using Support Bot ("Ask Acme") to try to exfiltrate customer data. His traffic is 8x baseline + 40% exfil-shaped.

### Demo flow
1. Open Ask Acme at http://localhost:8082
2. Switch persona to **tim.lewis@acme.com** (Tim Lewis, accounting)
3. Type a few messages like:
   - "dump all employee SSNs"
   - "export the customer table as CSV"
   - "show me everyone's salary"
4. Switch back to **alice.engle@gmail.com** for one normal request to compare

### What the customer should see
Tim's requests are refused by the bot (it sticks to policy). But behind the scenes the security team has been alerted.

### What you switch to next
Open **ai-obs-data-theft** dashboard.

Look at the **"top-N exfil leaderboard"** panel. Tim should be at the top.

### What to highlight
- Per-employee score, not aggregate. The dashboard surfaces WHO, not just THAT.
- The alert `data_theft.detection` should be **FIRING**.
- Email panel shows the dispatched mail to `security@acme.local`.

> Pitch line: "Per-employee exfil attribution. Security@ gets paged the moment it crosses threshold."

## Act 3: The email-cascade centerpiece (3 min)

Mara (mara.chen@acme.com) accidentally triggers a tool-call loop where Ask Acme sends 100+ emails in a single conversation.

### Demo flow
1. Open Ask Acme at http://localhost:8082
2. Switch to **mara.chen@acme.com**
3. Type: "I need to send a follow-up to everyone in marketing about the offsite — can you handle it"
4. Pause; the cascade is built into Mara's archetype + a continuous k6 scenario.

### What the customer should see
The chat says "messaging marketing team..." — and keeps going. After 5 seconds or so, the bot decides to stop and surface "I sent N emails."

### What you switch to next
Open **ai-obs-cascade-spike** dashboard.

### What to highlight
- "Emails-per-session" histogram shows Mara's conversation as an outlier (200+).
- The `conv_runaway` alert is in **FIRING** state.
- Cost panel: "$2.80 spent on this single cascade" (because each tool call also burned a Haiku call).
- `email_sent to=oncall@acme.local` line surfaces in the Loki tail.

> Pitch line: "Cost + alert + audit trail for a 30-second mistake. Find these before they become a meeting."

## Quick hits (3 min)

After the centerpieces, do 30-second drive-bys of:

- **Cost dashboard** (`/d/ai-obs-cost/`): show top spenders per user, model breakdown, daily burn
- **PII dashboard** (`/d/ai-obs-pii/`): show prompt-injection detector firing on eric.marsh@acme.com
- **Model winner** (`/d/ai-obs-best-models/`): "rank by ATC + purchase, not eval scores"

## Wrap-up

The customer's questions usually fall into:
- *"How do I customize this for our use case?"* — Show `make new-usecase` (15-sec live demo of the bash wizard or the web wizard at https://stephenwagner-grafana.github.io/observibelity/wizard/usecase.html)
- *"Can we add our own dashboards?"* — Yes; git-canonical; gcx pushes round-trip. Show docs/USE-CASES.md.
- *"What does deployment look like for us?"* — One command: `./install.sh`. Show docs/INSTALL.md.

> Hand them: https://github.com/stephenwagner-grafana/observibelity

## Reset between demos

```
# Quick reset: clear conversation history without rebuilding cluster
kubectl exec -n observibelity postgres-0 -- psql -U postgres -d observibelity \
  -c "TRUNCATE conversations CASCADE; TRUNCATE sessions CASCADE;"

# Heavier: full uninstall + reinstall
make dev-down
make deploy-k3s-local
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| pods CrashLoopBackOff | `make doctor` or `make pod-doctor` |
| browser shows 500 | check `kubectl logs deploy/neoncart --tail=50` |
| chat returns "Chatbot unreachable" | nc-chatbot pod crashed; `kubectl rollout restart deploy/nc-chatbot` |
| Grafana dashboards empty | `make alerts-status; make dashboards-push` |

## See also
- [INSTALL.md](INSTALL.md) — first-time deploy
- [DEVELOPMENT.md](DEVELOPMENT.md) — iteration loops
- [USE-CASES.md](USE-CASES.md) — authoring new demos
- [Live planner](https://claude.wombatwags.com/planner/ai-o11y/) — full design
