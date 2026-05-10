"""QA Pilot — agentic QA platform."""
__version__ = "0.3.0"

from qa_pilot.models import (
    Finding,
    Severity,
    Report,
    AgentResult,
    Verdict,
    Viewport,
)

__all__ = [
    "Finding",
    "Severity",
    "Report",
    "AgentResult",
    "Verdict",
    "Viewport",
    "__version__",
]
