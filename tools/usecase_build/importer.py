"""importer — read /workspace/ai-o11y-demo-pack and emit bundled YAMLs.

For each Python UseCase subclass under <demo-pack>/registry/use_cases/*.py we
parse the file with the AST (no imports, no exec) to extract the static class
attributes. Each one is mapped to a bundled YAML under
/workspace/observibelity/registry/use_cases/<name>.yaml.

Strategy:
  1. Walk *.py files, skip `__init__.py` and `base.py`.
  2. Build the class attribute table via ast.parse + ast.literal_eval.
  3. Map demo-pack archetype enum -> ObserVIBElity archetype keyword:
       DETERMINISTIC_RCA       -> trace-and-fix
       PER_USER_PATTERN        -> per-user-pattern
       LEADERBOARD             -> leaderboard
       SINGLE_EVENT_SEVERITY   -> single-event-severity
       PER_SESSION_SEVERITY    -> cascade
       GLOBAL_RATE             -> leaderboard   (rate ranked by category)
       REGRESSION_CURVE        -> leaderboard   (rate trend over time)
       PER_POLICY_RATE         -> leaderboard   (rate ranked by policy)
     (also heuristic fallback based on attribute names)
  4. Look up scenarios in <demo-pack>/registry/scenarios.yaml by
     `loadgen_scenarios` slug.
  5. Look up dashboards in <demo-pack>/dashboards/*.json by uid.
  6. Look up alerts in <demo-pack>/registry/alerts.yaml by ``grafana_alert_rules``.
  7. Skip the 3 use cases removed per planner.
  8. Skip if the output YAML already exists (warning).
  9. Print summary table to stderr.

Usage:
    python -m usecase_build.importer /path/to/ai-o11y-demo-pack
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover — pip install runs in the bash wrapper
    print("ERROR: pyyaml not installed. Run `pip install -r tools/requirements.txt`.", file=sys.stderr)
    sys.exit(2)


# --------------------------------------------------------------------------- #
# constants                                                                   #
# --------------------------------------------------------------------------- #

# 23 use cases the planner wants imported (kebab-case names). The keys are the
# `id` values found in the demo-pack Python files; the values are the bundled
# YAML names. Use cases not in this map are dropped with a "skipped" log line.
TARGET_USE_CASES: dict[str, str] = {
    "neoncart-mice-rca":                "mice-rca",
    "gift-recommender-model-winner":    "model-winner",
    "gift-recommender-quality-trend":   "quality-trend",
    "email-cascade":                    "email-cascade",
    "data-theft-tim":                   "data-theft-tim",
    "outlier-users-tim-eric":           "outlier-users",
    "prompt_injection":                 "prompt-injection-llm01",
    "sensitive-data-leaks":             "sensitive-data-leaks",
    "bad-question-askers":              "bad-question-askers",
    "token-spikes":                     "token-spikes",
    "toxicity":                         "toxicity",
    "hallucination_product_price":      "hallucination-product-price",
    "refund_policy_compliance":         "refund-policy-compliance",
    "pii_echo":                         "pii-echo",
    "customer_frustration":             "customer-frustration",
    "brand_voice_drift":                "brand-voice-drift",
    "confidential_disclosure":          "confidential-disclosure",
    "policy_circumvention":             "policy-circumvention",
    "hiring_discrimination_risk":       "hiring-discrimination-risk",
    "tool_call_runaway":                "tool-call-runaway",
    "cost_anomaly_per_user":            "cost-anomaly-per-user",
    "prompt-injections":                "prompt-injection",
    "response-guards":                  "response-guards",
}

# Dropped per planner — log "skipped: <name> (removed per planner)".
REMOVED_PER_PLANNER: set[str] = {
    "coworker_termination_intent",
    "llm-judge-supervisor",
    "least_efficient_user",
    "offline-evals-regression",
}

# Demo-pack Archetype enum value -> ObserVIBElity archetype keyword.
ARCHETYPE_MAP: dict[str, str] = {
    "DETERMINISTIC_RCA":      "trace-and-fix",
    "PER_USER_PATTERN":       "per-user-pattern",
    "LEADERBOARD":            "leaderboard",
    "SINGLE_EVENT_SEVERITY":  "single-event-severity",
    "PER_SESSION_SEVERITY":   "cascade",
    "GLOBAL_RATE":            "leaderboard",
    "REGRESSION_CURVE":       "leaderboard",
    "PER_POLICY_RATE":        "leaderboard",
}

VALID_ARCHETYPES = {
    "trace-and-fix", "per-user-pattern", "leaderboard",
    "single-event-severity", "cascade",
}


# --------------------------------------------------------------------------- #
# data classes                                                                #
# --------------------------------------------------------------------------- #

@dataclass
class ImportResult:
    imported: list[tuple[str, str]] = field(default_factory=list)   # (name, archetype)
    skipped: list[tuple[str, str]] = field(default_factory=list)    # (name, reason)
    errors: list[tuple[str, str]] = field(default_factory=list)     # (path, msg)


# --------------------------------------------------------------------------- #
# AST helpers                                                                 #
# --------------------------------------------------------------------------- #

def _literal(node: ast.AST) -> Any:
    """Best-effort literal evaluation. Returns None when not a literal."""
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def _enum_value(node: ast.AST) -> str | None:
    """Return the RHS attribute name for `EnumClass.VALUE` references."""
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _list_of_enum_values(node: ast.AST) -> list[str]:
    if not isinstance(node, ast.List):
        return []
    out: list[str] = []
    for el in node.elts:
        v = _enum_value(el)
        if v is not None:
            out.append(v)
    return out


def _list_of_call_first_arg(node: ast.AST) -> list[str]:
    """For lists like [DashboardRef("foo"), DashboardRef("bar", "x")] return
    the first positional arg of every call. Skips elements that don't match."""
    if not isinstance(node, ast.List):
        return []
    out: list[str] = []
    for el in node.elts:
        if isinstance(el, ast.Call) and el.args:
            first = _literal(el.args[0])
            if isinstance(first, str):
                out.append(first)
    return out


