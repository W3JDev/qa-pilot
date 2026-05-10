"""Vega — Smoke. Fast health probe of every public surface.

Does the URL respond? Does the page render? Are critical paths reachable?
No deep inspection — that's Iris's job. Vega just answers green/red.
"""
from __future__ import annotations

from datetime import datetime, timezone

from qa_pilot.agents.base import Agent
from qa_pilot.browser import BrowserSession, head_check
from qa_pilot.models import AgentResult, Finding, Severity


class VegaSmoke(Agent):
    name = "vega_smoke"

    async def run(self) -> AgentResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []

        # ---- Layer 1: raw HTTP ----
        async with head_check(self.config.target_url) as status:
            if status == 0:
                findings.append(Finding(
                    id="vega.http.unreachable",
                    agent=self.name,
                    severity=Severity.BLOCKER,
                    title="Target URL unreachable",
                    description=f"GET {self.config.target_url} did not return any HTTP status — DNS, network, or service is down.",
                    evidence_url=self.config.target_url,
                    suggested_fix="Verify the target_url is correct and the service is deployed.",
                ))
                return AgentResult(
                    agent=self.name, started_at=started,
                    finished_at=datetime.now(timezone.utc),
                    success=True, findings=findings,
                    summary=f"unreachable: {self.config.target_url}",
                )
            if status >= 500:
                findings.append(Finding(
                    id="vega.http.5xx",
                    agent=self.name,
                    severity=Severity.BLOCKER,
                    title=f"Server error: HTTP {status}",
                    description=f"GET {self.config.target_url} returned {status}.",
                    evidence_url=self.config.target_url,
                ))
            elif status >= 400:
                findings.append(Finding(
                    id="vega.http.4xx",
                    agent=self.name,
                    severity=Severity.MEDIUM,
                    title=f"Client error: HTTP {status}",
                    description=f"GET {self.config.target_url} returned {status}.",
                    evidence_url=self.config.target_url,
                ))

        # ---- Layer 2: real browser render check on first viewport ----
        viewport = self.config.viewports[0] if self.config.viewports else None
        artifacts: list[str] = []
        async with BrowserSession(
            viewport=viewport,
            artifacts_dir=self.artifacts_dir,
            run_label="vega",
        ) as session:
            try:
                await session.goto(self.config.target_url, wait_until="networkidle", timeout_ms=20_000)
                shot = await session.screenshot("homepage", full_page=False)
                artifacts.append(str(shot))
                body = await session.body_text(max_chars=2000)
                if not body or len(body.strip()) < 20:
                    findings.append(Finding(
                        id="vega.render.empty",
                        agent=self.name,
                        severity=Severity.BLOCKER,
                        title="Rendered body is empty or near-empty",
                        description=(
                            "Page loaded but produced <20 chars of visible text. "
                            "Likely a client-side render failure or blank page."
                        ),
                        evidence_screenshot=str(shot),
                        evidence_url=self.config.target_url,
                    ))
            except Exception as e:
                findings.append(Finding(
                    id="vega.render.exception",
                    agent=self.name,
                    severity=Severity.BLOCKER,
                    title=f"Browser render exception: {type(e).__name__}",
                    description=str(e)[:400],
                    evidence_url=self.config.target_url,
                ))

            # Surface any console errors / network failures the browser captured
            for entry in session.captured.console:
                if entry.level == "error":
                    findings.append(Finding(
                        id=f"vega.console.{abs(hash(entry.text)) % 10**8}",
                        agent=self.name,
                        severity=Severity.MEDIUM,
                        title="Console error on homepage",
                        description=entry.text[:300],
                        tags=["console"],
                    ))
            for nf in session.captured.network_failures:
                findings.append(Finding(
                    id=f"vega.network.{abs(hash(nf.url)) % 10**8}",
                    agent=self.name,
                    severity=Severity.MEDIUM,
                    title=f"{nf.method} {nf.url} failed",
                    description=(
                        f"status={nf.status} failure={nf.failure_text or '-'}"
                    ),
                    tags=["network"],
                ))

        return AgentResult(
            agent=self.name,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            success=True,
            findings=findings,
            artifacts=artifacts,
            summary=(
                f"smoke {'🟢' if not findings else '🟡'} "
                f"({len(findings)} finding{'' if len(findings) == 1 else 's'})"
            ),
        )
