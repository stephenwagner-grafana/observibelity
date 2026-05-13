"""SLOEmitter — emits a simple OpenSLO-flavored YAML per use case.

We don't strictly follow the OpenSLO spec (which is heavyweight); we emit a
small SLO doc that downstream tooling (Pyrra, OpenSLO converters) can map
onto its native shape.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..schema import UseCase


class SLOEmitter:
    """Emits an SLO YAML if the use case defines one."""

    artifact_kind = "slos"

    def emit(
        self,
        use_case: UseCase,
        archetype_path: Path,
        output_dir: Path,
    ) -> dict[str, Path]:
        if use_case.slo is None:
            return {}

        out_dir = output_dir / "slos"
        out_dir.mkdir(parents=True, exist_ok=True)

        slo = use_case.slo
        doc = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {
                "name": use_case.name,
                "displayName": use_case.title,
                "labels": {
                    "use_case": use_case.name,
                    "app": use_case.app.value,
                    "archetype": use_case.archetype.value,
                },
            },
            "spec": {
                "description": slo.objective,
                "service": use_case.app.value,
                "budgetingMethod": "Occurrences",
                "timeWindow": [{"duration": slo.window, "isRolling": True}],
                "objectives": [
                    {
                        "displayName": slo.objective,
                        "target": 1.0 - slo.error_budget,
                    }
                ],
            },
        }
        out_path = out_dir / f"{use_case.name}.yaml"
        with out_path.open("w") as f:
            yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)
        return {"slo": out_path}
