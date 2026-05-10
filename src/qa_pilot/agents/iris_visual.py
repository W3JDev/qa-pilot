"""Iris — Visual Inspector.

Captures full-page screenshots at every configured viewport and runs each
through a vision LLM for layout / readability / asset issues.

Future enhancement: visual regression diffing against baselines stored in S3
or a git LFS path. v0.1 is "describe what you see and flag obvious issues."
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from qa_pilot.agents.base import Agent
from qa_pilot.browser import BrowserSession
from qa_pilot.llm import vision
from qa_pilot.models import AgentResult, Finding, Severity


SYSTEM = (
    "You are Iris — a senior front-end QA inspector. Look at the screenshot "
    "and identify visible issues that would harm UX. Be specific. Output "
    "STRICTLY a JSON array, one object per finding. "
    "Schema: [{\"severity\":\"blocker|medium|low|info\",\"title\":\"<short>\","
    "\"description\":\"<1-2 sentences>\",\"suggested_fix\":\"<concise>\"}]. "
    "Empty array [] if nothing is wrong. Do NOT wrap in markdown."
)

USER_TEMPLATE = (
    "Inspect this screenshot of {target_url} at the {viewport} viewport.\n"
    "Look for: layout overflow, broken images, contrast issues, off-center "
    "elements, missing assets, text clipping, illegible labels, motion bugs "
    "frozen mid-frame, console errors visible on screen, anything that says "
    "'AI-built and not polished'. Be specific — name the element."
)


class IrisVisual(Agent):
    name = "iris_visual"

    async def run(self) -> AgentResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        artifacts: list[str] = []

        for viewport in self.config.viewports:
            async with BrowserSession(
                viewport=viewport,
                artifacts_dir=self.artifacts_dir,
                run_label="iris",
            ) as session:
                try:
                    await session.goto(self.config.target_url, wait_until="networkidle", timeout_ms=20_000)
                    shot_path = await session.screenshot(f"home_{viewport.name}", full_page=True)
                    artifacts.append(str(shot_path))
                except Exception as e:
                    findings.append(Finding(
                        id=f"iris.{viewport.name}.render_failed",
                        agent=self.name,
                        severity=Severity.BLOCKER,
                        title=f"Could not render at {viewport}",
                        description=f"{type(e).__name__}: {e}",
                    ))
                    continue

                # Vision LLM review
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
                # Best-effort JSON parse; tolerate the model wrapping in code fences.
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
                    sev = {
                        "blocker": Severity.BLOCKER,
                        "medium": Severity.MEDIUM,
                        "low": Severity.LOW,
                        "info": Severity.INFO,
                    }.get(sev_str, Severity.LOW)
                    findings.append(Finding(
                        id=f"iris.{viewport.name}.{i}",
                        agent=self.name,
                        severity=sev,
                        title=str(item.get("title", "Visual issue"))[:200],
                        description=str(item.get("description", ""))[:1000],
                        evidence_screenshot=str(shot_path),
                        evidence_url=self.config.target_url,
                        suggested_fix=item.get("suggested_fix"),
                        tags=[viewport.name, "visual"],
                    ))

        return AgentResult(
            agent=self.name,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            success=True,
            findings=findings,
            artifacts=artifacts,
            summary=(
                f"visual: {len(self.config.viewports)} viewport(s) inspected, "
                f"{len(findings)} finding(s)"
            ),
        )
