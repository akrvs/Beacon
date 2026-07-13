"""Beacon CLI: `beacon audit <domain>`."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import typer

from beacon import report
from beacon.checks import ALL_CHECKS
from beacon.checks.base import Finding
from beacon.fetch import Site, USER_AGENT
from beacon.generate.llmstxt import generate_llms_txt
from beacon.generate.mcp_scaffold import scaffold_mcp_server
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


@generate_app.command("mcp")
def mcp(
    spec: str = typer.Argument(..., help="Path or URL to an OpenAPI JSON spec"),
    output: Path = typer.Option(
        Path("mcp-server"), "--output", "-o", help="Directory to write the scaffold into"
    ),
    name: str = typer.Option(None, "--name", help="Server name (defaults to the spec title)"),
) -> None:
    """Scaffold a runnable MCP server that wraps the API described by an OpenAPI spec."""
    if spec.startswith(("http://", "https://")):
        response = httpx.get(spec, headers={"User-Agent": USER_AGENT}, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        raw = response.text
    else:
        raw = Path(spec).read_text()
    try:
        spec_data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise typer.BadParameter(f"Spec is not valid JSON: {error}") from error
    if not isinstance(spec_data, dict) or not spec_data.get("paths"):
        raise typer.BadParameter("Spec has no `paths` — is this really an OpenAPI document?")

    files = scaffold_mcp_server(spec_data, server_name=name)
    output.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        target = output / filename
        if target.exists():
            raise typer.BadParameter(f"{target} already exists — refusing to overwrite")
        target.write_text(content)
    typer.echo(f"Scaffolded MCP server in {output}/ — review server.py before deploying")


if __name__ == "__main__":
    app()
