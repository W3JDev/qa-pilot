"""Kai — Journey Walker.

Walks scripted user journeys defined in RunConfig.journeys. Each Journey
is a sequence of JourneyStep[] — click, type, scroll, wait, navigate,
assert (substring presence), screenshot.

Steps run sequentially. A step failure (selector not found, assert miss)
becomes a Finding. The whole journey can still complete even if one step
fails — Kai records the failure and moves on, producing a per-step
pass/fail audit.

Targets are natural-language ('the mic button', 'send button') and Kai
uses Playwright's get_by_text + role-based locators to find them. No AI
needed for routine clicks.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from qa_pilot.agents.base import Agent
from qa_pilot.browser import BrowserSession
from qa_pilot.models import AgentResult, Finding, Journey, JourneyStep, Severity

logger = logging.getLogger("qa_pilot.kai")


class KaiJourney(Agent):
    name = "kai_journey"

    async def run(self) -> AgentResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        artifacts: list[str] = []

        if not self.config.journeys:
            return AgentResult(
                agent=self.name, started_at=started,
                finished_at=datetime.now(timezone.utc),
                success=True, findings=[], summary="no journeys configured",
            )

        viewport = self.config.viewports[0] if self.config.viewports else None
        for j_idx, journey in enumerate(self.config.journeys):
            j_findings, j_artifacts = await self._run_journey(j_idx, journey, viewport)
            findings.extend(j_findings)
            artifacts.extend(j_artifacts)

        return AgentResult(
            agent=self.name,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            success=True,
            findings=findings,
            artifacts=artifacts,
            summary=(
                f"journeys: {len(self.config.journeys)} run, "
                f"{len(findings)} step failure(s)"
            ),
        )

    async def _run_journey(
        self,
        j_idx: int,
        journey: Journey,
        viewport,
    ) -> tuple[list[Finding], list[str]]:
        findings: list[Finding] = []
        artifacts: list[str] = []
        steps_passed = 0
        steps_failed = 0

        async with BrowserSession(
            viewport=viewport,
            artifacts_dir=self.artifacts_dir,
            run_label=f"kai_{j_idx}_{_safe(journey.name)}",
        ) as session:
            try:
                await session.goto(self.config.target_url, wait_until="networkidle", timeout_ms=20_000)
            except Exception as e:
                findings.append(Finding(
                    id=f"kai.{j_idx}.nav_failed",
                    agent=self.name,
                    severity=Severity.BLOCKER,
                    title=f"Journey '{journey.name}' could not start — navigation failed",
                    description=str(e)[:400],
                    repro_steps=[f"navigate to {self.config.target_url}"],
                ))
                return findings, artifacts

            for s_idx, step in enumerate(journey.steps):
                ok, detail = await self._run_step(session, step)
                if ok:
                    steps_passed += 1
                else:
                    steps_failed += 1
                    findings.append(Finding(
                        id=f"kai.{j_idx}.{s_idx}",
                        agent=self.name,
                        severity=Severity.MEDIUM,
                        title=(
                            f"Journey '{journey.name}' step #{s_idx + 1} failed "
                            f"({step.action})"
                        ),
                        description=detail,
                        repro_steps=_format_repro(journey, s_idx),
                        evidence_url=self.config.target_url,
                        tags=["journey", journey.name],
                    ))

            # Final screenshot of the journey end-state
            shot = await session.screenshot("end_state", full_page=False)
            artifacts.append(str(shot))

        # Summary finding for the journey itself (info-level)
        if steps_failed == 0:
            findings.append(Finding(
                id=f"kai.{j_idx}.summary",
                agent=self.name,
                severity=Severity.INFO,
                title=f"Journey '{journey.name}' passed ({steps_passed} steps)",
                description=f"All {steps_passed} steps completed without failure.",
                tags=["journey", journey.name, "summary"],
            ))

        return findings, artifacts

    async def _run_step(
        self,
        session: BrowserSession,
        step: JourneyStep,
    ) -> tuple[bool, str]:
        """Returns (success, detail). detail is a short failure reason on False."""
        action = step.action
        try:
            if action == "navigate":
                if not step.url:
                    return False, "navigate step requires `url`"
                await session.goto(step.url, wait_until="networkidle", timeout_ms=15_000)
                return True, ""

            if action == "click":
                if step.selector:
                    await session.page.locator(step.selector).first.click(timeout=5_000)
                    return True, ""
                if step.target:
                    # Per qa-pilot issue #6 — use the smart_click fallback chain
                    # (role -> text -> aria-label) instead of plain text-only.
                    # This is what makes sequential SPA clicks reliable
                    # without re-navigating between steps.
                    if await session.smart_click(step.target, timeout_ms=5_000):
                        return True, ""
                    return False, (
                        f"smart_click could not find a button/link/text "
                        f"matching {step.target!r} after role+text+aria fallbacks"
                    )
                return False, "click step requires `target` or `selector`"

            if action == "type":
                if step.text is None:
                    return False, "type step requires `text`"
                if step.selector:
                    await session.page.locator(step.selector).first.fill(step.text)
                    return True, ""
                if await session.fill_first_input(step.text):
                    return True, ""
                return False, "no visible input found to fill"

            if action == "scroll":
                # default: scroll to bottom
                await session.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                return True, ""

            if action == "wait":
                await asyncio.sleep(2.0)
                return True, ""

            if action == "assert":
                if not step.contains:
                    return False, "assert step requires `contains`"
                body = await session.body_text(max_chars=20_000)
                if step.contains.lower() in body.lower():
                    return True, ""
                return False, (
                    f"page body does not contain {step.contains!r} "
                    f"(checked first 20k chars)"
                )

            if action == "screenshot":
                label = step.target or "step"
                await session.screenshot(label, full_page=True)
                return True, ""

            return False, f"unknown action {action!r}"
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {str(e)[:200]}"


def _format_repro(journey: Journey, failing_step_idx: int) -> list[str]:
    """Render a repro-steps list up to and including the failing step."""
    out: list[str] = [f"Journey: {journey.name}"]
    for i, step in enumerate(journey.steps[: failing_step_idx + 1]):
        if step.action == "click":
            tgt = step.selector or step.target or "?"
            out.append(f"{i + 1}. click {tgt!r}")
        elif step.action == "type":
            out.append(f"{i + 1}. type {step.text!r}")
        elif step.action == "navigate":
            out.append(f"{i + 1}. navigate {step.url!r}")
        elif step.action == "assert":
            out.append(f"{i + 1}. assert page contains {step.contains!r}")
        elif step.action == "scroll":
            out.append(f"{i + 1}. scroll to bottom")
        elif step.action == "wait":
            out.append(f"{i + 1}. wait 2s")
        elif step.action == "screenshot":
            out.append(f"{i + 1}. screenshot {(step.target or 'step')!r}")
        else:
            out.append(f"{i + 1}. {step.action}")
    return out


def _safe(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s)[:40]
