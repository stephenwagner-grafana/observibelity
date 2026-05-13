"""Tests for tools/deploy-doctor/collect.py."""
from __future__ import annotations

import importlib
import json
import os
import tarfile

import pytest


def _try_import(modname: str):
    try:
        return importlib.import_module(modname)
    except ImportError as e:
        pytest.skip(f"{modname} not yet present (Phase 0 scaffold): {e}")


def _get_collector():
    mod = _try_import("deploy_doctor.collect")
    return getattr(mod, "Collector")


def test_collector_init():
    Collector = _get_collector()
    c = Collector(namespace="test", release="test")
    assert c.namespace == "test"


def test_redact_secrets():
    mod = _try_import("deploy_doctor.collect")
    redact = getattr(mod, "_redact", None)
    if redact is None:
        # Some scaffolds expose the helper as a Collector method
        Collector = getattr(mod, "Collector")
        redact = getattr(Collector, "_redact", None)
    if redact is None:
        pytest.skip("_redact helper not yet implemented (Phase 0 scaffold)")
    sample = "ANTHROPIC_API_KEY=sk-ant-abc-123\nGITHUB_TOKEN=ghp_secret\n"
    out = redact(sample)
    assert "sk-ant-abc-123" not in out
    assert "ghp_secret" not in out
    assert "REDACTED" in out


def test_bundle_writes_tar(temp_repo, mock_kubectl):
    Collector = _get_collector()
    c = Collector(namespace="x", release="x")
    out_path = str(temp_repo / "out.tar.gz")
    path = c.bundle(out_path)
    assert os.path.exists(path)
    with tarfile.open(path) as t:
        names = t.getnames()
        assert any("kubectl_events" in n for n in names)


def test_collect_state_file_redacts(temp_repo):
    mod = _try_import("deploy_doctor.collect")
    redact = getattr(mod, "_redact", None)
    if redact is None:
        Collector = getattr(mod, "Collector")
        redact = getattr(Collector, "_redact", None)
    if redact is None:
        pytest.skip("_redact helper not yet implemented (Phase 0 scaffold)")

    state = {
        "inputs": {
            "anthropic_key": "sk-ant-real-key-value",
            "github_org": "myorg",
        }
    }
    state_file = temp_repo / ".observibelity-state" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state))

    redacted = redact(state_file.read_text())
    assert "sk-ant-real-key-value" not in redacted
    # Non-sensitive fields should survive
    assert "myorg" in redacted
