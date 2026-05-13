"""ScenarioEmitter — emits k6 JS scenarios + ConfigMap manifests.

For each scenario in the use case, reads the archetype's k6 template (by
default `<archetype_dir>/k6_template.js`, optionally narrowed by the
scenario's `k6_template` field as a suffix), substitutes params via
string.Template, writes the JS to `scenarios/<uc>.<scn>.js`, and a k8s
ConfigMap referencing that script at `scenarios/<uc>.<scn>.cm.yaml`.
"""
from __future__ import annotations

from pathlib import Path
from string import Template

import yaml

from ..schema import UseCase, Scenario


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


def _render_template(text: str, mapping: dict[str, str]) -> str:
    """Apply string.Template substitution (handles missing keys safely)."""
    return Template(text).safe_substitute(mapping)


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
            mapping = {
                "use_case": use_case.name,
                "scenario": scn.name,
                "persona": scn.persona or "",
                "weight": str(scn.weight),
                "rate": scn.rate,
                "app": use_case.app.value,
                # Spread params as top-level vars too, stringifying as needed.
                **{k: str(v) for k, v in scn.params.items()},
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
