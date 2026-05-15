"""ScenarioEmitter — emits k6 JS scenarios + ConfigMap manifests.

For each scenario in the use case, reads the archetype's k6 template (by
default `<archetype_dir>/k6_template.js`, optionally narrowed by the
scenario's `k6_template` field as a suffix), renders Jinja2 placeholders
with the use-case + scenario context, writes the JS to
`scenarios/<uc>.<scn>.js`, and a k8s ConfigMap referencing that script
at `scenarios/<uc>.<scn>.cm.yaml`.
"""
from __future__ import annotations

import json
from pathlib import Path

import jinja2
import yaml

from ..schema import UseCase, Scenario


# Sensible defaults for every Jinja var referenced across the bundled
# k6 templates. The compiler must always produce valid JavaScript, even
# when a use-case YAML omits an optional param. These defaults are JSON-
# encoded so they drop into the template literally (arrays as `[]`,
# numbers as `0`, strings as quoted strings via str()).
_TEMPLATE_DEFAULTS: dict[str, object] = {
    # leaderboard archetype
    "rank_by": "category",
    "group_by": "category",
    "baseline_rate": 10,
    "categories": ["general"],
    # per-user-pattern archetype
    "persona_id": "anonymous@acme.com",
    "pattern_signature": "default",
    "message_count": 1,
    "message_template": "help me with my order please",
    "message_templates": ["help me with my order please"],
    # trace-and-fix archetype
    "trace_filter": "default",
    "trigger_phrase": "trigger this trace",
    # single-event-severity archetype
    "event_pattern": "default",
    "severity_signal": "default",
    "critical_rate_per_hour": 1,
    "near_miss_rate_per_hour": 3,
    "critical_messages": ["TRIGGER_CRITICAL: default"],
    "near_miss_messages": ["TRIGGER_NEAR_MISS: looks like default but is benign"],
    # cascade archetype
    "counter_metric": "events_total",
    "threshold": 5,
    "window": "10m",
    "cascade_persona": "cascade@acme.com",
    "cascade_messages": ["step 1", "step 2", "step 3"],
    "cascade_interval": 30,
}


_FALLBACK_K6 = """\
// Auto-generated placeholder — archetype k6 template not found.
// Use case: $use_case  scenario: $scenario  persona: $persona  rate: $rate
import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  vus: 1,
  duration: '1m',
};

export default function () {
  http.get('http://placeholder.invalid/');
  sleep(60);
}
"""


def _jinja_value(v: object) -> object:
    """Coerce a context value into something safe to drop into k6 JS.

    Lists and dicts become JSON literals (so `[1,2,3]` lands as a valid
    JS array). Strings, ints, floats, and bools pass through unchanged
    and Jinja's default str() coercion produces valid JS literals.
    """
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    return v


def _render_template(text: str, mapping: dict[str, object]) -> str:
    """Render the k6 template via Jinja2.

    Uses StrictUndefined so a typo in a template surfaces at compile
    time rather than silently emitting `` (which becomes invalid JS).
    Defaults from `_TEMPLATE_DEFAULTS` are merged underneath the caller's
    context so optional vars always have a value.
    """
    ctx: dict[str, object] = {k: _jinja_value(v) for k, v in _TEMPLATE_DEFAULTS.items()}
    ctx.update({k: _jinja_value(v) for k, v in mapping.items()})
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False)
    return env.from_string(text).render(**ctx)


def _configmap(use_case_name: str, scenario_name: str, script_filename: str, script_body: str) -> dict:
    cm_name = f"loadgen-{use_case_name}-{scenario_name}".replace("_", "-")
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": cm_name,
            "labels": {
                "app.kubernetes.io/component": "loadgen",
                "observibelity.io/use-case": use_case_name,
                "observibelity.io/scenario": scenario_name,
            },
        },
        "data": {script_filename: script_body},
    }


class ScenarioEmitter:
    """Emits one k6 script + ConfigMap per scenario."""

    artifact_kind = "scenarios"

    def __init__(self, archetype_dir: Path) -> None:
        self.archetype_dir = archetype_dir

    def _load_k6_template(self, archetype_path: Path, scenario: Scenario) -> str:
        candidates = [
            archetype_path / f"k6_template.{scenario.k6_template}.js",
            archetype_path / "k6_template.js",
        ]
        for c in candidates:
            if c.exists():
                return c.read_text()
        return _FALLBACK_K6

    def emit(
        self,
        use_case: UseCase,
        archetype_path: Path,
        output_dir: Path,
    ) -> dict[str, Path]:
        if not use_case.scenarios:
            return {}

        out_dir = output_dir / "scenarios"
        out_dir.mkdir(parents=True, exist_ok=True)

        out_paths: dict[str, Path] = {}
        for scn in use_case.scenarios:
            tpl = self._load_k6_template(archetype_path, scn)
            mapping: dict[str, object] = {
                # Templates reference `{{ name }}` (use case) ubiquitously;
                # also keep `use_case`/`scenario` aliases for clarity.
                "name": use_case.name,
                "use_case": use_case.name,
                "scenario": scn.name,
                "persona": scn.persona or "",
                # `persona_id` is the per-user-pattern template's primary
                # handle on the sticky user; derive it from `persona` when
                # the YAML doesn't override via params.
                "persona_id": scn.persona or _TEMPLATE_DEFAULTS["persona_id"],
                "weight": scn.weight,
                "rate": scn.rate,
                "app": use_case.app.value,
                # Spread params as top-level vars; types pass through so
                # lists become JSON arrays and numbers stay numbers.
                **scn.params,
            }
            script = _render_template(tpl, mapping)
            script_filename = f"{use_case.name}.{scn.name}.js"

            js_path = out_dir / script_filename
            js_path.write_text(script)
            out_paths[f"scenario_js:{scn.name}"] = js_path

            cm = _configmap(use_case.name, scn.name, script_filename, script)
            cm_path = out_dir / f"{use_case.name}.{scn.name}.cm.yaml"
            with cm_path.open("w") as f:
                yaml.safe_dump(cm, f, sort_keys=False, default_flow_style=False)
            out_paths[f"scenario_cm:{scn.name}"] = cm_path

        return out_paths
