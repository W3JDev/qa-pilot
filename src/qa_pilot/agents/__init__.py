"""QA Pilot agents — five specialists + a base contract.

  * vega_smoke      — fast health check
  * iris_visual     — viewport screenshots + visual inspection
  * sage_aesthetic  — design critic on screenshots (vision LLM)
  * argus_watchdog  — console + network failure capture (no LLM needed)
  * kai_journey     — scripted user-journey walker
"""
from qa_pilot.agents.argus_watchdog import ArgusWatchdog
from qa_pilot.agents.base import Agent, AgentRegistry
from qa_pilot.agents.iris_visual import IrisVisual
from qa_pilot.agents.kai_journey import KaiJourney
from qa_pilot.agents.sage_aesthetic import SageAesthetic
from qa_pilot.agents.vega_smoke import VegaSmoke

__all__ = [
    "Agent",
    "AgentRegistry",
    "ArgusWatchdog",
    "IrisVisual",
    "KaiJourney",
    "SageAesthetic",
    "VegaSmoke",
]

# Default registry. Users can register custom agents at runtime.
REGISTRY = AgentRegistry()
REGISTRY.register("vega_smoke", VegaSmoke)
REGISTRY.register("iris_visual", IrisVisual)
REGISTRY.register("sage_aesthetic", SageAesthetic)
REGISTRY.register("argus_watchdog", ArgusWatchdog)
REGISTRY.register("kai_journey", KaiJourney)
