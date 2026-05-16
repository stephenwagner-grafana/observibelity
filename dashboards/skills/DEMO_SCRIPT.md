# AI O11y demo script — the spoken narration

The 7-minute spoken script for the AI o11y demo. Compile dashboards
from these beats, not the reverse. Read `NARRATIVE.md` first to
understand the framings this script enacts.

> **Status**: v1 — locked prose for every act, three wow moments
> identified, dashboard cues consolidated to **3 dashboards / 2
> switches**. Open questions tracked at the bottom.

> **Total budget**: 7 min ± 45 s. Acts 3 and 4 are protected (the wow
> moments). Tighten Act 5 first if running long.

---

## Conventions

- **Spoken lines** in plain prose. Stage directions in *italics*.
- **Dashboard cue** marks when to switch dashboards (or scroll within
  one). Cue includes the uid + the specific panel that lands the beat.
- **Audience feel** marks what the audience should be feeling at that
  moment.
- Time budgets per act sum to ~7 min.

---

## The four dashboard scenes (the whole demo runs on these)

The demo uses **three dashboards** plus the Grafana Assistant overlay.
Switches are visible friction; we keep them to **two**.

| Scene | Dashboard | Acts it serves | Switch from previous |
|---|---|---|---|
| 1 | `ai-obs-app-neoncart` | 1 (open) + 2 (OTel) + 3 (conversations) | — (start here) |
| 2 | `ai-obs-outage-cost`  | 4 (economics) + (briefly) 6 (close) | **Switch #1** |
| 3 | `ai-obs-wags-ai` + Grafana Assistant | 5 (recursive) | **Switch #2** |

Rationale: opening on `ai-obs-app-neoncart` means the audience sees the
ribbon + the conversation panels from the first second. The "classical
OTel" panels (top of the dashboard) and the "AI conversation" panels
(middle of the dashboard) live on the **same dashboard** — we *scroll*
between them, which dramatizes the reveal in Act 3 better than a switch
would.

---

## Act 1 — Intro / The hook  *(~60 s)*

**Open on `ai-obs-app-neoncart`** — the ribbon visible across the top,
the dashboard quiet, no narration yet. Two beats of silence.

> "Yesterday, this demo environment generated **7.6 million tokens** of
> AI inference. On Claude Sonnet, the same workload would have cost
> **one hundred and fourteen dollars**. Locally, on a single GPU sitting
> three meters from where I'm standing, it cost **two dollars and
> sixty-seven cents**. A 97.7% reduction."

*Beat. Let the number land.*

> "The only reason we know that — to the cent — is observability."

*Now the thesis. Spoken cleanly, no rush.*

> **"Observability optimized systems. Now observability is optimizing
> AI systems. And increasingly, AI is optimizing observability itself."**

*Beat. The recursion needs a moment to register.*

> "Classical observability has three primitives: a metric datapoint, a
> log line, a span. AI observability needs a fourth.
> **A conversation is the base unit of AI observability.**"

*Gesture at the conversation panels mid-dashboard. Don't dwell — just
plant the foreshadow.*

> "Traditional observability was built for deterministic systems —
> code either ran, or it didn't. AI is different. It's
> non-deterministic. It's subjective. The same input gives you a
> different output. **The job of AI observability is to turn that
> ambiguous behavior into measurable operational systems.** Shift-left
> for AI."

**Dashboard cue**: `ai-obs-app-neoncart` — ribbon visible, the
conversation bar chart peeking from below the fold. The 97.7% number is
not on screen — it's an *opening claim* the audience will see paid back
in Act 4.

**Audience feel**: scope + provocation. *"These numbers are real. This
isn't a slide deck."*

---

## Act 2 — Traditional OTel + RCA  *(~60 s)*

**Stay on `ai-obs-app-neoncart`**. Scroll to the **top** of the
dashboard — the SLO health row, the trace explorer, the alert table.

> "Before we talk about AI, let me show you the part that's familiar.
> NeonCart is a real e-commerce app. Real customers shopping right now,
> real carts being added, real failures when something breaks. And when
> something breaks — we use the tools you already know."

*One trace. One log line. One alert. Make it a triptych — three small
gestures, not a deep dive.*

