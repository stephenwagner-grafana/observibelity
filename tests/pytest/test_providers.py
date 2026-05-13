"""Tests for tools/deploy-doctor/providers/."""
from __future__ import annotations

import importlib
import pytest


def _try_import(modname: str):
    """Try to import a module; if it doesn't exist yet (Phase 0), skip."""
    try:
        return importlib.import_module(modname)
    except ImportError as e:
        pytest.skip(f"{modname} not yet present (Phase 0 scaffold): {e}")


def test_provider_is_abstract():
    base = _try_import("deploy_doctor.providers.base")
    Provider = getattr(base, "Provider")
    with pytest.raises(TypeError):
        Provider()  # type: ignore[abstract]


def test_suggestion_dataclass():
    base = _try_import("deploy_doctor.providers.base")
    Suggestion = getattr(base, "Suggestion")
    Urgency = getattr(base, "Urgency")
    s = Suggestion(text="run kubectl", command="kubectl get pods")
    assert s.urgency == Urgency.MEDIUM
    assert s.confidence == 0.5


def test_anthropic_diagnose_raises_phase0():
    anthropic_mod = _try_import("deploy_doctor.providers.anthropic")
    AnthropicProvider = getattr(anthropic_mod, "AnthropicProvider")
    with pytest.raises(NotImplementedError, match="Phase 1"):
        AnthropicProvider().diagnose({}, "")


def test_ollama_diagnose_raises_phase0():
    ollama_mod = _try_import("deploy_doctor.providers.ollama")
    OllamaProvider = getattr(ollama_mod, "OllamaProvider")
    with pytest.raises(NotImplementedError, match="Phase 1"):
        OllamaProvider().diagnose({}, "")


def test_make_provider_unknown_raises():
    providers = _try_import("deploy_doctor.providers")
    make_provider = getattr(providers, "make_provider")
    with pytest.raises(ValueError):
        make_provider("nonexistent")