def _list_of_call_kwargs(node: ast.AST) -> list[dict[str, Any]]:
    """For lists of dataclass constructors return a list of {arg_name: value}
    dicts. Positional args are mapped to numeric keys ('_0', '_1', ...)."""
    if not isinstance(node, ast.List):
        return []
    out: list[dict[str, Any]] = []
    for el in node.elts:
        if not isinstance(el, ast.Call):
            continue
        rec: dict[str, Any] = {}
        for i, a in enumerate(el.args):
            rec[f"_{i}"] = _literal(a)
        for kw in el.keywords:
            if kw.arg:
                rec[kw.arg] = _literal(kw.value)
        out.append(rec)
    return out


def _parse_usecase_class(tree: ast.Module) -> dict[str, Any] | None:
    """Find the first class whose bases include a name like 'UseCase' and
    return its static attribute table."""
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(
            (isinstance(b, ast.Name) and b.id.endswith("UseCase"))
            or (isinstance(b, ast.Attribute) and b.attr.endswith("UseCase"))
            for b in node.bases
        ):
            continue
        attrs: dict[str, Any] = {"_class_name": node.name}
        for stmt in node.body:
            # plain assignment: id = "foo"
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        attrs[t.id] = _read_attr(stmt.value)
            # annotated assignment: id: ClassVar[str] = "foo"
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
                attrs[stmt.target.id] = _read_attr(stmt.value)
        return attrs
    return None


def _read_attr(value: ast.AST) -> Any:
    """Dispatch attribute reading. Returns a literal, an enum string, a list,
    or a list-of-dict shape depending on what we see."""
    if isinstance(value, ast.Constant):
        return value.value
    if isinstance(value, ast.List):
        # Inspect first element to choose the right reader
        if value.elts and isinstance(value.elts[0], ast.Attribute):
            return _list_of_enum_values(value)
        if value.elts and isinstance(value.elts[0], ast.Call):
            return _list_of_call_kwargs(value)
        # Plain list of literals
        lit = _literal(value)
        return lit if lit is not None else []
    if isinstance(value, ast.Attribute):
        return _enum_value(value)
    return _literal(value)


# --------------------------------------------------------------------------- #
# archetype inference                                                         #
# --------------------------------------------------------------------------- #