> "Trace. Log. Metric. Pod state. Find the bad pod, find the bad line,
> ship the fix. This is what observability has done for fifteen years
> and it still works. Nothing on this screen would surprise an SRE."

*Beat.*

> "Now bolt an LLM into the same application — and we have. NeonCart's
> shopping assistant is a real chatbot, running on a real GPU,
> answering real customers. The moment you do that, the rules change.
> The failure modes get weirder. The unit of work stops being a
> request. **And the tools we just looked at — they can't see inside
> the conversation.**"

**Dashboard cue**: `ai-obs-app-neoncart` top row (`🏥 Health — is
NeonCart up and meeting SLOs?` + `🔍 Trace explorer`). Standard
Grafana. No AI yet.

**Audience feel**: comfort. The SRE in the room nods. *"Okay, fine,
I know this part."* Setting them up for the surprise.

---

## Act 3 — Conversations as telemetry  *(~90 s)*  ⭐ **WOW #1**

**Scroll down** on `ai-obs-app-neoncart` to the Specialists + Tool
calls + LLM gateway rows. The conversation panels.

> "Watch what happens when we treat conversations as first-class
> telemetry."

*Click on a single bar in `📦 Specialists`. The conversation drawer
opens.*

> "One bar. One conversation. **Inside that bar**: the user's prompt,
> the model that handled it, every tool the agent called, every
> evaluator that scored the output, the tokens consumed, the latency,
> the dollar cost, the trace ID, and the business outcome — in this
> case, a cart-add. That happened in real life, fourteen seconds ago,
> to a real shopper."

*Beat. Let them absorb the shape.*

> "Same anatomy as a trace, different units. Prompts, not HTTP
> requests. Tools, not function calls. Evaluators, not error codes.
> Tokens, not bytes. **A conversation is a semantic execution graph** —
> and once you treat it as a primitive, you can do everything you do
> with spans. Search them. Group them. Aggregate them. Alert on them."

*Scroll back to the bar chart, zoom out so the audience sees the
density.*

> "Every bar is a customer talking to an LLM right now. We didn't
> sample these. We didn't summarize them into log lines. We captured
> the conversation as a primitive — and we can query it like one."

**Dashboard cue**: `ai-obs-app-neoncart` middle rows — `📦 Specialists`
+ `🛠 Tool calls` + `🤖 LLM gateway`. The drawer opening on a single
conversation is the visual punchline.

**Audience feel**: surprise + recognition. *"Oh. This is genuinely
new. This is not just dashboards with the word 'AI' in the title."*
The first **wow moment**.

---

## Act 4 — AI economics + customer impact  *(~90 s)*  ⭐ **WOW #2**

