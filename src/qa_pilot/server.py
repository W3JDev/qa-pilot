"""qa-pilot HTTP server — deployable as a Railway service or anywhere
that runs Python.

Endpoints:
  GET  /              — landing + status JSON
  GET  /health        — health probe (Railway uses this)
  GET  /agents        — list registered agents
  POST /qa/smoke      — fast smoke test against one URL
  POST /qa/run        — full team run (synchronous; small jobs)
  POST /qa/run-async  — kicks off a background run, returns run_id
  GET  /qa/runs/{id}  — fetch run status + report

Set QA_PILOT_API_TOKEN to require Bearer-token auth on POST /qa/* routes
(recommended for any public deployment).

Run locally:
    uvicorn qa_pilot.server:app --reload --port 8000

Railway:
    set start command: `uvicorn qa_pilot.server:app --host 0.0.0.0 --port $PORT`
    OR rely on the included railway.json
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from qa_pilot import __version__
from qa_pilot.agents import REGISTRY
from qa_pilot.models import (
    Journey,
    JourneyStep,
    Report,
    ReportConfig,
    ReportDestination,
    RunConfig,
    Viewport,
)
from qa_pilot.orchestrator import QALead

logger = logging.getLogger("qa_pilot.server")


# -----------------------------------------------------------------------------
# Auth (optional bearer token)
# -----------------------------------------------------------------------------

API_TOKEN = os.environ.get("QA_PILOT_API_TOKEN")


def _require_token(authorization: str | None) -> None:
    """Bearer-token gate for write endpoints. No-op when QA_PILOT_API_TOKEN
    is unset (useful for local dev)."""
    if not API_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token. Set Authorization: Bearer <token>.",
        )
    if authorization.removeprefix("Bearer ").strip() != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid token.",
        )


# -----------------------------------------------------------------------------
# Run registry (in-memory; persistence is a Phase-2 problem)
# -----------------------------------------------------------------------------

class StoredRun(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "running"          # running | done | failed
    target_url: str
    report: Report | None = None
    error: str | None = None


_runs: dict[str, StoredRun] = {}


# -----------------------------------------------------------------------------
# Request models
# -----------------------------------------------------------------------------

class SmokeRequest(BaseModel):
    target_url: str
    model: str = Field(default="gpt-4o-mini")


class RunRequest(BaseModel):
    target_url: str
    viewports: list[Viewport] | None = None
    agents: list[str] | None = None
    journeys: list[Journey] | None = None
    model: str = Field(default="gpt-4o-mini")
    timeout_sec: int = Field(default=120)


# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------

app = FastAPI(
    title="qa-pilot",
    description=(
        "Agentic QA platform — autonomous browser-driven test team for any web app. "
        "Source: https://github.com/W3JDev/qa-pilot"
    ),
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("QA_PILOT_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    """Tiny landing page so the public Railway URL isn't a JSON dump."""
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>qa-pilot {__version__}</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 720px;
            margin: 5vh auto; padding: 1.2rem; line-height: 1.55;
            background: #0a0a0c; color: #f4f1ea; }}
    h1 {{ font-size: 2rem; margin: 0 0 .5rem 0; letter-spacing: -0.02em; }}
    code, pre {{ background: #15181f; padding: .15rem .4rem; border-radius: 6px;
                 font-family: ui-monospace, monospace; font-size: .92em; }}
    pre {{ padding: 1rem; overflow-x: auto; }}
    a {{ color: #c8a45c; }}
    .pill {{ display: inline-block; background: #15181f; border: 1px solid #2a2f3a;
             border-radius: 999px; padding: .15rem .7rem; font-size: .8rem;
             font-family: ui-monospace, monospace; color: #a8a8a8;
             text-transform: uppercase; letter-spacing: .12em; }}
  </style>
</head>
<body>
  <span class="pill">qa-pilot · v{__version__}</span>
  <h1>Live QA agent.</h1>
  <p>Five specialist agents — Smoke, Visual, Journey, Watchdog, Aesthetic — drive a
     real browser and report findings like a human tester. Run anywhere.</p>
  <p><strong>Quick test:</strong></p>
  <pre>curl -X POST {os.environ.get("QA_PILOT_PUBLIC_URL", "https://your-deploy")}/qa/smoke \\
  -H "Content-Type: application/json" \\
  -d '{{"target_url": "https://your-app.com"}}'</pre>
  <p><a href="/agents">/agents</a> · <a href="/health">/health</a> ·
     <a href="https://github.com/W3JDev/qa-pilot">github</a></p>
</body>
</html>"""
    return HTMLResponse(html)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "qa-pilot",
        "version": __version__,
        "auth_required": bool(API_TOKEN),
        "ollama_configured": bool(os.environ.get("OLLAMA_API_BASE")),
    }


@app.get("/agents")
async def list_agents() -> dict:
    return {"agents": REGISTRY.names()}


@app.post("/qa/smoke")
async def qa_smoke(
    req: SmokeRequest,
    authorization: str | None = Header(default=None),
) -> Report:
    _require_token(authorization)
    config = RunConfig(
        target_url=req.target_url,
        agents=["vega_smoke"],
        llm_model=req.model,
        report=ReportConfig(formats=["json"], destinations=[]),
    )
    artifacts_dir = Path(os.environ.get("QA_PILOT_ARTIFACTS_DIR", "/tmp/qa-artifacts"))
    return await QALead(config, artifacts_dir).run()


@app.post("/qa/run")
async def qa_run(
    req: RunRequest,
    authorization: str | None = Header(default=None),
) -> Report:
    """Synchronous run — returns the Report. Recommended for jobs <30s."""
    _require_token(authorization)
    config = _config_from_request(req)
    artifacts_dir = Path(os.environ.get("QA_PILOT_ARTIFACTS_DIR", "/tmp/qa-artifacts"))
    return await asyncio.wait_for(
        QALead(config, artifacts_dir).run(),
        timeout=req.timeout_sec,
    )


@app.post("/qa/run-async")
async def qa_run_async(
    req: RunRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    """Kicks off a background run, returns run_id immediately. Poll
    GET /qa/runs/{id} for status."""
    _require_token(authorization)
    config = _config_from_request(req)
    artifacts_dir = Path(os.environ.get("QA_PILOT_ARTIFACTS_DIR", "/tmp/qa-artifacts"))
    run_id = uuid.uuid4().hex[:12]
    _runs[run_id] = StoredRun(
        run_id=run_id,
        started_at=datetime.now(timezone.utc),
        target_url=config.target_url,
    )

    async def _bg():
        try:
            report = await QALead(config, artifacts_dir).run()
            _runs[run_id].report = report
            _runs[run_id].status = "done"
        except Exception as e:  # noqa: BLE001
            _runs[run_id].status = "failed"
            _runs[run_id].error = f"{type(e).__name__}: {e}"
        finally:
            _runs[run_id].finished_at = datetime.now(timezone.utc)

    asyncio.create_task(_bg())
    return {"run_id": run_id, "status": "running"}


@app.get("/qa/runs/{run_id}")
async def qa_run_status(run_id: str) -> StoredRun:
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, f"run_id {run_id!r} not found")
    return run


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _config_from_request(req: RunRequest) -> RunConfig:
    return RunConfig(
        target_url=req.target_url,
        viewports=req.viewports or [Viewport()],
        agents=req.agents or ["vega_smoke", "iris_visual", "sage_aesthetic"],
        journeys=req.journeys or [],
        llm_model=req.model,
        timeout_sec=req.timeout_sec,
        report=ReportConfig(formats=["json"], destinations=[]),
    )
