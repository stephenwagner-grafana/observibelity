"""DashboardEmitter — emits Grafana dashboard JSON.

Reads `<archetype_dir>/dashboard_panels.json` as the template panel pack,
interpolates use-case-specific variables, appends `extra_panels`, and
emits a complete Grafana dashboard JSON to `dashboards/<uid>.json`.

If the archetype's template pack is missing, falls back to a minimal
single-row dashboard so the compiler stays usable while template packs
are being authored in parallel.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..schema import UseCase


_VAR_PATTERN = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _substitute(node: Any, vars: dict[str, str]) -> Any:
    """Walk a JSON-shaped tree and replace ${var} tokens in strings.

    Lists and dicts are walked recursively. Non-string scalars are passed
    through unchanged. Unknown variables are left as-is (so authors notice).
    """
    if isinstance(node, str):
        return _VAR_PATTERN.sub(lambda m: vars.get(m.group(1), m.group(0)), node)
    if isinstance(node, list):
        return [_substitute(item, vars) for item in node]
    if isinstance(node, dict):
        return {k: _substitute(v, vars) for k, v in node.items()}
    return node


def _minimal_dashboard(use_case: UseCase, title: str, uid: str) -> dict:
    """Fallback dashboard when the archetype has no dashboard_panels.json."""
    return {
        "uid": uid,
        "title": title,
        "tags": ["ai-observability", f"use_case:{use_case.name}", f"app:{use_case.app.value}"],
        "schemaVersion": 39,
        "version": 1,
        "panels": [
            {
                "id": 1,
                "type": "row",
                "title": f"{title} — placeholder (template pack not found)",
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
            }
        ],
    }


class DashboardEmitter:
    """Emits one Grafana dashboard JSON per use case (if `dashboard` set)."""

    artifact_kind = "dashboards"

    def __init__(self, archetype_dir: Path) -> None:
        self.archetype_dir = archetype_dir

    def emit(
        self,
        use_case: UseCase,
        archetype_path: Path,
        output_dir: Path,
    ) -> dict[str, Path]:
        if use_case.dashboard is None:
            return {}

        dash = use_case.dashboard
        out_dir = output_dir / "dashboards"
        out_dir.mkdir(parents=True, exist_ok=True)

        title = dash.title or use_case.title
        uid = dash.uid

        # Try to load a panel pack from the archetype, optionally narrowed
        # by `panels_from_template` (which becomes a filename suffix).
        panel_pack: dict | None = None
        candidates: list[Path] = []
        if dash.panels_from_template:
            candidates.append(archetype_path / f"dashboard_panels.{dash.panels_from_template}.json")
        candidates.append(archetype_path / "dashboard_panels.json")
        for c in candidates:
            if c.exists():
                try:
                    panel_pack = json.loads(c.read_text())
                except json.JSONDecodeError as e:
                    raise ValueError(f"failed to parse panel pack {c}: {e}") from e
                break

        if panel_pack is None:
            dashboard_obj = _minimal_dashboard(use_case, title, uid)
        else:
            dashboard_obj = dict(panel_pack)
            dashboard_obj.setdefault("uid", uid)
            dashboard_obj["uid"] = uid
            dashboard_obj["title"] = title

        # Interpolate vars across the whole structure.
        vars_ = {
            "name": use_case.name,
            "title": title,
            "uid": uid,
            "app": use_case.app.value,
            "archetype": use_case.archetype.value,
            "phase": str(use_case.phase),
        }
        dashboard_obj = _substitute(dashboard_obj, vars_)

        # Append extra_panels (already raw Grafana panel dicts).
        if dash.extra_panels:
            panels = list(dashboard_obj.get("panels", []))
            panels.extend(dash.extra_panels)
            dashboard_obj["panels"] = panels

        # Stamp our standard tags.
        tags = set(dashboard_obj.get("tags", []) or [])
        tags.update(
            {
                "ai-observability",
                f"use_case:{use_case.name}",
                f"app:{use_case.app.value}",
                f"archetype:{use_case.archetype.value}",
            }
        )
        dashboard_obj["tags"] = sorted(tags)

        out_path = out_dir / f"{uid}.json"
        out_path.write_text(json.dumps(dashboard_obj, indent=2) + "\n")
        return {"dashboard": out_path}
