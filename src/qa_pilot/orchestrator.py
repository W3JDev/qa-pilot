"""QA Lead — orchestrates all agents in parallel and aggregates findings."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from qa_pilot.agents import REGISTRY
from qa_pilot.models import AgentResult, Report, RunConfig

logger = logging.getLogger("qa_pilot.orchestrator")


class QALead:
    """Spawn the configured agents concurrently, collect their results,
    build a Report. Failures in one agent don't kill the run — each agent
    is wrapped in run_safe()."""

    def __init__(self, config: RunConfig, artifacts_dir: Path | None = None) -> None:
        self.config = config
        self.artifacts_dir = artifacts_dir or Path("./qa-artifacts")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    async def run(self) -> Report:
        started = datetime.now(timezone.utc)
        agents = self._instantiate_agents()
        if not agents:
            logger.warning("No agents configured — Report will be empty.")

        # Fan out
        tasks = [a.run_safe() for a in agents]
        results: list[AgentResult] = await asyncio.gather(*tasks, return_exceptions=False)

        report = Report.from_agent_results(
            target_url=self.config.target_url,
            viewports=self.config.viewports,
            results=results,
            started_at=started,
        )
        return report

    def _instantiate_agents(self):
        agents = []
        for name in self.config.agents:
            cls = REGISTRY.get(name)
            if cls is None:
                logger.warning("unknown agent %r — skipping", name)
                continue
            agents.append(cls(self.config, self.artifacts_dir))
        return agents
