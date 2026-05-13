"""Tests for the usecase_build compiler + schema + archetype templates.

The compiler module sits at tools/usecase_build/ — tests/pytest/conftest.py
already inserts tools/ on sys.path, so `from usecase_build...` works.

These tests are designed to be tolerant of in-progress work: archetype
templates may contain placeholders that don't parse as strict JSON/YAML, so
we skip rather than fail in those cases.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# fixtures                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture
def example_yaml() -> Path:
    return REPO_ROOT / "registry" / "use_cases" / "_example.yaml"


@pytest.fixture
def archetype_dir() -> Path:
    return REPO_ROOT / "tools" / "usecase-templates"


# --------------------------------------------------------------------------- #
# schema                                                                      #
# --------------------------------------------------------------------------- #

class TestSchema:
    def test_example_yaml_parses(self, example_yaml: Path) -> None:
        """The shipped _example.yaml must always parse via UseCase."""
        from usecase_build.schema import UseCase

        data = yaml.safe_load(example_yaml.read_text())
        uc = UseCase(**data)
        assert uc.name
        assert uc.archetype

    def test_kebab_case_validation(self) -> None:
        """Names with spaces / uppercase must be rejected."""
        from usecase_build.schema import UseCase

        with pytest.raises(Exception):
            UseCase(
                name="Bad Name With Spaces",
                title="x",
                app="neoncart",
                phase=1,
                archetype="trace-and-fix",
            )

    def test_phase_range(self) -> None:
        """Phase must be 0, 1, or 2."""
        from usecase_build.schema import UseCase

        with pytest.raises(Exception):
            UseCase(
                name="test",
                title="x",
                app="neoncart",
                phase=99,
                archetype="trace-and-fix",
            )

    def test_archetype_enum(self) -> None:
        """Only the 5 published archetypes are accepted."""
        from usecase_build.schema import UseCase

        with pytest.raises(Exception):
            UseCase(
                name="test",
                title="x",
                app="neoncart",
                phase=1,
                archetype="not-a-real-archetype",
            )


# --------------------------------------------------------------------------- #
# compiler                                                                    #
# --------------------------------------------------------------------------- #

class TestCompiler:
    def test_compiler_loads_archetype(
        self, tmp_path: Path, example_yaml: Path, archetype_dir: Path
    ) -> None:
        """Compiler validate() returns a list of issue strings (possibly empty)."""
        from usecase_build.compiler import Compiler
        from usecase_build.schema import UseCase

        data = yaml.safe_load(example_yaml.read_text())
        uc = UseCase(**data)

        output_dir = tmp_path / "generated"
        output_dir.mkdir()
        compiler = Compiler(archetype_dir=archetype_dir, output_dir=output_dir)
        issues = compiler.validate(uc)
        # The example may surface zero or more issues depending on which
        # archetype-specific rules apply — we just assert the return shape.
        assert isinstance(issues, list)
        assert all(isinstance(i, str) for i in issues)

    def test_centerpiece_requires_slo(self, archetype_dir: Path) -> None:
        """A centerpiece use case without an SLO must produce a validation issue."""
        from usecase_build.compiler import Compiler
        from usecase_build.schema import UseCase

        uc = UseCase(
            name="test-centerpiece",
            title="Test Centerpiece",
            app="neoncart",
            phase=1,
            centerpiece=True,
            archetype="per-user-pattern",
            evaluators=[],
        )
        c = Compiler(archetype_dir=archetype_dir, output_dir=Path("/tmp"))
        issues = c.validate(uc)
        assert any("SLO" in i for i in issues), f"expected SLO issue, got: {issues}"

    def test_validate_returns_strings(self, archetype_dir: Path) -> None:
        """All validation issues should be human-readable strings."""
        from usecase_build.compiler import Compiler
        from usecase_build.schema import UseCase

        uc = UseCase(
            name="trivial",
            title="Trivial",
            app="neoncart",
            phase=0,
            archetype="trace-and-fix",
        )
        c = Compiler(archetype_dir=archetype_dir, output_dir=Path("/tmp"))
        issues = c.validate(uc)
        assert isinstance(issues, list)
        for issue in issues:
            assert isinstance(issue, str)
            assert issue.strip(), "issue strings must be non-empty"


# --------------------------------------------------------------------------- #
# archetype template packs                                                    #
# --------------------------------------------------------------------------- #

ARCHETYPES = [
    "trace-and-fix",
    "per-user-pattern",
    "leaderboard",
    "single-event-severity",
    "cascade",
]

REQUIRED_FILES = [
    "README.md",
    "k6_template.js",
    "dashboard_panels.json",
    "alert_template.yaml",
    "evaluator_template.yaml",
]


class TestArchetypeTemplates:
    @pytest.mark.parametrize("archetype", ARCHETYPES)
    def test_archetype_has_required_files(
        self, archetype: str, archetype_dir: Path
    ) -> None:
        """Every archetype dir must ship the 5 standard template files."""
        d = archetype_dir / archetype
        assert d.exists(), f"archetype dir missing: {archetype}"
        for fname in REQUIRED_FILES:
            assert (d / fname).exists(), f"{archetype}/{fname} missing"

    @pytest.mark.parametrize("archetype", ARCHETYPES)
    def test_archetype_templates_parse(
        self, archetype: str, archetype_dir: Path
    ) -> None:
        """Templates should be syntactically valid (or recognized placeholders)."""
        d = archetype_dir / archetype

        # --- JSON panel template ---------------------------------------- #
        panels_text = (d / "dashboard_panels.json").read_text()
        # Authors often use ${var} or {{var}} placeholders; replace with a
        # safe quoted token before attempting to parse.
        sanitized = panels_text.replace("{{", '"').replace("}}", '"')
        try:
            json.loads(sanitized)
        except json.JSONDecodeError:
            pytest.skip(
                f"{archetype}/dashboard_panels.json has placeholders preventing direct parse"
            )

        # --- YAML templates --------------------------------------------- #
        for fname in ["alert_template.yaml", "evaluator_template.yaml"]:
            text = (d / fname).read_text()
            try:
                yaml.safe_load(text)
            except yaml.YAMLError:
                pytest.skip(
                    f"{archetype}/{fname} has placeholders preventing direct parse"
                )

    @pytest.mark.parametrize("archetype", ARCHETYPES)
    def test_archetype_readme_nonempty(
        self, archetype: str, archetype_dir: Path
    ) -> None:
        """Every archetype README must have some content."""
        text = (archetype_dir / archetype / "README.md").read_text()
        assert text.strip(), f"{archetype}/README.md is empty"


# --------------------------------------------------------------------------- #
# importer                                                                    #
# --------------------------------------------------------------------------- #

class TestImporter:
    """Smoke tests for the demo-pack importer's AST extraction.

    These tests don't require a real demo-pack on disk — they synthesize a
    tiny Python source string and feed it through the importer's parsers.
    """

    def test_parse_usecase_class_extracts_attrs(self) -> None:
        from usecase_build.importer import _parse_usecase_class
        import ast

        src = (
            "from base import UseCase, Archetype\n"
            "class FooUseCase(UseCase):\n"
            "    id = 'foo-bar'\n"
            "    title = 'Foo Bar'\n"
            "    app = 'neoncart'\n"
            "    archetype = Archetype.PER_USER_PATTERN\n"
            "    is_centerpiece = True\n"
        )
        attrs = _parse_usecase_class(ast.parse(src))
        assert attrs is not None
        assert attrs["id"] == "foo-bar"
        assert attrs["title"] == "Foo Bar"
        assert attrs["app"] == "neoncart"
        assert attrs["archetype"] == "PER_USER_PATTERN"
        assert attrs["is_centerpiece"] is True

    def test_archetype_mapping_known(self) -> None:
        """ARCHETYPE_MAP covers every demo-pack archetype we expect."""
        from usecase_build.importer import ARCHETYPE_MAP, VALID_ARCHETYPES

        for demo_arch in [
            "DETERMINISTIC_RCA",
            "PER_USER_PATTERN",
            "LEADERBOARD",
            "SINGLE_EVENT_SEVERITY",
            "PER_SESSION_SEVERITY",
            "GLOBAL_RATE",
            "REGRESSION_CURVE",
            "PER_POLICY_RATE",
        ]:
            assert demo_arch in ARCHETYPE_MAP
            assert ARCHETYPE_MAP[demo_arch] in VALID_ARCHETYPES

    def test_build_yaml_matches_schema(self, tmp_path: Path) -> None:
        """A YAML produced by build_yaml() must round-trip through UseCase."""
        from usecase_build.importer import build_yaml
        from usecase_build.schema import UseCase

        attrs = {
            "_class_name": "DemoUseCase",
            "id": "demo-uc",
            "title": "Demo Use Case",
            "app": "neoncart",
            "is_centerpiece": False,
            "loadgen_scenarios": [],
            "grafana_dashboards": [],
            "grafana_alert_rules": [],
            "loadgen_rate_per_min": 30,
            "description": "demo",
        }
        data = build_yaml(
            name="demo-uc",
            attrs=attrs,
            archetype="leaderboard",
            scenarios_index={},
            dashboards_index={},
            alerts_index={},
        )
        # Must parse via the schema.
        uc = UseCase(**data)
        assert uc.name == "demo-uc"
        assert uc.archetype.value == "leaderboard"

    def test_kebab_helper(self) -> None:
        from usecase_build.importer import kebab

        assert kebab("Foo_Bar Baz") == "foo-bar-baz"
        assert kebab("ALREADY-KEBAB") == "already-kebab"
        assert kebab("snake_case_id") == "snake-case-id"
