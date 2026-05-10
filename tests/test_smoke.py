"""Tests for the model layer — no network/browser needed."""
from __future__ import annotations

from datetime import datetime, timezone

from qa_pilot.models import (
    AgentResult,
    Finding,
    Report,
    Severity,
    Verdict,
    Viewport,
)


def test_finding_emoji():
    f = Finding(id="t.1", agent="vega_smoke", severity=Severity.BLOCKER,
                title="x", description="y")
    assert f.emoji == "🔴"
    f.severity = Severity.MEDIUM  # type: ignore
    assert f.emoji == "🟡"


def test_report_verdict_rolls_up_to_red_on_blocker():
    now = datetime.now(timezone.utc)
    res = AgentResult(
        agent="vega_smoke", started_at=now, finished_at=now, success=True,
        findings=[Finding(id="x", agent="vega_smoke", severity=Severity.BLOCKER,
                          title="bad", description="bad")],
    )
    report = Report.from_agent_results(
        target_url="https://example.com",
        viewports=[Viewport()],
        results=[res],
        started_at=now,
    )
    assert report.verdict == Verdict.RED


def test_report_verdict_rolls_up_to_yellow_on_medium():
    now = datetime.now(timezone.utc)
    res = AgentResult(
        agent="iris_visual", started_at=now, finished_at=now, success=True,
        findings=[Finding(id="y", agent="iris_visual", severity=Severity.MEDIUM,
                          title="meh", description="meh")],
    )
    report = Report.from_agent_results(
        target_url="https://example.com",
        viewports=[Viewport()],
        results=[res],
        started_at=now,
    )
    assert report.verdict == Verdict.YELLOW


def test_report_verdict_green_when_no_findings():
    now = datetime.now(timezone.utc)
    res = AgentResult(agent="vega_smoke", started_at=now, finished_at=now, success=True)
    report = Report.from_agent_results(
        target_url="https://example.com",
        viewports=[Viewport()],
        results=[res],
        started_at=now,
    )
    assert report.verdict == Verdict.GREEN


def test_viewport_str():
    v = Viewport(width=1280, height=720, name="laptop")
    assert "laptop" in str(v) and "1280" in str(v)
