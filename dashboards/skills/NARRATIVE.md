# AI O11y narrative — the demo we are building

This document is the **primary source of truth** for the AI o11y demo
going forward. Everything else (dashboards, skills, code) is downstream
of this vision. **The dashboards compile from the story, not the
reverse.**

Read this before reading anything else in `dashboards/skills/`.

---

## What we are actually building

This is **not** "a set of Grafana dashboards." This is an
**AI-native observability presentation system**:

- narrative-aware dashboards
- semantic observability concepts
- automated aesthetic enforcement
- dashboard linting and critique
- story-first demo architecture
- AI-assisted observability workflows

The system should feel:

- **executive-friendly** — a CFO sees a number they care about in 5 seconds
- **cinematic** — emotional progression beat by beat
- **technically credible** — the SRE in the room respects the queries
- **emotionally understandable** — the business value lands viscerally
- **premium** — not "Grafana defaults", a deliberate product
- **deeply tied to Grafana + OpenTelemetry concepts** — this *is* Grafana, just refined

---

## Core thesis (the single sentence)

> **Observability optimized systems. Now observability is optimizing AI systems. And increasingly, AI is optimizing observability itself.**

That recursion is the demo's punchline. Three loops, each tighter than
the last:

1. classical o11y → systems get healthier
2. classical o11y → AI systems get healthier (the new frontier)
3. AI inside o11y → observability itself gets smarter (the recursive payoff)

---

## Secondary thesis — LLMs change the nature of telemetry

LLMs introduce things classical o11y was never designed for:

- **non-determinism** — the same input can produce different outputs
- **semantic ambiguity** — "correct" depends on intent
- **subjective correctness** — quality requires evaluation, not just success/fail
- **probabilistic workflows** — branches taken based on model decisions
- **agent / tool orchestration** — LLMs call tools that call LLMs
- **conversational execution paths** — the unit of work is a dialogue, not a request

Classical observability has three primitives:

- **metric datapoint** — the atomic unit of metrics
- **log line** — the atomic unit of logs
- **span** — the atomic unit of traces

AI observability introduces a fourth:

> **A conversation is the base unit of AI observability.**

A conversation is not just a log entry. It's a **semantic execution graph**
with:

- **prompts** — what the user asked, what the system asked the model
- **tools** — every function called, with arguments and results
- **evals** — quality judgments from rule-based or model-based judges
- **tokens** — input/output, by model, by phase
- **model decisions** — routing, fallbacks, retries
- **traces** — spans for every leg
- **user intent** — the inferred or declared goal
- **business outcomes** — the cart-add, the ticket created, the refund issued

Every dashboard panel in the AI o11y system should ultimately tie back
to **conversations**. The convo bar chart on `ai-obs-cost` is the
prototypical example — each bar is one conversation, with everything
about it discoverable on drill-down.

---

## Shift-left framing (the mental model)

The key conceptual axis is **subjective ↔ objective** /
**non-deterministic ↔ deterministic** (treat these as the same axis —
they correlate).

```
   LEFT                                                    RIGHT
   ─────────────────────────────────────────────────────────────
   subjective    ←─────── observability ───────→    objective
   experimental                                     production
   dev                                              prod
   non-deterministic                                deterministic
```

The insight:

> **AI observability shifts ambiguous AI behavior into measurable operational systems.**

The demo should repeatedly reinforce this **rightward motion**: moving
from reactive prod debugging toward proactive AI quality engineering,
with observability + evals + tracing + semantic telemetry as the
machinery.

Visually, the shift-left framing should appear in the narrative system
itself — a single recurring visual cue (gradient, arrow, color shift)
that telegraphs "we are moving left → right, subjective → objective"
across the dashboards.

---

## The strongest conceptual framings — keep these intact

If a future chat is uncertain how to phrase something, fall back to
one of these:

1. **"A conversation is the base unit of AI observability."** — the
   new primitive, alongside metrics, logs, traces.
2. **"AI changes the nature of telemetry itself."** — why o11y has to
   evolve, not just bolt on.
3. **"Observability optimized systems; now it optimizes AI."** — the
   bridge from the old story to the new.
4. **"Using AI to optimize observability, while using observability to
   optimize AI."** — the recursive payoff.
5. **"Shift-left turns subjective AI behavior into measurable
   operational systems."** — the executive-readable summary.
6. **"Observability is the control plane for AI systems."** — the
   strategic close. (*Replaces the earlier "operating system" phrasing
   — "control plane" is sharper, technically grounded, and lands
   harder for engineering audiences without losing executives.*)

Quote these verbatim where possible. They are load-bearing.

### The 97.7% callback (a recurring narrative motif)

The demo opens with a concrete cost number — *7.6M tokens of inference,
$114 on Claude Sonnet vs. $2.67 locally, a 97.7% reduction* — and pays
it back in Act 4 by comparing the day's AI inference cost ($2.67) to a
single 45-second outage's missed revenue (~$47K, ~18,000×). The
callback is the moment the audience realizes the *economics of AI are
not about inference cost; they're about what observability prevents*.
Protect this callback structurally — it's how the demo earns its
financial credibility.

---

## Target demo flow (6 acts, ~7 minutes)

The dashboards must serve these beats. If a dashboard doesn't support
one of these acts, it doesn't belong in the demo flow.

### Act 1 — Intro / Sales framing
**Beat**: "AI changes observability." Establish:
- the three classical primitives + the new "conversation" primitive
- deterministic vs non-deterministic systems
- subjective vs objective evaluation
- shift-left for AI systems
- Grafana + OTel + AI O11y as the answer

