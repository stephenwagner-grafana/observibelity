"""Pydantic models for the bundled use-case YAML schema.

A "use case" is the smallest demoable unit in ObserVIBElity. Each YAML in
registry/use_cases/<name>.yaml describes one use case: its scenarios (load),
evaluators (signal extraction), dashboard panels, alert rules, SLO and
demo-script metadata. The compiler reads these YAMLs and emits Sigil
evaluator JSON, Grafana dashboard JSON, Prometheus rule YAML, k6 scenario
JS + ConfigMap, OpenSLO YAML, and registry rows.

All models use Pydantic 2.x syntax.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# --- Enums --------------------------------------------------------------


class Severity(str, Enum):
    """Severity level shared by evaluators + alerts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Archetype(str, Enum):
    """The five canonical use-case archetypes. Each archetype maps to a
    template pack under tools/usecase-templates/<archetype>/ that supplies
    the k6 scenario skeleton + Grafana panel pack."""

    TRACE_AND_FIX = "trace-and-fix"
    PER_USER_PATTERN = "per-user-pattern"
    LEADERBOARD = "leaderboard"
    SINGLE_EVENT_SEVERITY = "single-event-severity"
    CASCADE = "cascade"


class App(str, Enum):
    """Which demo app this use case exercises."""

    NEONCART = "neoncart"
    SUPPORTBOT = "supportbot"
    BOTH = "both"


class EvaluatorKind(str, Enum):
    """Sigil evaluator kinds."""

    RULE = "rule"
    RUBRIC = "rubric"
    REGEX = "regex"
    LLM_JUDGE = "llm-judge"


# --- Nested models ------------------------------------------------------


class Scenario(BaseModel):
    """One k6 traffic scenario.

    `k6_template` names a sub-template inside the archetype's template pack
    (e.g. "sticky-persona", "rate-burst"). `params` is sub-template-specific
    and is interpolated into the k6 JS at compile time.
    """

    name: str
    k6_template: str
    persona: Optional[str] = None
    persona_filter: Optional[list[str]] = None
    weight: int = 1
    rate: str = "5m"  # e.g. "5m" = wait 5 min, "5/h" = 5 per hour
    params: dict = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_is_identifier_safe(cls, v: str) -> str:
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("scenario name must be identifier-safe")
        return v


class Evaluator(BaseModel):
    """One Sigil evaluator.

    `spec` is the rule expression / rubric prompt / regex pattern, depending
    on `kind`. The compiler will emit a Sigil-format JSON file.
    """

    name: str
    kind: EvaluatorKind
    severity: Severity = Severity.MEDIUM
    spec: str
    params: dict = Field(default_factory=dict)

    @field_validator("spec")
    @classmethod
    def spec_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("evaluator spec must be non-empty")
        return v


class Dashboard(BaseModel):
    """The use case's dashboard.

    `panels_from_template` names a panel pack inside the archetype template
    dir. `extra_panels` is a list of raw Grafana panel JSON dicts that are
    appended verbatim after the templated panels.
    """

    uid: str
    title: Optional[str] = None
    panels_from_template: Optional[str] = None
    extra_panels: list[dict] = Field(default_factory=list)
    folder: str = "ai-observability"


class Alert(BaseModel):
    """One Prometheus alerting rule.

    `condition` is the PromQL expression. `route` is the contact-point name
    in Alertmanager (email address, Slack channel, etc.).
    """

    name: str
    condition: str
    severity: Severity
    route: Optional[str] = None
    duration: str = "5m"


class SLO(BaseModel):
    """An SLO with an error budget. Required for centerpiece use cases."""

    objective: str
    error_budget: float = 0.001
    window: str = "30d"


class Demo(BaseModel):
    """Demo-script metadata used by the wizards + skill prompts.

    `do` describes what the SE does to trigger the signal.
    `signal` describes what shows up where (which dashboard, which alert).
    `sell` is the one-line value prop for an SE pitch.
    """

    do: str
    signal: str
    sell: Optional[str] = None


# --- Top-level model ----------------------------------------------------


class UseCase(BaseModel):
    """One bundled use case.

    Compiles into: evaluator JSON, dashboard JSON, alert rule YAML, k6 JS +
    ConfigMap, SLO YAML, and a registry row in registry/use_cases.yaml.
    """

    name: str
    title: str
    app: App
    phase: int = Field(ge=0, le=2)
    centerpiece: bool = False
    archetype: Archetype
    description: Optional[str] = None

    scenarios: list[Scenario] = Field(default_factory=list)
    evaluators: list[Evaluator] = Field(default_factory=list)
    dashboard: Optional[Dashboard] = None
    alerts: list[Alert] = Field(default_factory=list)
    slo: Optional[SLO] = None
    demo: Optional[Demo] = None

    @field_validator("name")
    @classmethod
    def name_must_be_kebab_case(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("name must be kebab-case (lowercase, hyphens)")
        if v != v.lower():
            raise ValueError("name must be lowercase")
        return v

    @field_validator("title")
    @classmethod
    def title_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title must be non-empty")
        return v


# --- Errors -------------------------------------------------------------


class UseCaseValidationError(Exception):
    """Raised when a use case fails validation beyond what Pydantic catches."""

    def __init__(self, name: str, issues: list[str]) -> None:
        self.use_case_name = name
        self.issues = issues
        msg = f"use case {name!r} has {len(issues)} validation issue(s):\n" + "\n".join(
            f"  - {iss}" for iss in issues
        )
        super().__init__(msg)