**Switch to `ai-obs-outage-cost`.** (Dashboard switch #1 of 2.)

> "Every one of those conversations costs money. And every one of them
> either *makes* money or doesn't. So AI observability has to do
> something observability has never had to do before: put a dollar
> sign on intelligence itself."

*Gesture at the hero `💰 Revenue right now` — the big number.*

> "This is what NeonCart is making, right now, this second."

*Then the missed-revenue chart.*

> "And this — this orange bar at two fourteen this morning — is what
> NeonCart **didn't make**. A k3s node went NotReady for forty-five
> seconds. The chatbot kept trying. Carts couldn't close. **Forty-five
> seconds. Forty-seven thousand dollars.**"

*Beat. Let the number sit.*

> "That's not a unit test you could write. That's not a metric anyone
> would have thought to alert on. It's only visible because we put
> observability on the AI, and on the infrastructure, and on the
> customer journey, and joined them in real time."

*The callback. This is the moment Act 1 pays back.*

> "Remember the number I opened with? Two dollars and sixty-seven cents
> for the entire day of AI inference. The forty-seven thousand we lost
> in those forty-five seconds is **eighteen thousand times** what the
> AI itself cost to run. The economics of AI are not about what
> inference costs. They're about what observability prevents."

**Dashboard cue**: `ai-obs-outage-cost` — `💰 Revenue right now` (hero)
→ `📉 Missed revenue today` (the orange spike) → callback to the
opening number.

**Audience feel**: visceral. The CFO has done this math in their head
before. The second **wow moment**.

---

## Act 5 — AI optimizing observability  *(~75 s)*  ⭐ **WOW #3**

**Switch to `ai-obs-wags-ai`.** (Dashboard switch #2 of 2.) Open
Grafana Assistant in a side panel.

> "So far we've used observability to optimize the AI. Now watch what
> happens when you point AI *at* observability."

*Open the Assistant. Type a vague business question.*

> "**Why did revenue dip at two fourteen this morning?**"

*The Assistant works for 5–10 seconds. It returns: a paragraph of
explanation, the specific log line, the highlighted bar on the chart,
the linked trace, the related runbook.*

> "Notice what just happened. I asked a business question in plain
> English. The system reached into traces, logs, **and** conversations,
> correlated four signals across a two-minute window, and gave me an
> answer with citations."

*Beat.*

> "This isn't a chatbot pasted onto a dashboard. This is the
> observability surface *becoming* intelligent. Every signal we just
> looked at — every trace, every metric, every conversation — is now
> queryable in natural language."

*Now the meta-payoff. Scroll back to `ai-obs-app-neoncart` for two
seconds — just enough to show the convo bar chart.*

> "And here's the recursion: the conversation I just had with Grafana
> Assistant? **It's also a conversation.** Prompts. Tokens. Tool calls.
> A trace. It shows up on the same dashboard, in the same bar chart,
> as the customer conversations did. **The observability system
> observes itself.**"

**Dashboard cue**: `ai-obs-wags-ai` + Grafana Assistant overlay. The
**meta-conversation appearing in `ai-obs-app-neoncart`** is the **third
wow moment** — the visual proof that the recursive loop closes.

**Audience feel**: future-state + closure. *"They can do this now.
And it's measuring itself."*

**Fallback**: If Assistant misfires live, fall back to a pre-recorded
30-second clip + a single still showing the meta-conversation. The
recursive payoff (the meta-conversation) is the load-bearing beat —
the Assistant ask is the dramatization, but the *point* is the
recursion. Either path lands the point.

---

## Act 6 — Executive payoff  *(~60 s)*

**Hold on `ai-obs-app-neoncart`** (no switch — we're already there from
the Act 5 callback).

> "Three primitives became four. Metric, log, span — and now,
> conversation."

*Beat.*

> "AI is going into every product. The companies that ship it reliably
> will be the ones who can see inside it — who can put numbers on
> subjective behavior, dollars on probabilistic decisions, and
> engineering rigor on systems that, by definition, aren't
> deterministic. **Observability is becoming the control plane for AI
> systems.** Unified telemetry — metrics, logs, traces, and now
> conversations — is the precondition for that to work. That's what
> Grafana is."

*Final beat.*

> "Three loops. Observability made systems healthier. Then it made AI
> healthier. Now it's making itself smarter. We're here for what comes
> next."

**Dashboard cue**: `ai-obs-app-neoncart` — the same screen we opened
on. The visual return-to-start reinforces the closure.

**Audience feel**: closure + opportunity. *"This is where the industry
is going."* Hand-off to Q&A.

---

## Time budget summary

| Act | Budget | Wow? | Dashboard |
|---|---|---|---|
| 1 — Hook + thesis | 60 s | — | `ai-obs-app-neoncart` (top, ribbon) |
| 2 — Traditional OTel | 60 s | — | `ai-obs-app-neoncart` (top rows) |
| 3 — Conversations | 90 s | ⭐ #1 | `ai-obs-app-neoncart` (middle rows) |
| 4 — Economics + impact | 90 s | ⭐ #2 | `ai-obs-outage-cost` *(switch #1)* |
| 5 — AI ↔ observability | 75 s | ⭐ #3 | `ai-obs-wags-ai` + Assistant *(switch #2)*; brief return to neoncart |
| 6 — Executive close | 60 s | — | `ai-obs-app-neoncart` |
| **Total** | **7 min 15 s** | **3** | **3 dashboards / 2 switches** |

Trim levers if running long (in order):
1. Cut the callback line in Act 4 (—10 s, but loses the loop closure)
2. Trim the Assistant question in Act 5 (—15 s, but weakens Wow #3)
3. Trim Act 6 to 45 s by dropping the "Three loops" close (—15 s,
   strategic loss)

Add levers if running short:
1. Linger on the convo drawer in Act 3 (+10 s, strengthens Wow #1)
2. Add a second missed-revenue example in Act 4 (+15 s, strengthens
   Wow #2)

---

## Hard rules for the script

1. **The thesis sentence is spoken verbatim in Act 1.** Don't paraphrase.
2. **The conversation primitive is spoken verbatim** the first time it
   appears (Act 1). After that, lean on it.
3. **The 97.7% / $114 → $2.67 hook is the cold open** in Act 1, and
   pays back as a callback in Act 4. Cut neither without restructuring.
4. **Three wow moments**: convo drill-down (Act 3) + missed-revenue +
   callback (Act 4) + recursive meta-conversation (Act 5). If a request
   implies cutting any of them, push back.
5. **Two dashboard switches max.** The scroll-within-neoncart in Acts
   1–3 is the secret weapon — protect it.
6. **Act 5's load-bearing beat is the meta-conversation**, not the
   Assistant query. The fallback recording must show the
   meta-conversation appearing in `ai-obs-app-neoncart`.
7. **End on the dashboard we opened on.** Visual return-to-start is
   the closure cue.

---

## What needs to be true in the environment for this to work

The script is grounded in real data. These are the preconditions:

- [ ] `ai-obs-app-neoncart` has a visible conversation drawer/drill-down
      from the Specialists bar chart. (Currently: bar chart exists,
      drill-down behavior to confirm.)
- [ ] `ai-obs-outage-cost` shows a recent (within last 24h) orange
      missed-revenue spike. (Currently: yes, the demo loadgen schedules
      these.)
- [ ] The cumulative 24h cost-savings number (97.7% / $114 → $2.67) is
      computable from live data — ideally surfaced as a small KPI panel
      on `ai-obs-app-neoncart` or `ai-obs-outage-cost` for the Act 4
      callback to land visually as well as verbally.
- [ ] Grafana Assistant can answer "why did revenue dip at 2:14?" with
      a usable response in ≤ 10 s. (Currently: gcx auth past the wall
      but `usage_limit_reached` — see `MEMORY.md → gcx_setup.md`.
      **Resolve before demo day.**)
- [ ] The Assistant conversation must itself emit
      `gen_ai_*` telemetry so it appears on the neoncart bar chart for
      the meta-conversation reveal. **Confirm telemetry path.**

---

## Open questions

- [ ] **Should the 97.7% number be on screen during Act 1?** Trade-off:
      visible = reinforces credibility; invisible = sets up a stronger
      Act 4 callback because the audience can't pre-read it.
      *Recommendation*: invisible in Act 1, visible (as a small KPI) in
      Act 4. Adds a panel requirement on `ai-obs-outage-cost`.
- [ ] **Fallback for Grafana Assistant** — pre-record + still, or live
      retry? Current plan: pre-recorded 30 s clip kept in a tab,
      shown on misfire.
- [ ] **Where does the shift-left motif appear visually?** The soft
      palette gradient (blue → purple → pink → orange) implicitly does
      this. Should we make it explicit with a recurring legend on each
      dashboard? *Risk*: another design element competing for
      attention. *Recommendation*: leave implicit; explain verbally in
      Act 1 only.
- [ ] **Does Act 2 need to live on a different dashboard?** Argument
      for switching to Explore: it dramatizes "this is traditional
      tooling." Argument against: a switch costs 5–8 seconds and we
      have budget pressure. *Recommendation*: stay on
      `ai-obs-app-neoncart` top rows — the SRE will recognize the
      tools regardless of whether they're in Explore or a dashboard.
- [ ] **Should Act 6 reuse the convo bar chart visually as a "see, it
      keeps measuring" close?** Probably yes — the visual continuity
      reinforces the recursion claim. Pending design pass.

---

## Hand-offs

If any of the **environment preconditions** above are red on demo day,
escalate to:

1. **Drill-down drawer missing on `ai-obs-app-neoncart`** → hand off to
   `ai-o11y-story-architect` for a rebuild of the Specialists row with
   explicit data-link / drill-down panels.
2. **Cost-savings KPI missing for Act 4 callback** → hand off to
   `ai-o11y-story-architect` to add a `ai.cost_per_mtoken` /
   `revenue.kpi` panel comparing local-marginal vs. equivalent-Claude
   cost.
3. **Assistant unreliable on demo day** → record the fallback now.
   Do not wait until demo day to find out.
