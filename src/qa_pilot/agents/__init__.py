"""QA Pilot agents — five specialists + a base contract.

  * vega_smoke    — fast health check
  * iris_visual   — viewport screenshots + visual inspection
  * sage_aesthetic — design critic on screenshots (vision LLM)

Future:
  * kai_journey   — flow walker (uses RunConfig.journeys)
  * argus_watchdog — console + network bug hunter
"""
from qa_pilot.agents.base import Agent, AgentRegistry
from qa_pilot.agents.vega_smoke import VegaSmoke
from qa_pilot.agents.iris_visual import IrisVisual
from qa_pilot.agents.sage_aesthetic import SageAesthetic

__all__ = ["Agent", "AgentRegistry", "VegaSmoke", "IrisVisual", "SageAesthetic"]

# Default registry. Users can register custom agents at runtime.
REGISTRY = AgentRegistry()
REGISTRY.register("vega_smoke", VegaSmoke)
REGISTRY.register("iris_visual", IrisVisual)
REGISTRY.register("sage_aesthetic", SageAesthetic)
