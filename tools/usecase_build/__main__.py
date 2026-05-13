"""CLI entry point: usecase-build.

Discovers bundled use-case YAMLs, validates each via Pydantic + Compiler
cross-checks, then runs the Compiler to emit derived artifacts.

Exit code 0 on full success, 1 on any failure.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from .compiler import Compiler
from .schema import UseCase, UseCaseValidationError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="usecase-build",
        description="Compile bundled use-case YAMLs into chart artifacts.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("../registry/use_cases"),
        help=(
            "Path to a YAML file OR a directory of YAMLs "
            "(default: registry/use_cases/)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("../registry/_generated"),
        help="Where to write derived artifacts (default: registry/_generated/).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Just validate the YAML; don't emit.",
    )
    parser.add_argument(
        "--archetype-dir",
        type=Path,
        default=Path("usecase-templates"),
        help="Path to template packs (default: tools/usecase-templates/).",
    )
    parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Only compile use cases whose name matches this regex.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print every compiled artifact path.",
    )
    return parser


def _discover_yamls(path: Path) -> list[Path]:
    """Return YAML files under path (or just [path] if it's a file)."""
    if path.is_file():
        return [path]
    if not path.exists():
        return []
    yamls: list[Path] = []
    for ext in ("*.yaml", "*.yml"):
        yamls.extend(p for p in path.glob(ext) if not p.name.startswith("_"))
    return sorted(yamls)


def _load_use_case(yaml_path: Path) -> UseCase:
    raw = yaml.safe_load(yaml_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{yaml_path}: YAML root must be a mapping")
    return UseCase.model_validate(raw)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    pattern: re.Pattern | None = re.compile(args.filter) if args.filter else None

    yamls = _discover_yamls(args.input)
    if not yamls:
        print(f"usecase-build: no YAMLs found under {args.input}", file=sys.stderr)
        return 0

    compiler = Compiler(archetype_dir=args.archetype_dir, output_dir=args.output_dir)

    compiled = 0
    failed = 0
    skipped = 0

    for yaml_path in yamls:
        # Parse to get the name; load_use_case raises if invalid Pydantic.
        try:
            uc = _load_use_case(yaml_path)
        except (ValidationError, ValueError, yaml.YAMLError) as e:
            failed += 1
            print(f"FAIL  {yaml_path}: {e}", file=sys.stderr)
            continue

        if pattern and not pattern.search(uc.name):
            skipped += 1
            if args.verbose:
                print(f"SKIP  {yaml_path} (filter)")
            continue

        # Cross-cut validation.
        issues = compiler.validate(uc)
        if issues:
            failed += 1
            try:
                raise UseCaseValidationError(uc.name, issues)
            except UseCaseValidationError as e:
                print(f"FAIL  {yaml_path}: {e}", file=sys.stderr)
            continue

        if args.validate_only:
            compiled += 1
            print(f"OK    {yaml_path}  ({uc.name})")
            continue

        try:
            out_paths = compiler.compile(uc)
        except Exception as e:  # broad: emitters can raise anything
            failed += 1
            print(f"FAIL  {yaml_path}: emitter error: {e}", file=sys.stderr)
            continue

        compiled += 1
        print(f"OK    {yaml_path}  ({uc.name})  -> {len(out_paths)} artifact(s)")
        if args.verbose:
            for kind, p in out_paths.items():
                print(f"        {kind}: {p}")

    print(
        f"\nusecase-build: compiled={compiled} failed={failed} "
        f"skipped={skipped} total={len(yamls)}",
        file=sys.stderr,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