**Tone**: confident, big-picture. The audience should feel the scope.

### Act 2 — Traditional OTel + RCA
**Beat**: "Here's what o11y already does well." Demonstrate:
- production debugging on a deterministic failure
- traces / logs / metrics in the classical role
- the standard Grafana toolkit

**Tone**: grounded, familiar. The SRE in the room nods.

### Act 3 — AI conversations as telemetry
**Beat**: "Now look at this — an AI system, with conversations as
first-class telemetry." Demonstrate:
- conversations forked into the OTel stack
- spans, tools, models, evals all attached to one conversation
- the convo bar chart as the visual proof
- semantic search across conversations

**Tone**: the "huh, that's new" moment. The first **wow moment**.

### Act 4 — AI economics + operational impact
**Beat**: "And here's what it costs and what it pays back." Demonstrate:
- tokens / cost / latency per model
- eval quality (subjective → measurable)
- customer impact (the outage-cost dashboard)
- business value (revenue captured / missed)

**Tone**: now we're talking dollars. The CFO leans in.

### Act 5 — AI optimizing observability
**Beat**: "And now the recursive payoff." Demonstrate:
- AI investigations finding the root cause
- AI suggesting which panels matter for a given incident
- the feedback loop — observability improving AI quality, AI
  improving observability practice

**Tone**: the second **wow moment**. The future-state reveal.

### Act 6 — Executive payoff
**Beat**: "Why this matters." Close on:
- why AI O11y matters strategically
- why unified telemetry matters (Grafana's positioning)
- observability as the operating system for AI systems

**Tone**: confident, future-facing. Hand-off to Q&A.

---

## Wow moments — the punchlines we are aiming for

These are the specific instants the audience should feel something.
The demo has **three load-bearing wow moments**; lose any of them and
the demo is hollow.

1. ⭐ **WOW #1 — Conversation primitive revealed.** *(Act 3)* The
   audience sees one bar in `📦 Specialists` open into a conversation
   drawer with prompt + tools + evals + tokens + trace + business
   outcome. The realization: *a conversation is to AI o11y what a span
   is to traces*. **Load-bearing.**

2. ⭐ **WOW #2 — Missed-revenue + 97.7% callback.** *(Act 4)* The
   orange spike on the missed-revenue chart ($47K in 45 seconds) is
   immediately compared to the day's AI inference cost ($2.67). The
   ratio (~18,000×) is the gut-punch — *the economics of AI are not
   about what inference costs, they're about what observability
   prevents*. **Load-bearing.** Requires the 97.7% hook to have been
   planted in Act 1.

3. ⭐ **WOW #3 — Recursive meta-conversation.** *(Act 5)* The
   conversation that the demo presenter just had with Grafana Assistant
   appears, in real time, on the *same* `ai-obs-app-neoncart` bar
   chart that showed customer conversations in Act 3. *The
   observability system observes itself.* The recursion stops being a
   slogan and becomes a visible loop. **Load-bearing — this is the
   meta-payoff.**

The wow moments are spaced ~2 minutes apart, which is roughly the
audience's emotional attention budget. Don't bunch them.

---

## Visual language — what supports the narrative

The design system already enforces most of this; `design_system.md`
should be read as **the visual half of this narrative document**. Hard
rules that serve the story:

- **The ribbon** at the top of every dashboard is the unifying motif —
  a single visual signature that says "you are in the AI o11y system".
- **Status palette** (green / amber / red) for "is it working?" — the
  story of health.
- **Soft palette** (blue → purple → pink → orange) for AI feel — the
  story of model economics.
- **Per-model color pins** — model identity is conserved across panels.
- **Conversation visualizations** — every dashboard should have at
  least one panel where you can clearly see "this is conversations,
  not just data".
- **One hero per row** — beats are visually punctuated.

---

## Implementation direction

The dashboard system should increasingly behave like a **semantic
dashboard compiler**, not a prompt collection:

```
   spoken narrative
        ↓
   story beats (one per demo act)
        ↓
   dashboard archetype per beat
        ↓
   semantic panel taxonomy
        ↓
   design tokens + aesthetic compiler
        ↓
   final dashboard JSON (push to Grafana Cloud)
        ↓
   linter + critic + iteration
```

Skills evolve to match: `ai-o11y-demo-narrator` (new) writes / refines
the spoken script; `ai-o11y-story-architect` maps a beat to a dashboard
plan; the rest of the pipeline renders.

---

## Tomorrow's primary work

**Not** "build dashboards." **Instead**:

1. Write the actual spoken demo script (start in `DEMO_SCRIPT.md`).
2. Tighten the emotional arc — where does each act land?
3. Refine the conceptual explanations until each is one short sentence.
4. Identify the wow moments precisely (above is v1; expect revision).
5. Decide which existing dashboards support each beat; which need a
   rebuild; which need to be retired.
6. Evolve the skills around the finalized narrative.

The dashboards should **support** narration, not overwhelm it. If a
dashboard requires explanation, the dashboard is wrong — the narration
should be the explanation and the dashboard the evidence.

---

## Where this fits

- **This file is canonical** for the project's *direction*.
- **`design_system.md`** is canonical for the *visual contract*.
- **`README.md` (skills/)** is canonical for the *pipeline*.
- **`DEMO_SCRIPT.md`** (next) will be canonical for the *spoken
  narration*.
- **`CONTINUATION.md`** is canonical for *where we left off*.

Read in that order at the start of every chat.
