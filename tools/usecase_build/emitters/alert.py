"""AlertEmitter — emits Prometheus alerting rule groups.

One YAML file per use case at `alerts/<usecase>.yaml`, containing a single
rule group with one rule per alert in the use case.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..schema import UseCase


class AlertEmitter:
    """Emits a Prometheus rule group YAML per use case."""

    artifact_kind = "alerts"

    def emit(
        self,
        use_case: UseCase,
        archetype_path: Path,
        output_dir: Path,
    ) -> dict[str, Path]:
        if not use_case.alerts:
            return {}

        out_dir = output_dir / "alerts"
        out_dir.mkdir(parents=True, exist_ok=True)

        rules: list[dict] = []
        for al in use_case.alerts:
            rule = {
                "alert": al.name,
                "expr": al.condition,
                "for": al.duration,
                "labels": {
                    "severity": al.severity.value,
                    "use_case": use_case.name,
                    "app": use_case.app.value,
                },
                "annotations": {
                    "summary": f"{use_case.title}: {al.name} firing",
                    "description": (
                        use_case.description.strip().split("\n", 1)[0]
                        if use_case.description
                        else f"Alert from use case {use_case.name}"
                    ),
                    "runbook": f"registry/use_cases/{use_case.name}.yaml",
                },
            }
            if al.route:
                rule["labels"]["route"] = al.route
            rules.append(rule)

        doc = {"groups": [{"name": use_case.name, "rules": rules}]}
        out_path = out_dir / f"{use_case.name}.yaml"
        with out_path.open("w") as f:
            yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)
        return {"alerts": out_path}
