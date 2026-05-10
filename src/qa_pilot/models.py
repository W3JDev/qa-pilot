"""Pydantic models — the canonical typed surface for findings, agents, reports."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Core types
# -----------------------------------------------------------------------------


class Severity(str, Enum):
    """Finding severity, mapped to verdict color."""
    BLOCKER = "blocker"        # 🔴 — release stops here
    MEDIUM = "medium"          # 🟡 — ship with follow-up
    LOW = "low"                # 🟢 — polish item
    INFO = "info"              # ⚪ — observation, not a problem


class Verdict(str, Enum):
    GREEN = "green"            # 🟢 ship-ready
    YELLOW = "yellow"          # 🟡 ship with issues
    RED = "red"                # 🔴 blockers found


class Viewport(BaseModel):
    """Browser viewport spec."""
    width: int = 1440
    height: int = 900
    name: str = "desktop"      # "desktop" | "tablet" | "mobile" | etc.

    def __str__(self) -> str:
        return f"{self.name} ({self.width}×{self.height})"


# -----------------------------------------------------------------------------
# Findings
# -----------------------------------------------------------------------------


class Finding(BaseModel):
    """One actionable observation from an agent."""
    id: str = Field(..., description="Stable id, prefixed with agent name")
    agent: str = Field(..., description="Which agent produced this")
    severity: Severity
    title: str = Field(..., max_length=200)
    description: str
    repro_steps: list[str] = Field(default_factory=list)
    evidence_screenshot: str | None = Field(
        default=None,
        description="Path or URL to a screenshot supporting the finding",
    )
    evidence_url: str | None = Field(
        default=None,
        description="The URL where the issue was observed",
    )
    suggested_fix: str | None = None
    tags: list[str] = Field(default_factory=list)

    @property
    def emoji(self) -> str:
        return {
            Severity.BLOCKER: "🔴",
            Severity.MEDIUM: "🟡",
            Severity.LOW: "🟢",
            Severity.INFO: "⚪",
        }[self.severity]


# -----------------------------------------------------------------------------
# Agent results + final report
# -----------------------------------------------------------------------------


class AgentResult(BaseModel):
    """One agent's output from a run."""
    agent: str
    started_at: datetime
    finished_at: datetime
    success: bool                      # did the agent complete without error
    findings: list[Finding] = Field(default_factory=list)
    artifacts: list[str] = Field(
        default_factory=list,
        description="Paths/URLs to saved screenshots, video clips, etc.",
    )
    summary: str = ""

    @property
    def duration_sec(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


class Report(BaseModel):
    """Final consolidated report from a QA run."""
    target_url: str
    viewports: list[Viewport]
    agents_run: list[str]
    started_at: datetime
    finished_at: datetime
    verdict: Verdict
    summary: str
    agent_results: list[AgentResult] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)

    @classmethod
    def from_agent_results(
        cls,
        target_url: str,
        viewports: list[Viewport],
        results: list[AgentResult],
        started_at: datetime,
    ) -> "Report":
        all_findings = [f for r in results for f in r.findings]
        sev_counts = {s: 0 for s in Severity}
        for f in all_findings:
            sev_counts[f.severity] += 1

        if sev_counts[Severity.BLOCKER] > 0:
            verdict = Verdict.RED
        elif sev_counts[Severity.MEDIUM] > 0:
            verdict = Verdict.YELLOW
        else:
            verdict = Verdict.GREEN

        summary = (
            f"{sev_counts[Severity.BLOCKER]} blocker · "
            f"{sev_counts[Severity.MEDIUM]} medium · "
            f"{sev_counts[Severity.LOW]} low · "
            f"{sev_counts[Severity.INFO]} info"
        )

        return cls(
            target_url=target_url,
            viewports=viewports,
            agents_run=[r.agent for r in results],
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            verdict=verdict,
            summary=summary,
            agent_results=results,
            findings=all_findings,
        )


# -----------------------------------------------------------------------------
# Run config (loaded from YAML)
# -----------------------------------------------------------------------------


class JourneyStep(BaseModel):
    action: Literal["click", "type", "scroll", "wait", "assert", "navigate", "screenshot"]
    target: str | None = None          # natural-language description
    text: str | None = None             # for type
    contains: str | None = None         # for assert
    url: str | None = None              # for navigate
    selector: str | None = None         # explicit selector override


class Journey(BaseModel):
    name: str
    steps: list[JourneyStep]


class ReportDestination(BaseModel):
    type: Literal["file", "github_pr_comment", "slack", "telegram", "stdout"]
    path: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class ReportConfig(BaseModel):
    formats: list[Literal["markdown", "json"]] = Field(default_factory=lambda: ["markdown"])
    destinations: list[ReportDestination] = Field(
        default_factory=lambda: [ReportDestination(type="stdout")]
    )


class RunConfig(BaseModel):
    """The full YAML-loadable run definition."""
    target_url: str
    viewports: list[Viewport] = Field(default_factory=lambda: [Viewport()])
    agents: list[str] = Field(
        default_factory=lambda: ["vega_smoke", "iris_visual", "sage_aesthetic"]
    )
    journeys: list[Journey] = Field(default_factory=list)
    report: ReportConfig = Field(default_factory=ReportConfig)
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="Pluggable via litellm — e.g. gpt-4o, claude-sonnet-4.5, gemini-2.5-flash",
    )
    timeout_sec: int = 120
