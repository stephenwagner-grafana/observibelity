"""Tests for the reset_password tool."""
from __future__ import annotations

import pytest

from app.tool import ResetPassword, ResetPasswordArgs


def test_knobs():
    assert ResetPassword.NAME == "reset_password"
    assert ResetPassword.SIDE_EFFECT is True
    assert ResetPassword.IDEMPOTENT is True
    assert ResetPassword.BACKING_TABLES == []
    assert "sb-it-troubleshoot" in ResetPassword.ALLOWED_CALLERS


@pytest.mark.asyncio
async def test_execute_returns_queued():
    tool = ResetPassword.__new__(ResetPassword)
    res = await tool.execute(ResetPasswordArgs(persona_id="alice"), None)
    assert res.status == "queued"
    assert res.persona_id == "alice"
    assert res.method == "email"


@pytest.mark.asyncio
async def test_execute_custom_method():
    tool = ResetPassword.__new__(ResetPassword)
    res = await tool.execute(ResetPasswordArgs(persona_id="3", method="sms"), None)
    assert res.method == "sms"
