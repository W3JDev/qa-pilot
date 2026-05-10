"""Argus — Console + Network Watchdog.

Drives the target URL, stays idle for a short observation window, and
surfaces every console error and every failed network request as a
finding. No vision LLM needed — this is straight observability.

Usually runs in parallel with Kai so they share the same user journey
without double-driving the browser. When Kai isn't in the config, Argus
runs a stand-alone pass: just load the homepage and wait.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from qa_pilot.agents.base import Agent
from qa_pilot.browser import BrowserSession
from qa_pilot.models import AgentResult, Finding, Severity


class ArgusWatchdog(Agent):
    name = "argus_watchdog"

    async def run(self) -> AgentResult:
        started = datetime.now(timezone.utc)
        findings: list[Finding] = []
        artifacts: list[str] = []

        viewport = self.config.viewports[0] if self.config.viewports else None
        async with BrowserSession(
            viewport=viewport,
            artifacts_dir=self.artifacts_dir,
            run_label="argus",
        ) as session:
            try:
                await session.goto(self.config.target_url, wait_until="networkidle", timeout_ms=20_000)
            except Exception as e:
                return AgentResult(
                    agent=self.name, started_at=started,
                    finished_at=datetime.now(timezone.utc),
                    success=False,
                    summary=f"navigation failed: {type(e).__name__}: {e}",
                    findings=[Finding(
                        id="argus.nav_failed",
                        agent=self.name,
                        severity=Severity.BLOCKER,
                        title="Could not navigate to target_url",
                        description=str(e)[:400],
                    )],
                )

            # Idle observation window — let SPA hydrate, async calls settle
            await asyncio.sleep(3.0)

            shot = await session.screenshot("watchdog_final", full_page=False)
            artifacts.append(str(shot))

            # Deduplicate console errors by text (same error fires repeatedly).
            # Per qa-pilot issue #7 — also include CDP-captured Log.entryAdded
            # events which catch browser-level deprecations + violations not
            # reported via the regular `console` event.
            seen_console: set[str] = set()
            all_console_entries = (
                list(session.captured.console)
                + list(session.captured.cdp_log_entries)
            )
            for entry in all_console_entries:
                if entry.level not in ("error", "warning"):
                    continue
                key = entry.text[:200]
                if key in seen_console:
                    continue
                seen_console.add(key)
                findings.append(Finding(
                    id=f"argus.console.{abs(hash(key)) % 10**8}",
                    agent=self.name,
                    severity=(
                        Severity.MEDIUM if entry.level == "error" else Severity.LOW
                    ),
                    title=f"Console {entry.level}: {entry.text[:80]}",
                    description=entry.text[:800],
                    evidence_url=entry.location_url or self.config.target_url,
                    tags=["console", entry.level],
                ))

            # Runtime exceptions (uncaught JS) — per issue #7. These are the
            # invisible bugs the DOM scan misses entirely. ALWAYS severity 2+.
            seen_exc: set[str] = set()
            for exc in session.captured.runtime_exceptions:
                key = exc.text[:200]
                if key in seen_exc:
                    continue
                seen_exc.add(key)
                location = ""
                if exc.url:
                    location = f"\nat {exc.url}"
                    if exc.line is not None:
                        location += f":{exc.line}"
                findings.append(Finding(
                    id=f"argus.runtime_exc.{abs(hash(key)) % 10**8}",
                    agent=self.name,
                    severity=Severity.MEDIUM,
                    title=f"Uncaught JS exception: {exc.text[:80]}",
                    description=(
                        f"{exc.text}{location}\n\n"
                        f"Stack:\n{exc.stack or '(no stack)'}"
                    )[:1500],
                    evidence_url=exc.url or self.config.target_url,
                    tags=["runtime", "javascript"],
                ))

            # Deduplicate network failures by (method, url, status)
            seen_net: set[tuple] = set()
            for nf in session.captured.network_failures:
                key = (nf.method, nf.url, nf.status)
                if key in seen_net:
                    continue
                seen_net.add(key)
                sev = (
                    Severity.BLOCKER if nf.status and nf.status >= 500
                    else Severity.MEDIUM if nf.status and nf.status >= 400
                    else Severity.LOW
                )
                status_label = f"HTTP {nf.status}" if nf.status else "network failure"
                findings.append(Finding(
                    id=f"argus.network.{abs(hash(key)) % 10**8}",
                    agent=self.name,
                    severity=sev,
                    title=f"{status_label} on {nf.method} {_short_path(nf.url)}",
                    description=(
                        f"URL: {nf.url}\n"
                        f"Method: {nf.method}\n"
                        f"Status: {nf.status or 'n/a'}\n"
                        f"Failure: {nf.failure_text or 'n/a'}"
                    ),
                    evidence_url=nf.url,
                    tags=["network", str(nf.status or "failed")],
                ))

        return AgentResult(
            agent=self.name,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            success=True,
            findings=findings,
            artifacts=artifacts,
            summary=(
                f"watchdog: {len(seen_console)} console, "
                f"{len(seen_net)} network, "
                f"{len(seen_exc)} runtime exception(s)"
            ),
        )


def _short_path(url: str) -> str:
    """Shorten a URL to just scheme://host/...path for display."""
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        path = p.path or "/"
        if len(path) > 40:
            path = path[:37] + "…"
        return f"{p.scheme}://{p.netloc}{path}"
    except Exception:
        return url[:80]
