"""Shared pytest fixtures for ObserVIBElity Phase 0 tests."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Make the deploy-doctor package importable.
REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


@pytest.fixture
def temp_repo(tmp_path):
    """Create a minimal repo skeleton under tmp_path for tests that need one."""
    (tmp_path / "Chart.yaml").write_text("name: observibelity\nversion: 0.1.0\n")
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=test\n")
    (tmp_path / "tools").mkdir(exist_ok=True)
    (tmp_path / ".observibelity-state").mkdir(exist_ok=True)
    return tmp_path


@pytest.fixture
def mock_kubectl(mocker):
    """Patch subprocess.run so kubectl invocations return canned output."""

    def fake_run(args, **kw):  # noqa: ANN001 — mirrors subprocess.run signature
        # Normalize args to a list
        argv = list(args) if not isinstance(args, str) else args.split()
        if argv and argv[0] == "kubectl":
            if len(argv) >= 3 and argv[1] == "get" and argv[2] == "events":
                return subprocess.CompletedProcess(
                    args=argv, returncode=0, stdout="No events", stderr=""
                )
            if len(argv) >= 2 and argv[1] == "get":
                return subprocess.CompletedProcess(
                    args=argv, returncode=0, stdout="No resources found", stderr=""
                )
            # Generic kubectl success
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout="", stderr=""
            )
        if argv and argv[0] == "helm":
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout="STATUS: deployed", stderr=""
            )
        # Default: empty success
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout="", stderr=""
        )

    return mocker.patch("subprocess.run", side_effect=fake_run)


@pytest.fixture
def sample_collect_output():
    """Plausible output shape from Collector.collect()."""
    return {
        "kubectl_events": "LAST SEEN   TYPE      REASON\n5m          Normal    Pulled",
        "helm_status": "NAME: obs\nSTATUS: deployed",
        "pods": "NAME      READY   STATUS\nobs-0     1/1     Running",
    }
