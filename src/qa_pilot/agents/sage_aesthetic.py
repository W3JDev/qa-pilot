"""Sage — Aesthetic Critic.

Iris flags functional issues. Sage critiques the design language. Looks at
homepage screenshots through the lens of "would a top-5 SV product team
ship this?"

Outputs are LOW severity by default — design polish, not blockers.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from qa_pilot.agents.base import Agent
from qa_pilot.browser import BrowserSession
from qa_pilot.llm import vision
from qa_pilot.models import AgentResult, Finding, Severity


SYSTEM = (
    "You are Sage — a product design critic with senior taste. Compared to "
    "Linear, Vercel, Pi.ai, Arc, Stripe, you call out where this looks "
    "amateur or AI-built vs. where it lands. You are kind but exacting. "
    "Output a JSON array of design observations. Schema: "
    "[{\"severity\":\"medium|low|info\",\"title\":\"<short>\","
    "\"description\":\"<1-2 sentences>\",\"suggested_fix\":\"<concise>\"}]. "
    "No markdown wrapping. Empty array [] if it's already excellent."
)

USER_TEMPLATE = (
    "Critique this screenshot of {target_url} at {viewport}.\n"
    "Focus on:\n"
    "  • typographic hierarchy (sizes, weights, contrast)\n"
    "  • spacing rhythm — too tight, too loose, irregular?\n"
    "  • color discipline — accent overuse, gradients without purpose\n"
    "  • motion / animation that's clearly mid-frame and looks broken\n"
    "  • 'AI-built tells' — generic icon clusters, neon glows on tech topics, "
    "    over-saturated dashboards, copy that says 'leverage' or 'streamline'\n"
    "  • copy that breaks immersion (over-cheerful greeting, robotic CTA)\n"
    "Be SPECIFIC — name the element. No generic feedback."
)


class SageAesthetic(Agent):
    name = "sage_aesthetic"

    async def run(self) -> AgentResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        artifacts: list[str] = []

        # Sage works on the desktop viewport only by default — design issues
        # at desktop tend to telegraph the rest. (Mobile-specific design crit
        # could be its own agent if there's demand.)
        viewport = next(
            (v for v in self.config.viewports if v.name == "desktop"),
            self.config.viewports[0] if self.config.viewports else None,
        )
        if viewport is None:
            return AgentResult(
                agent=self.name, started_at=started,
                finished_at=datetime.now(timezone.utc),
                success=True, findings=[], summary="no viewport configured",
            )

        async with BrowserSession(
            viewport=viewport,
            artifacts_dir=self.artifacts_dir,
            run_label="sage",
        ) as session:
            try:
                await session.goto(self.config.target_url, wait_until="networkidle", timeout_ms=20_000)
                shot_path = await session.screenshot("design_review", full_page=True)
                artifacts.append(str(shot_path))
            except Exception as e:
                return AgentResult(
                    agent=self.name, started_at=started,
                    finished_at=datetime.now(timezone.utc),
                    success=False,
                    summary=f"render failed: {type(e).__name__}: {e}",
                )

            review = await vision(
                USER_TEMPLATE.format(
                    target_url=self.config.target_url,
                    viewport=viewport,
                ),
                shot_path,
                model=self.config.llm_model,
                system=SYSTEM,
                max_tokens=2000,
            )
            cleaned = review.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```", 2)[-1].lstrip("json\n").rstrip("`").strip()
            try:
                items = json.loads(cleaned)
                if not isinstance(items, list):
                    items = []
            except Exception:
                items = []

            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                sev_str = str(item.get("severity", "low")).lower()
                # Sage downgrades anything claimed as 'blocker' to 'medium' —
                # design is rarely a release blocker.
                sev = {
                    "blocker": Severity.MEDIUM,
                    "medium": Severity.MEDIUM,
                    "low": Severity.LOW,
                    "info": Severity.INFO,
                }.get(sev_str, Severity.LOW)
                findings.append(Finding(
                    id=f"sage.{viewport.name}.{i}",
                    agent=self.name,
                    severity=sev,
                    title=str(item.get("title", "Design observation"))[:200],
                    description=str(item.get("description", ""))[:1000],
                    evidence_screenshot=str(shot_path),
                    evidence_url=self.config.target_url,
                    suggested_fix=item.get("suggested_fix"),
                    tags=["design", viewport.name],
                ))

        return AgentResult(
            agent=self.name,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            success=True,
            findings=findings,
            artifacts=artifacts,
            summary=f"design review: {len(findings)} note(s)",
        )
