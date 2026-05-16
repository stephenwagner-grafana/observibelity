"""Retired tests — the prewarm task has been replaced by the model-pool
scheduler. Behavior coverage moved to ``test_scheduler.py``.

This file is kept as an explicit no-op so the test runner doesn't fail on
a missing module and so the deletion is auditable in code review.
"""
from __future__ import annotations


def test_prewarm_module_is_a_stub() -> None:
    """The old PrewarmTask class is a no-op shim now — assert that."""
    from app.prewarm import PrewarmTask, maybe_start_prewarm

    assert maybe_start_prewarm() is None
    task = PrewarmTask()
    assert task.models == []
    assert task.window == 0
