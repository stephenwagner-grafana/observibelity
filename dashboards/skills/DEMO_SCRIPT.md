# AI O11y demo script — the spoken narration

The 7-minute spoken script for the AI o11y demo. Compile dashboards
from these beats, not the reverse. Read `NARRATIVE.md` first to
understand the framings this script enacts.

> **Status**: v0 scaffold — beats outlined, prose TBD. Tomorrow's
> primary task is to fill in the actual narration and lock the
> emotional arc.

---

## Conventions

- **Spoken lines** in plain prose. Stage directions in *italics*.
- **Dashboard cue** marks when to switch dashboards. Cue includes the
  uid + the specific panel that lands the beat.
- **Audience feel** marks what the audience should be feeling at that
  moment.
- Time budgets per act sum to ~7 min. Adjust as the script tightens.

---

## Act 1 — Intro / Sales framing  *(~60 s)*

**Open with**: the recursive thesis. State it cleanly and let it land.

> "Observability optimized our systems. Now observability is optimizing
> AI systems. And increasingly, AI is optimizing observability itself."

*Beat. Let the recursion register.*

**Then**: the new primitive.

> "Classical observability has three primitives: a metric datapoint,
> a log line, a span. AI observability needs a fourth: **a conversation**."

*Stage direction: gesture at a conversation bar chart on the landing
dashboard — even just for a half-second of preview.*

**Set up shift-left**:

> "Traditional o11y handled deterministic systems — code either ran or
> it didn't. AI is different. It's non-deterministic, it's subjective,
> the same input produces different outputs. The demo today is about
> moving that ambiguous behavior into measurable operational systems —
> shift-left for AI."

**Dashboard cue**: `ai-obs-app-landing` — the folder navigator with
the soft-palette ribbon. Establishes the visual signature.

**Audience feel**: scope. "These people have thought about this."

---

## Act 2 — Traditional OTel + RCA  *(~60 s)*

**Pitch**: "Here's the part that's already familiar."

> "Here's a perfectly ordinary k3s cluster running a perfectly ordinary
> e-commerce app. NeonCart. Customers add to cart, place orders. When
> something breaks, we use the standard tools."

*Show a deterministic failure. Walk the audience through one trace,
one log line, one metric panel. Make it boring on purpose.*

**Dashboard cue**: ObserVIBElity → Explore (traces) → Logs (LogQL)
→ Metrics. Standard Grafana experience, no AI yet.

**Audience feel**: comfort. The SRE nods.

**Bridge to Act 3**:

> "But now the application has an AI brain. The chatbot. Let's look
> at the same kind of failure — but from the AI's side."

---

## Act 3 — AI conversations as telemetry  *(~90 s)*

**The "huh, that's new" moment.** This is where the convo bar chart
or its equivalent earns its keep.

> "A conversation isn't a log entry. It's a semantic execution graph.
> One conversation has prompts, tools called, evals run, tokens
> consumed, model decisions made, traces emitted, user intent declared,
> and a business outcome attached."

*Click on a conversation. Show the whole graph: prompt → router →
gift-finder → tool calls → evaluator scores → cart-add event.*

> "Same shape as a trace, but the units are different. Tools, not
> spans. Evals, not error rates. Tokens, not bytes."

**Dashboard cue**: `ai-obs-app-neoncart` → click into a bar →
conversation drawer. The drill-down is the **first wow moment**.

**Audience feel**: surprise. "Oh, this is genuinely new."

---

## Act 4 — AI economics + operational impact  *(~90 s)*

**The CFO leans in.** Cost + impact in one breath.

> "Every conversation costs money. Tokens, model choice, retries.
> Multiply by traffic, and that's a P&L line. But it pays back too —
> conversations close carts, save tickets, deflect support calls.
> That's a P&L line on the other side."

*Show the model economics dashboard. Cost per 1M tokens by model.
Hover the convo to see its individual cost.*

> "And here's the moment the audience usually feels something."

*Switch to the outage-cost dashboard. Show the live revenue rate.*

> "This is what the engine made today. This is what it didn't make.
> When k3s flickered for 45 seconds at 2:14am, that orange bar is the
> dollars that didn't happen."

**Dashboard cue**: `ai-obs-outage-cost`. The missed-revenue bar chart
is the **second wow moment**. Sum to today: ~$900K missed.

**Audience feel**: visceral. The CFO has done this math in their head.

---

## Act 5 — AI optimizing observability  *(~75 s)*

**The recursive payoff.** This is the most ambitious act.

> "So far we've used observability to optimize the AI. Now watch what
> happens when we point AI at observability itself."

*Open Grafana Assistant with a vague prompt:*

> "**Why did revenue dip at 2:14 this morning?**"

*Assistant returns the answer with the supporting traces, the bar in
the chart highlighted, the runbook link surfaced.*

> "It looked at the conversations, found the ones that errored, traced
> them to the k3s NotReady event, correlated with the deploy, and gave
> us the answer."

**Dashboard cue**: `ai-obs-wags-ai` and Grafana Assistant integration.

**Audience feel**: future-state reveal. "We can do this *now*?"

---

## Act 6 — Executive payoff  *(~60 s)*

**Close on strategic positioning.**

> "AI is going to be in every product. The thing that turns those
> AI products from probabilistic and ambiguous into reliable and
> measurable is observability. The thing that makes observability
> reach across metrics, logs, traces, AND conversations is unified
> telemetry. The thing that already does that is Grafana."

*Beat.*

> "Observability is becoming the operating system for AI systems.
> Three primitives became four. Three loops will become five. We're
> here for that."

**Dashboard cue**: back to `ai-obs-app-landing`. Resolution.

**Audience feel**: closure + opportunity.

---

## Total budget: ~7 min ± 45 s

Adjust act 5 first if running long (it's the most malleable). Acts 3
and 4 are the wow moments — protect them.

---

## Hard rules for the script

1. **The thesis sentence is spoken verbatim in act 1.** Don't paraphrase.
2. **The conversation primitive is spoken verbatim** the first time it
   appears. After that, lean on it.
3. **Two wow moments**: convo drill-down (act 3) + missed-revenue (act 4).
   Both must land. If either gets cut, the demo is hollow.
4. **One AI-optimizing-observability moment** (act 5). The recursive
   payoff. If it doesn't work live, have a fallback recording.
5. **Time the dashboard switches** — every switch is friction. Aim for
   ≤ 4 dashboard switches across the whole 7 min.

---

## Open questions for tomorrow

- [ ] Which existing dashboards survive vs. need rebuild vs. retire?
- [ ] What's the precise opening line of act 1? (the recursive thesis
      needs to land in *under 4 seconds*)
- [ ] What's the fallback if Grafana Assistant misfires in act 5?
- [ ] Where does shift-left appear visually? — needs a single recurring
      motif across dashboards.
- [ ] Should there be a 30-second "intermission" beat between acts 3
      and 4 to let the convo primitive settle before introducing $?
