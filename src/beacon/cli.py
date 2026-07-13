"""Beacon CLI: `beacon audit <domain>`."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from beacon import report
from beacon.checks import ALL_CHECKS
from beacon.checks.base import Finding
from beacon.fetch import Site
from beacon.generate.llmstxt import generate_llms_txt
from beacon.scoring import score

app = typer.Typer(no_args_is_help=True, add_completion=False)
generate_app = typer.Typer(no_args_is_help=True)
app.add_typer(generate_app, name="generate", help="Generate missing agent-readiness pieces")


@app.callback()
def main() -> None:
    """Beacon — audit and improve a business's agent-readiness."""


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


@generate_app.command("llms-txt")
def llms_txt(
    domain: str = typer.Argument(..., help="Domain or URL to generate llms.txt for"),
    output: Path = typer.Option(None, "--output", "-o", help="Write to a file instead of stdout"),
) -> None:
    """Draft an llms.txt from the site's sitemap and page metadata."""

    async def run() -> str:
        site = Site(domain)
        try:
            return await generate_llms_txt(site)
        finally:
            await site.aclose()

    text = asyncio.run(run())
    if output is not None:
        output.write_text(text)
        typer.echo(f"Wrote {output} — review the draft before publishing it at /llms.txt")
    else:
        typer.echo(text)


if __name__ == "__main__":
    app()
