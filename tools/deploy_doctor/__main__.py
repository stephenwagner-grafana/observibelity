"""CLI entry point for deploy-doctor.

Phase 0: --collect-only is the default. Bundles diagnostics into a tarball
the user attaches to a GitHub issue.

Phase 1: --diagnose will call a Provider (Claude or Ollama) and print
concrete suggestions.
"""
from __future__ import annotations

import argparse
import sys

from .collect import Collector
from .diagnose import Diagnoser
from .providers import make_provider


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deploy-doctor",
        description=(
            "Collect ObserVIBElity deployment diagnostics. "
            "Phase 0 produces a tarball; Phase 1 will additionally diagnose via LLM."
        ),
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Phase 0 default; just collect diagnostics into a tarball.",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Phase 1 only; call the configured Provider and print suggestions.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Where to write the diagnostics tarball.",
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "ollama"],
        default="anthropic",
        help="Which Provider to use when --diagnose is set.",
    )
    parser.add_argument(
        "--include-secrets",
        action="store_true",
        help="Do NOT redact secrets in collected output (default: redact).",
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default="observibelity",
        help="Kubernetes namespace to inspect.",
    )
    parser.add_argument(
        "--release",
        type=str,
        default="observibelity",
        help="Helm release name to inspect.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    collector = Collector(
        namespace=args.namespace,
        release=args.release,
        redact_secrets=not args.include_secrets,
    )

    # Phase 0: collect-only is the safe default. Even if neither flag is set
    # we behave as a collector, because that's the failure-recovery path.
    if args.collect_only or not args.diagnose:
        bundle_path = collector.bundle(args.output)
        print(f"Diagnostics collected at: {bundle_path}")
        return 0

    # --diagnose path. In Phase 0 the Diagnoser raises NotImplementedError;
    # we catch that and emit a friendly message so the caller knows to fall
    # back to --collect-only.
    try:
        provider = make_provider(args.provider)
        diagnoser = Diagnoser(collector, provider)
        result = diagnoser.diagnose()
        print(result.summary)
        for i, suggestion in enumerate(result.suggestions, start=1):
            print(f"\n{i}. [{suggestion.urgency.value}] {suggestion.text}")
            if suggestion.command:
                print(f"   $ {suggestion.command}")
        return 0
    except NotImplementedError as exc:
        print(f"deploy-doctor: {exc}", file=sys.stderr)
        print(
            "Run again with --collect-only to produce a diagnostics tarball.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
