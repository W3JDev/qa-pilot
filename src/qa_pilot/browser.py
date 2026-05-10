"""Playwright wrapper — the browser shape every agent uses.

We hide the Playwright API behind a small async surface that:
  * Hosts a single page per BrowserSession context manager
  * Captures screenshots to a per-run artifacts directory
  * Tails console errors + failed network requests for the Watchdog agent
  * Exposes natural-language helpers (find_by_text, click_by_text)

Keep this thin. Agents own their own logic; this is just the I/O layer.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from playwright.async_api import (
    BrowserContext,
    ConsoleMessage,
    Page,
    Request,
    Response,
    async_playwright,
)

from qa_pilot.models import Viewport

logger = logging.getLogger("qa_pilot.browser")


@dataclass
class ConsoleEntry:
    level: str            # "log" | "error" | "warning" | etc.
    text: str
    location_url: str | None = None


@dataclass
class NetworkFailure:
    url: str
    method: str
    status: int | None = None
    failure_text: str | None = None


@dataclass
class RuntimeException:
    """Captured via CDP Runtime.exceptionThrown — uncaught JS errors that
    don't always surface via console.error."""
    text: str
    line: int | None = None
    column: int | None = None
    url: str | None = None
    stack: str | None = None


@dataclass
class CapturedSession:
    """What the watchdog agent reads after a session is closed."""
    console: list[ConsoleEntry] = field(default_factory=list)
    network_failures: list[NetworkFailure] = field(default_factory=list)
    screenshots: list[Path] = field(default_factory=list)
    runtime_exceptions: list[RuntimeException] = field(default_factory=list)
    cdp_log_entries: list[ConsoleEntry] = field(default_factory=list)


