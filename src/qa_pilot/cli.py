"""qa-pilot CLI — Typer-based, the user-facing entry point.

Subcommands:
  smoke <url>           Quick smoke check (only Vega), prints to stdout
  run <config.yaml>     Full team run from a config file
  agents                List registered agents
  version               Print version
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import typer
import yaml
from rich.console import Console

from qa_pilot import __version__
from qa_pilot.agents import REGISTRY
from qa_pilot.models import (
    ReportConfig,
    ReportDestination,
    RunConfig,
    Viewport,
)
from qa_pilot.orchestrator import QALead
from qa_pilot.reporting import write_to_destinations

console = Console()
app = typer.Typer(
    name="qa-pilot",
    help="Agentic QA platform — autonomous browser-driven test team for any web app.",
    no_args_is_help=True,
)


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
    )


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"qa-pilot {__version__}")


@app.command()
def agents() -> None:
    """List registered agents."""
    for name in REGISTRY.names():
        console.print(f"  • {name}")


@app.command()
def smoke(
    url: str = typer.Argument(..., help="Target URL to smoke-test"),
    artifacts_dir: Path = typer.Option(
        Path("./qa-artifacts"),
        "--artifacts",
        "-a",
        help="Where to save screenshots",
    ),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="LLM model (litellm-style)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Quick smoke test against a URL. Just runs Vega."""
    _setup_logging(verbose)
    config = RunConfig(
        target_url=url,
        agents=["vega_smoke"],
        llm_model=model,
        report=ReportConfig(formats=["markdown"], destinations=[ReportDestination(type="stdout")]),
    )
    report = asyncio.run(QALead(config, artifacts_dir).run())
    write_to_destinations(report, config.report)
    raise typer.Exit(code=0 if report.verdict.value != "red" else 1)


@app.command()
def run(
    config_path: Path = typer.Argument(..., help="Path to a YAML run config"),
    artifacts_dir: Path = typer.Option(
        Path("./qa-artifacts"),
        "--artifacts",
        "-a",
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Override the LLM model"),
    fmt: str = typer.Option("markdown", "--format", "-f", help="markdown | json"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the QA team against a config file."""
    _setup_logging(verbose)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        console.print(f"[red]config file must be a YAML object[/red]")
        raise typer.Exit(code=2)

    # Normalize viewports (allow shorthand)
    if "viewports" in raw and isinstance(raw["viewports"], list):
        raw["viewports"] = [
            Viewport(**v) if isinstance(v, dict) else Viewport()
            for v in raw["viewports"]
        ]

    config = RunConfig(**raw)
    if model:
        config.llm_model = model
    if fmt and fmt not in ("markdown", "json"):
        console.print(f"[red]unknown format {fmt!r}[/red]")
        raise typer.Exit(code=2)
    if fmt:
        # CLI --format overrides config.report.formats
        config.report.formats = [fmt]

    report = asyncio.run(QALead(config, artifacts_dir).run())
    sent_to = write_to_destinations(report, config.report)
    if sent_to:
        console.print(f"[dim]delivered to: {', '.join(sent_to)}[/dim]")
    raise typer.Exit(code=0 if report.verdict.value != "red" else 1)


if __name__ == "__main__":
    app()
