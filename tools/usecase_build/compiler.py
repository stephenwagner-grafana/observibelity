"""Compiler — turns a validated UseCase into all derived chart artifacts.

Two entry points:
- compile(use_case): run every emitter and return {kind: path}.
- validate(use_case): cross-cut validations Pydantic can't express on a
  single field (e.g. archetype/role pairing rules).
"""
from __future__ import annotations

from pathlib import Path

from .emitters import (
    AlertEmitter,
    DashboardEmitter,
    EvaluatorEmitter,
    RegistryRowEmitter,
    ScenarioEmitter,
    SLOEmitter,
)
from .schema import Archetype, Severity, UseCase


class Compiler:
    """Top-level compiler: dispatches a UseCase across all emitters."""

    def __init__(self, archetype_dir: Path, output_dir: Path) -> None:
        self.archetype_dir = Path(archetype_dir)
        self.output_dir = Path(output_dir)
        self.emitters = [
            EvaluatorEmitter(),
            DashboardEmitter(self.archetype_dir),
            AlertEmitter(),
            ScenarioEmitter(self.archetype_dir),
            SLOEmitter(),
            RegistryRowEmitter(),
        ]

    def compile(self, use_case: UseCase) -> dict[str, Path]:
        """Compile a UseCase. Returns {artifact_kind: output_path}."""
        archetype_path = self.archetype_dir / use_case.archetype.value
        # The archetype dir is allowed to be missing — emitters fall back to
        # placeholders so this tool stays useful while template packs are
        # being authored in parallel. (Compile-time hard failure here would
        # block every other agent.)
        if not archetype_path.exists():
            archetype_path.mkdir(parents=True, exist_ok=True)

        out_paths: dict[str, Path] = {}
        for emitter in self.emitters:
            paths = emitter.emit(use_case, archetype_path, self.output_dir)
            out_paths.update(paths)
        return out_paths

    def validate(self, use_case: UseCase) -> list[str]:
        """Run cross-field validations. Returns issues; empty list = valid.

        Pydantic handles single-field constraints; this method covers
        relationships between fields (e.g. centerpiece requires SLO).
        """
        issues: list[str] = []

        # Archetype-specific rules.
        if use_case.archetype == Archetype.SINGLE_EVENT_SEVERITY:
            crits = [e for e in use_case.evaluators if e.severity == Severity.CRITICAL]
            if not crits:
                issues.append(
                    "single-event-severity archetype requires at least one "
                    "critical evaluator"
                )

        if use_case.archetype == Archetype.LEADERBOARD:
            if not use_case.dashboard:
                issues.append("leaderboard archetype requires a dashboard")

        if use_case.archetype == Archetype.PER_USER_PATTERN:
            has_persona = any(
                s.persona or s.persona_filter for s in use_case.scenarios
            )
            if use_case.scenarios and not has_persona:
                issues.append(
                    "per-user-pattern archetype: at least one scenario must "
                    "set persona or persona_filter"
                )

        if use_case.archetype == Archetype.CASCADE:
            if len(use_case.scenarios) < 2:
                issues.append(
                    "cascade archetype expects multiple stages (≥2 scenarios)"
                )

        # Centerpiece rules.
        if use_case.centerpiece:
            if not use_case.slo:
                issues.append("centerpiece use cases must define an SLO")
            if not use_case.evaluators:
                issues.append("centerpiece use cases must define ≥1 evaluator")
            if not use_case.dashboard:
                issues.append("centerpiece use cases must define a dashboard")

        # Cross-component sanity.
        eval_names = {e.name for e in use_case.evaluators}
        if len(eval_names) != len(use_case.evaluators):
            issues.append("evaluator names must be unique within a use case")

        scn_names = {s.name for s in use_case.scenarios}
        if len(scn_names) != len(use_case.scenarios):
            issues.append("scenario names must be unique within a use case")

        alert_names = {a.name for a in use_case.alerts}
        if len(alert_names) != len(use_case.alerts):
            issues.append("alert names must be unique within a use case")

        # Alert routing referencing a real severity tier — soft check, only
        # warn if every alert has severity=low (almost certainly a mistake
        # for a demo signal).
        if use_case.alerts and all(a.severity == Severity.LOW for a in use_case.alerts):
            issues.append(
                "all alerts have severity=low — at least one should be "
                "medium or higher for the demo to surface in default views"
            )

        return issues
