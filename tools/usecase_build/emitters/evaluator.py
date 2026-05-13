"""EvaluatorEmitter — emits Sigil evaluator JSON files.

One JSON file per evaluator, named <usecase>.<evaluator>.json. The format
is a best-effort approximation of the Sigil evaluator spec (per the live
planner): a single JSON object with name/kind/severity/expression/tags.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..schema import UseCase

# Sigil JSON header — included as a top-level key so the file remains
# valid JSON (Sigil ignores unknown top-level keys). Points back to the
# source YAML for round-trip traceability.
_HEADER_KEY = "_source"


class EvaluatorEmitter:
    """Emits one Sigil JSON per evaluator in the use case."""

    artifact_kind = "evaluators"

    def emit(
        self,
        use_case: UseCase,
        archetype_path: Path,
        output_dir: Path,
    ) -> dict[str, Path]:
        out_dir = output_dir / "evaluators"
        out_dir.mkdir(parents=True, exist_ok=True)

        out_paths: dict[str, Path] = {}
        for ev in use_case.evaluators:
            spec = {
                _HEADER_KEY: f"registry/use_cases/{use_case.name}.yaml",
                "name": ev.name,
                "kind": ev.kind.value,
                "severity": ev.severity.value,
                "expression": ev.spec,
                "tags": [
                    f"use_case:{use_case.name}",
                    f"app:{use_case.app.value}",
                    f"archetype:{use_case.archetype.value}",
                    f"phase:{use_case.phase}",
                ],
                "params": ev.params,
            }
            out_path = out_dir / f"{use_case.name}.{ev.name}.json"
            out_path.write_text(json.dumps(spec, indent=2, sort_keys=False) + "\n")
            out_paths[f"evaluator:{ev.name}"] = out_path
        return out_paths
