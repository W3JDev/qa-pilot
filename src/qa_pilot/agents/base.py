"""Agent base — the contract every QA agent implements."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from qa_pilot.models import AgentResult, RunConfig

logger = logging.getLogger("qa_pilot.agents.base")


class Agent(ABC):
    """Abstract base. Subclasses implement run(); orchestrator handles timing
    and error capture so individual agents don't have to."""

    name: str = "agent"

    def __init__(self, config: RunConfig, artifacts_dir: Path) -> None:
        self.config = config
        self.artifacts_dir = artifacts_dir

    @abstractmethod
    async def run(self) -> AgentResult:
        """Run this agent against config.target_url. Return findings."""

    async def run_safe(self) -> AgentResult:
        """Wrap run() in error capture so one agent's crash doesn't kill the run."""
        started = datetime.now(timezone.utc)
        try:
            result = await self.run()
            return result
        except Exception as e:  # noqa: BLE001
            logger.exception("%s crashed: %s", self.name, e)
            return AgentResult(
                agent=self.name,
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                success=False,
                summary=f"{type(e).__name__}: {e}",
            )


class AgentRegistry:
    """Plug-in registry. Lets users register custom agents."""

    def __init__(self) -> None:
        self._agents: dict[str, type[Agent]] = {}

    def register(self, name: str, agent_cls: type[Agent]) -> None:
        self._agents[name] = agent_cls

    def get(self, name: str) -> type[Agent] | None:
        return self._agents.get(name)

    def names(self) -> list[str]:
        return sorted(self._agents.keys())