class BrowserSession:
    """Single-page session. One per agent run.

    Usage:
        async with BrowserSession(viewport=Viewport()) as session:
            await session.goto("https://example.com")
            await session.screenshot("home")
            text = await session.body_text()
    """

    def __init__(
        self,
        *,
        viewport: Viewport | None = None,
        artifacts_dir: Path | None = None,
        run_label: str = "run",
        headless: bool = True,
    ) -> None:
        self.viewport = viewport or Viewport()
        self.artifacts_dir = artifacts_dir or Path("./qa-artifacts")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.run_label = run_label
        self.headless = headless
        self.captured = CapturedSession()
        self._page: Page | None = None
        self._ctx: BrowserContext | None = None
        self._pw = None
        self._cdp = None

    async def __aenter__(self) -> "BrowserSession":
        self._pw = await async_playwright().start()
        browser = await self._pw.chromium.launch(headless=self.headless)
        self._ctx = await browser.new_context(
            viewport={"width": self.viewport.width, "height": self.viewport.height},
        )
        page = await self._ctx.new_page()
        self._page = page

        # Console capture
        def _on_console(msg: ConsoleMessage) -> None:
            self.captured.console.append(
                ConsoleEntry(
                    level=msg.type,
                    text=msg.text,
                    location_url=msg.location.get("url") if msg.location else None,
                )
            )

        # Network failure capture
        def _on_response(resp: Response) -> None:
            if resp.status >= 400:
                self.captured.network_failures.append(
                    NetworkFailure(
                        url=resp.url,
                        method=resp.request.method,
                        status=resp.status,
                    )
                )

        def _on_request_failed(req: Request) -> None:
            self.captured.network_failures.append(
                NetworkFailure(
                    url=req.url,
                    method=req.method,
                    failure_text=(req.failure or "")[:200],
                )
            )

        page.on("console", _on_console)
        page.on("response", _on_response)
        page.on("requestfailed", _on_request_failed)

        # CDP-direct listeners (per qa-pilot issue #7) — catches uncaught JS
        # exceptions, browser-level Log entries (deprecations, violations),
        # and network failures that don't fire response events (CORS, CSP).
        try:
            cdp = await self._ctx.new_cdp_session(page)
            await cdp.send("Runtime.enable")
            await cdp.send("Network.enable")
            await cdp.send("Log.enable")
            self._cdp = cdp

            def _on_exception(params):
                d = params.get("exceptionDetails", {})
                self.captured.runtime_exceptions.append(RuntimeException(
                    text=d.get("text") or d.get("exception", {}).get("description") or "uncaught exception",
                    line=d.get("lineNumber"),
                    column=d.get("columnNumber"),
                    url=d.get("url"),
                    stack=(d.get("exception") or {}).get("description"),
                ))

            def _on_loading_failed(params):
                self.captured.network_failures.append(NetworkFailure(
                    url=params.get("request", {}).get("url") or "(unknown)",
                    method=params.get("request", {}).get("method", "GET"),
                    status=None,
                    failure_text=(
                        f"{params.get('errorText', 'failed')} "
                        f"(blocked={params.get('blockedReason') or 'no'}, "
                        f"type={params.get('type', '?')})"
                    )[:240],
                ))

            def _on_log_entry(params):
                entry = params.get("entry", {})
                level = entry.get("level", "log")
                if level not in ("error", "warning"):
                    return
                self.captured.cdp_log_entries.append(ConsoleEntry(
                    level=level,
                    text=entry.get("text", ""),
                    location_url=entry.get("url"),
                ))

            cdp.on("Runtime.exceptionThrown", _on_exception)
            cdp.on("Network.loadingFailed", _on_loading_failed)
            cdp.on("Log.entryAdded", _on_log_entry)
        except Exception as e:
            # CDP is not strictly required — if it fails (e.g. older Chromium
            # build), continue with the Playwright-event-only path.
            logger.debug("CDP listeners not attached: %s", e)
            self._cdp = None

        return self

    async def __aexit__(self, *exc) -> None:
        if self._ctx is not None:
            await self._ctx.close()
        if self._pw is not None:
            await self._pw.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("BrowserSession not entered — use 'async with'")
        return self._page

    # --- high-level helpers -------------------------------------------------

    async def goto(self, url: str, *, wait_until: str = "domcontentloaded", timeout_ms: int = 30_000) -> None:
        await self.page.goto(url, wait_until=wait_until, timeout=timeout_ms)

    async def screenshot(self, label: str, *, full_page: bool = True) -> Path:
        """Save a screenshot to the artifacts dir, return its path."""
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
        path = self.artifacts_dir / f"{self.run_label}_{self.viewport.name}_{safe}.png"
        await self.page.screenshot(path=str(path), full_page=full_page)
        self.captured.screenshots.append(path)
        return path

    async def body_text(self, *, max_chars: int = 8_000) -> str:
        text = await self.page.inner_text("body")
        return text[:max_chars]

    async def html(self, *, max_chars: int = 12_000) -> str:
        html = await self.page.content()
        return html[:max_chars]

    async def click_text(self, text: str, *, timeout_ms: int = 5_000) -> bool:
        """Click an element whose visible text matches. Returns True on success."""
        try:
            await self.page.get_by_text(text, exact=False).first.click(timeout=timeout_ms)
            return True
        except Exception as e:
            logger.warning("click_text(%r) failed: %s", text, e)
            return False

    async def smart_click(self, target: str, *, timeout_ms: int = 5_000) -> bool:
        """Click using a fallback chain optimized for sequential SPA steps
        (per qa-pilot issue #6 — the Kai sequencer fix). Tries:

          1. role=button name=target           — most semantic + most reliable
          2. role=link name=target
          3. text=target                       — fallback when role isn't set
          4. css selector heuristics           — last resort

        Returns True on the first success. False if all four miss.
        """
        attempts = [
            lambda: self.page.get_by_role("button", name=target).first.click(timeout=timeout_ms),
            lambda: self.page.get_by_role("link", name=target).first.click(timeout=timeout_ms),
            lambda: self.page.get_by_text(target, exact=False).first.click(timeout=timeout_ms),
            lambda: self.page.locator(f"[aria-label*={target!r} i]").first.click(timeout=timeout_ms),
        ]
        for i, attempt in enumerate(attempts, 1):
            try:
                await attempt()
                return True
            except Exception as e:
                logger.debug("smart_click attempt %d for %r failed: %s", i, target, e)
        logger.warning("smart_click(%r) exhausted all 4 strategies", target)
        return False

    async def fill_first_input(self, value: str) -> bool:
        """Fill the first visible <input>. Naive but useful for chat-y UIs."""
        try:
            await self.page.locator("input:visible").first.fill(value)
            return True
        except Exception as e:
            logger.warning("fill_first_input failed: %s", e)
            return False

    async def click_role(self, role: str, name: str | None = None) -> bool:
        try:
            loc = self.page.get_by_role(role, name=name) if name else self.page.get_by_role(role)
            await loc.first.click(timeout=5_000)
            return True
        except Exception as e:
            logger.warning("click_role(%s, %s) failed: %s", role, name, e)
            return False

    async def wait(self, ms: int) -> None:
        await asyncio.sleep(ms / 1000.0)


@asynccontextmanager
async def head_check(url: str, *, timeout_sec: int = 10) -> AsyncIterator[int]:
    """Tiny helper for raw HTTP HEAD/GET (Vega smoke uses this without spinning a browser)."""
    import httpx
    async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
        try:
            resp = await client.get(url)
            yield resp.status_code
        except Exception:
            yield 0