def infer_archetype(attrs: dict[str, Any], source_text: str) -> str:
    """Map a demo-pack Archetype.X enum value to one of the 5 ObserVIBElity
    archetypes. Falls back to keyword heuristics, then 'leaderboard'."""
    raw = attrs.get("archetype")
    if isinstance(raw, str) and raw in ARCHETYPE_MAP:
        return ARCHETYPE_MAP[raw]

    name = (attrs.get("_class_name") or "").lower()
    text = source_text.lower()

    if "cascade" in name or "runaway" in name or "cascade" in text and "loop" in text:
        return "cascade"
    if "single_event" in text or "critical_alert_threshold=1" in text:
        return "single-event-severity"
    if "persona" in text and "weight" in text:
        return "per-user-pattern"
    if "trace_filter" in text or "trace_id" in text:
        return "trace-and-fix"
    if "judge" in text and "rate" in text:
        return "leaderboard"
    return "leaderboard"


# --------------------------------------------------------------------------- #
# sidecar lookups                                                             #
# --------------------------------------------------------------------------- #

def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text())
        return loaded if isinstance(loaded, dict) else {}
    except yaml.YAMLError:
        return {}


def _index_dashboards(dashboard_dir: Path) -> dict[str, dict[str, Any]]:
    """uid -> {title, uid, slug}. We only need lightweight metadata."""
    out: dict[str, dict[str, Any]] = {}
    if not dashboard_dir.exists():
        return out
    for f in sorted(dashboard_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        uid = data.get("uid") or f.stem
        out[uid] = {
            "uid": uid,
            "title": data.get("title", uid),
            "file": str(f.name),
        }
    return out


# --------------------------------------------------------------------------- #
# YAML emission                                                               #
# --------------------------------------------------------------------------- #

# Demo-pack severity ('warning', 'critical', ...) -> schema Severity enum
SEVERITY_MAP: dict[str, str] = {
    "low": "low", "info": "low",
    "med": "medium", "medium": "medium", "warning": "medium",
    "warn": "medium",
    "high": "high",
    "critical": "critical", "crit": "critical", "p0": "critical",
}


def _normalize_severity(raw: Any, default: str = "medium") -> str:
    if not isinstance(raw, str):
        return default
    return SEVERITY_MAP.get(raw.strip().lower(), default)


def build_yaml(
    name: str,
    attrs: dict[str, Any],
    archetype: str,
    scenarios_index: dict[str, Any],
    dashboards_index: dict[str, dict[str, Any]],
    alerts_index: dict[str, Any],
) -> dict[str, Any]:
    """Construct the bundled YAML dict for one use case.

    Field names + value shapes match `usecase_build.schema.UseCase` exactly so
    the output round-trips through `UseCase(**yaml.safe_load(...))`.
    """
    title = attrs.get("title") or name.replace("-", " ").title()
    description = (attrs.get("description") or "").strip() or f"TODO: describe {name}"
    app = attrs.get("app") or "neoncart"
    if app not in {"neoncart", "supportbot", "both"}:
        # ObserVIBElity only ships these three; fold "hrbot" into supportbot
        app = "supportbot" if app == "hrbot" else "neoncart"

    is_centerpiece = bool(attrs.get("is_centerpiece") or False)
    phase = 1 if is_centerpiece else 2

    # --- scenarios -------------------------------------------------------- #
    rate_per_min = attrs.get("loadgen_rate_per_min") or 30
    rate_str = f"{rate_per_min}/m" if rate_per_min else "5m"

    scenarios: list[dict[str, Any]] = []
    for s_name in attrs.get("loadgen_scenarios") or []:
        if not isinstance(s_name, str):
            continue
        sd = scenarios_index.get(s_name) or {}
        s_weight = sd.get("weight", 1)
        # schema requires int weight; round if needed
        if isinstance(s_weight, float):
            s_weight = max(1, int(round(s_weight)))
        scenarios.append({
            "name": s_name,
            "k6_template": _scenario_template_for(archetype),
            "weight": s_weight,
            "rate": rate_str,
            "params": {
                "description": sd.get("description", f"TODO: describe scenario {s_name}"),
                "capability": sd.get("capability", "TODO"),
            },
        })
    if not scenarios:
        scenarios.append({
            "name": f"{name}-default",
            "k6_template": _scenario_template_for(archetype),
            "weight": 1,
            "rate": rate_str,
            "params": {"description": "TODO: define a k6 traffic scenario for this use case"},
        })

    # --- evaluators (cannot be inferred from a Python class) -------------- #
    # single-event-severity archetype requires at least one 'critical'
    # evaluator (enforced by the compiler).
    eval_severity = "critical" if archetype == "single-event-severity" else "medium"
    evaluators: list[dict[str, Any]] = [{
        "name": f"{name}-default",
        "kind": "rubric",  # TODO: review — could be rule | regex | llm-judge
        "severity": eval_severity,
        "spec": "TODO: Sigil expression (rule | rubric prompt | regex pattern)",
        "params": {},
    }]

    # --- dashboard --------------------------------------------------------- #
    dashboard_uid_refs: list[str] = []
    db_attr = attrs.get("grafana_dashboards")
    if isinstance(db_attr, list):
        for item in db_attr:
            if isinstance(item, dict):
                v = item.get("_0") or item.get("uid")
                if isinstance(v, str):
                    dashboard_uid_refs.append(v)
    primary_uid = dashboard_uid_refs[0] if dashboard_uid_refs else f"obs-uc-{name}"
    primary_meta = dashboards_index.get(primary_uid, {})
    dashboard = {
        "uid": primary_uid,
        "title": primary_meta.get("title", title),
        "panels_from_template": archetype,
        "extra_panels": [],
        "folder": "ai-observability",
    }

    # --- alerts ------------------------------------------------------------ #
    alerts: list[dict[str, Any]] = []
    for rule_name in attrs.get("grafana_alert_rules") or []:
        if not isinstance(rule_name, str):
            continue
        rd = alerts_index.get(rule_name) or {}
        alerts.append({
            "name": rule_name,
            "condition": (rd.get("query") or "TODO: PromQL alert condition").strip(),
            "severity": _normalize_severity(rd.get("severity"), default="medium"),
            "duration": "5m",
        })

    # --- SLO --------------------------------------------------------------- #
    slo: dict[str, Any] | None = None
    if is_centerpiece:
        slo = {
            "objective": "TODO: e.g. 'success_rate >= 0.95'",
            "error_budget": 0.001,
            "window": "30d",
        }

    # --- demo metadata ----------------------------------------------------- #
    demo = {
        "do": (attrs.get("problem") or f"TODO: what does the SE do to trigger {name}?").strip(),
        "signal": (attrs.get("customer_pitch") or "TODO: where does the signal show up?").strip(),
        "sell": (attrs.get("punchline") or "TODO: one-line value prop").strip(),
    }

    out: dict[str, Any] = {
        "name": name,
        "title": title.strip() if isinstance(title, str) else str(title),
        "app": app,
        "phase": phase,
        "centerpiece": is_centerpiece,
        "archetype": archetype,
        "description": description,
        "scenarios": scenarios,
        "evaluators": evaluators,
        "dashboard": dashboard,
        "alerts": alerts,
        "demo": demo,
    }
    if slo is not None:
        out["slo"] = slo
    return out


def _scenario_template_for(archetype: str) -> str:
    """Default k6 sub-template name for each archetype. Authors can swap."""
    return {
        "trace-and-fix":          "single-trigger",
        "per-user-pattern":       "sticky-persona",
        "leaderboard":            "rate-by-category",
        "single-event-severity":  "rare-event",
        "cascade":                "burst-then-quiet",
    }.get(archetype, "single-trigger")


# --------------------------------------------------------------------------- #
# main driver                                                                 #
# --------------------------------------------------------------------------- #

def kebab(s: str) -> str:
    s = re.sub(r"[_\s]+", "-", s.strip().lower())
    s = re.sub(r"[^a-z0-9\-]+", "", s)
    return re.sub(r"-+", "-", s).strip("-")


def import_one(
    py_file: Path,
    out_dir: Path,
    scenarios_index: dict[str, Any],
    dashboards_index: dict[str, dict[str, Any]],
    alerts_index: dict[str, Any],
    result: ImportResult,
) -> None:
    """Parse one demo-pack Python use case and (maybe) write a YAML."""
    try:
        source = py_file.read_text()
        tree = ast.parse(source, filename=str(py_file))
    except (OSError, SyntaxError) as e:
        result.errors.append((str(py_file), f"parse failed: {e}"))
        return

    attrs = _parse_usecase_class(tree)
    if attrs is None:
        result.skipped.append((py_file.stem, "no UseCase subclass found"))
        return

    raw_id = attrs.get("id") or attrs.get("slug") or py_file.stem
    if not isinstance(raw_id, str):
        result.errors.append((str(py_file), "missing string 'id' or 'slug'"))
        return

    # Drop planner-removed use cases.
    if raw_id in REMOVED_PER_PLANNER or py_file.stem in {
        "coworker_termination", "llm_judge_supervisor",
        "least_efficient_user", "offline_evals_regression",
    }:
        result.skipped.append((raw_id, "removed per planner"))
        return

    # If we have an allowlist and this isn't on it, drop (keeps imports tight).
    if TARGET_USE_CASES and raw_id not in TARGET_USE_CASES:
        result.skipped.append((raw_id, "not in target list"))
        return

    name = TARGET_USE_CASES.get(raw_id) or kebab(raw_id)
    archetype = infer_archetype(attrs, source)

    if archetype not in VALID_ARCHETYPES:
        result.errors.append((str(py_file), f"invalid archetype mapping: {archetype}"))
        return

    out_path = out_dir / f"{name}.yaml"
    if out_path.exists():
        result.skipped.append((name, "output YAML exists — refusing to overwrite"))
        return

    data = build_yaml(
        name=name,
        attrs=attrs,
        archetype=archetype,
        scenarios_index=scenarios_index,
        dashboards_index=dashboards_index,
        alerts_index=alerts_index,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "# Imported from /workspace/ai-o11y-demo-pack — review TODO markers.\n"
        + yaml.safe_dump(data, sort_keys=False, default_flow_style=False, width=100)
    )
    result.imported.append((name, archetype))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "demo_pack",
        nargs="?",
        default="/workspace/ai-o11y-demo-pack",
        help="Path to the legacy ai-o11y-demo-pack repo",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory for bundled YAMLs (default: <repo>/registry/use_cases)",
    )
    args = parser.parse_args(argv)

    demo_pack = Path(args.demo_pack)
    if not demo_pack.is_dir():
        print(f"ERROR: demo-pack not found at {demo_pack}", file=sys.stderr)
        return 2

    py_dir = demo_pack / "registry" / "use_cases"
    if not py_dir.is_dir():
        print(f"ERROR: missing {py_dir}", file=sys.stderr)
        return 2

    # ObserVIBElity repo root is two levels up from this file
    # (.../observibelity/tools/usecase_build/importer.py)
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = Path(args.out) if args.out else repo_root / "registry" / "use_cases"

    scenarios_index = _load_yaml(demo_pack / "registry" / "scenarios.yaml")
    alerts_index = _load_yaml(demo_pack / "registry" / "alerts.yaml")
    dashboards_index = _index_dashboards(demo_pack / "dashboards")

    result = ImportResult()
    py_files = sorted(
        f for f in py_dir.glob("*.py")
        if f.name not in {"__init__.py", "base.py"}
    )
    for f in py_files:
        import_one(f, out_dir, scenarios_index, dashboards_index, alerts_index, result)

    _print_summary(result, out_dir)
    return 0 if not result.errors else 1


def _print_summary(result: ImportResult, out_dir: Path) -> None:
    print("", file=sys.stderr)
    print(f"=== Import summary (out: {out_dir}) ===", file=sys.stderr)
    print(f"  imported: {len(result.imported)}", file=sys.stderr)
    for name, arch in result.imported:
        print(f"    + {name:35s}  archetype={arch}", file=sys.stderr)
    if result.skipped:
        print(f"  skipped: {len(result.skipped)}", file=sys.stderr)
        for name, reason in result.skipped:
            print(f"    - {name:35s}  ({reason})", file=sys.stderr)
    if result.errors:
        print(f"  errors:  {len(result.errors)}", file=sys.stderr)
        for path, msg in result.errors:
            print(f"    ! {path}: {msg}", file=sys.stderr)
    print("", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
