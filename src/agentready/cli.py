"""AgentReady CLI: `agentready audit <domain>`."""

from __future__ import annotations

import asyncio

import typer

from agentready import report
from agentready.checks import ALL_CHECKS
from agentready.checks.base import Finding
from agentready.fetch import Site
from agentready.scoring import score

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
    """AgentReady — audit and improve a business's agent-readiness."""


async def run_audit(domain: str) -> tuple[Site, list[Finding]]:
    site = Site(domain)
    findings: list[Finding] = []
    try:
        for check in ALL_CHECKS:
            findings.extend(await check.run(site))
    finally:
        await site.aclose()
    return site, findings


@app.command()
def audit(
    domain: str = typer.Argument(..., help="Domain or URL to audit, e.g. example.com"),
    json_out: bool = typer.Option(False, "--json", help="Emit the report as JSON"),
) -> None:
    """Audit a domain's agent-readiness and print a scored report."""
    site, findings = asyncio.run(run_audit(domain))
    card = score(findings)
    if json_out:
        typer.echo(report.to_json(site.domain, findings, card))
    else:
        typer.echo(report.render_text(site.domain, findings, card))


if __name__ == "__main__":
    app()
