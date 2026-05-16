# Dashboard rating — current vs. envisioned look-and-feel

Rated against [`design_system.md`](design_system.md). Scores are 1–5 on six axes,
weighted equally. Bottom-line is the average.

Look & feel target: **the AI o11y reference style** (refined dark, soft palette
ribbon at the top, elevated card panels, intentional color, story arc).

## Axes
1. **Story arc** — does the dashboard read top-to-bottom as a single narrative?
2. **Hero emphasis** — is each row's most important panel visually dominant?
3. **Color discipline** — one palette track per panel, no rainbow, per-model pins?
4. **Human-scaled numbers** — units & magnitudes that pass the glance test?
5. **Premium feel** — elevated cards, descriptions, subtle annotations?
6. **Empty-state resilience** — no "No data" blanks, no flicker?

---

## `ai-obs-outage-cost` (the one we just rebuilt)

| Axis | Score | Note |
|---|:---:|---|
| Story arc | 4 | Business → missed → projected → engine → flow → sources → action. Missing "AI economics" callout. |
| Hero emphasis | 4 | Three heros are crisp ($/hr, missed today, projected cost). 24h, annualized still feel co-equal. |
| Color discipline | 4 | Status palette (green/red) on revenue is right. Per-model pins land on the stacked-by-model bars. The "annual @ 99% SLA" orange is a touch loud. |
| Human-scaled numbers | 4 | `$905K` / `$54K` / `360 carts/hr` / `3 hours` all read well. `$143M` annualized still needs a "if today repeats every day for a year" subtitle. |
| Premium feel | 3 | Lacks the aesthetic ribbon at the top — we haven't run `_apply_ai_obs_aesthetic.py` on it yet. Descriptions are good. |
| Empty-state resilience | 5 | `instant: true` + `noValue: "$0"` fixed the flicker. |
| **Avg** | **4.0** | — |

**Next moves**: run the aesthetic pass; add an AI-economics row before "Action"; rephrase the `$143M` subtitle.

---

## `ai-obs-app-neoncart` (the "convo bar chart" reference dashboard)

Rated from memory of the user's screenshots + reference.

| Axis | Score | Note |
|---|:---:|---|
| Story arc | 4 | The conversation bar chart is the hero. Surrounding panels support it. |
| Hero emphasis | 3 | The "AI o11y — NeonCart" headline isn't a hero, the convo bar steals attention by default. Could promote it intentionally. |
| Color discipline | 3 | Convo bars are great. Some right-side panels still use Grafana's classic palette. |
| Human-scaled numbers | 4 | Cost panels are properly per-hour / per-1M tokens. |
| Premium feel | 4 | Has the ribbon, has descriptions. The right-rail panels look like default Grafana. |
| Empty-state resilience | 4 | Per the recent canonical-labels sweep, panels show data. |
| **Avg** | **3.7** | — |

**Next moves**: per the user's words — the convo bars *love them*, but they "could use some outlining and shadow to pop". That's a fillOpacity bump + a soft shadow override on the override list. Apply the soft palette to the right-rail panels.

---

## `ai-obs-cost (per-user attribution)`

User explicitly said: *loves the convo bar chart series, but the right-side panels are using "standard Grafana color sets" — wants the soft palette applied there.*

| Axis | Score | Note |
|---|:---:|---|
| Story arc | 4 | Per-user attribution is the singular story. |
| Hero emphasis | 3 | The leaderboard is the natural hero but is sized similar to the supporting panels. |
| Color discipline | 2 | User identified this one — right-side panels are off-palette. |
| Human-scaled numbers | 4 | `$/1M tokens` convention is in place per memory. |
| Premium feel | 3 | Ribbon present, but the off-palette right rail breaks the feel. |
| Empty-state resilience | 4 | Mostly fine, recent fixes landed. |
| **Avg** | **3.3** | — |

**Next moves**: re-run `_apply_ai_obs_aesthetic.py` (it should soften those palette-classic right-rail colors). Add a fillOpacity / outline override on the convo bars to make them pop.

---

## `ai-obs-app-landing` (the "apps landing page")

The reference for what a polished section header / landing page should look like.
User said this one's the look-and-feel target.

| Axis | Score | Note |
|---|:---:|---|
| Story arc | 5 | Landing page — its job is to send you to the right deep-dive. Single-stage. |
| Hero emphasis | 5 | Big buttons / cards do their job. |
| Color discipline | 5 | All on the soft palette. |
| Human-scaled numbers | 5 | Mostly title text — no numerics to misjudge. |
| Premium feel | 5 | Reference for "premium". |
| Empty-state resilience | 5 | Static. |
| **Avg** | **5.0** | — |

**Next moves**: none. Use this as the reference for the design system.

---

## Average across observed dashboards: **4.0 / 5**

The shape is right. The gap is on color discipline (palette discipline on the
right-side panels) and on hero emphasis (it's the easy thing to forget when
you're focused on the queries). Running `_apply_ai_obs_aesthetic.py` as the
mandatory last step (per checklist §4) closes both gaps mechanically.

## What to do, ranked by impact

1. **Hard-enforce the aesthetic pass.** Every rebuild script's last line should
   be `subprocess.run(["python3", str(HERE / "_apply_ai_obs_aesthetic.py"), str(DASH)])`.
2. **Add the "shadow + outline pop" override** to the bar-chart helper —
   `custom.lineWidth: 1`, `custom.lineColor` matching the soft palette top hue
   (`palette.orange` for the warm end). This is what the user means by "pop".
3. **Promote section heroes consistently.** Hero = `w ≥ 12, h = 8,
   colorMode: background`. The dashboard rebuild script should validate this
   per row.
4. **Audit each curated dashboard for off-palette right-rail panels.**
   The aesthetic pass will fix most; the rest need per-panel overrides.
5. **Subtitle every big number.** `$143M` is meaningless without "if today
   repeats every day". Add a `description` on every hero stat.
