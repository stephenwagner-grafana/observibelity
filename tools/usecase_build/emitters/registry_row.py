"""RegistryRowEmitter — appends/updates a row in registry/use_cases.yaml.

Idempotent: replaces any existing entry with the same `name`. Writes the
file under output_dir (so a build into _generated/ doesn't clobber the
hand-edited registry); the caller may copy it into place.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..schema import UseCase


def _row_from_use_case(uc: UseCase) -> dict:
    return {
        "name": uc.name,
        "title": uc.title,
        "app": uc.app.value,
        "phase": uc.phase,
        "centerpiece": uc.centerpiece,
        "archetype": uc.archetype.value,
        "description": (uc.description or "").strip().split("\n", 1)[0],
        "scenario_count": len(uc.scenarios),
        "evaluator_count": len(uc.evaluators),
        "alert_count": len(uc.alerts),
        "has_slo": uc.slo is not None,
        "source": f"registry/use_cases/{uc.name}.yaml",
    }


class RegistryRowEmitter:
    """Idempotently writes a use-case row into the rolled-up registry."""

    artifact_kind = "registry"

    def emit(
        self,
        use_case: UseCase,
        archetype_path: Path,
        output_dir: Path,
    ) -> dict[str, Path]:
        out_dir = output_dir / "registry"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "use_cases.yaml"

        # Read existing doc, if any.
        doc: dict = {"use_cases": []}
        if out_path.exists():
            try:
                loaded = yaml.safe_load(out_path.read_text()) or {}
                if isinstance(loaded, dict) and isinstance(loaded.get("use_cases"), list):
                    doc = loaded
            except yaml.YAMLError:
                # Corrupt — start over rather than silently merging junk.
                doc = {"use_cases": []}

        rows = doc.get("use_cases") or []
        # Drop existing row with same name (idempotent re-write).
        rows = [r for r in rows if not (isinstance(r, dict) and r.get("name") == use_case.name)]
        rows.append(_row_from_use_case(use_case))
        # Keep deterministic ordering by phase then name.
        rows.sort(key=lambda r: (r.get("phase", 99), r.get("name", "")))
        doc["use_cases"] = rows

        with out_path.open("w") as f:
            yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)
        return {"registry": out_path}
