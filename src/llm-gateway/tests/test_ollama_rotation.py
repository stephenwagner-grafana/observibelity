"""Unit tests for the Ollama lockstep model rotation.

The rotation is deterministic given (epoch_seconds, window_seconds, models),
so we patch ``time.time`` and assert the bucket math + model selection.

Why this matters: the "lockstep" guarantee is only useful if every replica
agrees on the same model at the same instant. These tests pin down the math
that gives that guarantee.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from app.providers.ollama import (
    OllamaProvider,
    _parse_rotation_models,
)


def _make_provider(env: dict[str, str]) -> OllamaProvider:
    """Build an OllamaProvider with env vars patched in."""
    with patch.dict(os.environ, env, clear=False):
        return OllamaProvider({"base_url": "http://stub:11434"})


def test_parse_rotation_models_handles_blanks_and_whitespace():
    assert _parse_rotation_models("a,b ,, c") == ["a", "b", "c"]
    assert _parse_rotation_models("") == []
    assert _parse_rotation_models(None) == []


def test_rotation_lockstep_same_bucket_same_model():
    """Two providers at the same wall clock pick the same model — lockstep."""
    env = {
        "OLLAMA_ROTATION_ENABLED": "true",
        "OLLAMA_ROTATION_WINDOW_SECONDS": "300",
        "OLLAMA_ROTATION_MODELS": "llama3.2:1b,phi3:mini,qwen2.5:7b",
    }
    p1 = _make_provider(env)
    p2 = _make_provider(env)
    # Pin time to mid-bucket so we are not flapping on the boundary.
    with patch("app.providers.ollama.time.time", return_value=1_700_000_000.0):
        m1, b1 = p1._current_rotation_model()
        m2, b2 = p2._current_rotation_model()
    assert m1 == m2
    assert b1 == b2


def test_rotation_advances_at_window_boundary():
    env = {
        "OLLAMA_ROTATION_ENABLED": "true",
        "OLLAMA_ROTATION_WINDOW_SECONDS": "300",
        "OLLAMA_ROTATION_MODELS": "a,b,c",
    }
    p = _make_provider(env)
    # Pick a starting epoch where bucket index in pool will be deterministic.
    base = 300 * 1_000_000  # exact bucket boundary
    with patch("app.providers.ollama.time.time", return_value=float(base)):
        m_now, b_now = p._current_rotation_model()
    with patch(
        "app.providers.ollama.time.time", return_value=float(base + 300)
    ):
        m_next, b_next = p._current_rotation_model()
    with patch(
        "app.providers.ollama.time.time", return_value=float(base + 600)
    ):
        m_after, b_after = p._current_rotation_model()
    # Buckets advance one per window.
    assert b_next == b_now + 1
    assert b_after == b_now + 2
    # And the model walks through the pool in order.
    pool = ["a", "b", "c"]
    assert m_now == pool[b_now % 3]
    assert m_next == pool[b_next % 3]
    assert m_after == pool[b_after % 3]
    assert m_now != m_next  # adjacent buckets differ for a 3-entry pool


def test_rotation_disabled_falls_back_to_default_model():
    env = {
        "OLLAMA_ROTATION_ENABLED": "false",
        "OLLAMA_ROTATION_MODELS": "a,b,c",
    }
    p = _make_provider(env)
    # Even though a pool exists, disabled means we return the static model.
    model, bucket = p._current_rotation_model()
    assert model == p.model
    assert bucket == 0


def test_rotation_with_empty_pool_falls_back_to_default():
    """No pool configured => act like a single-model provider."""
    env = {
        "OLLAMA_ROTATION_ENABLED": "true",
        "OLLAMA_ROTATION_MODELS": "",
    }
    p = _make_provider(env)
    model, _bucket = p._current_rotation_model()
    assert model == p.model
