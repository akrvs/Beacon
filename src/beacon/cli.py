"""Beacon CLI: `beacon audit <domain>`."""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import typer
import yaml

from beacon import history, report
from beacon.checks import ALL_CHECKS
from beacon.checks.base import Finding
from beacon.fetch import Site, USER_AGENT, normalize_base_url
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
    try:
        results = await asyncio.gather(*(check.run(site) for check in ALL_CHECKS))
    finally:
        await site.aclose()
    return site, [finding for check_findings in results for finding in check_findings]


@app.command()
def audit(
    domain: str = typer.Argument(None, help="Domain or URL to audit, e.g. example.com"),
    domains_file: Path = typer.Option(
        None, "--file", "-f", help="Audit every domain in this file (one per line) and print a ranking"
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit the report as JSON"),
    html: Path = typer.Option(
        None,
        "--html",
        help="Also write a shareable HTML report (a ranked benchmark when used with --file)",
    ),
    min_score: int = typer.Option(
        None,
        "--min-score",
        help="Exit 1 if any today-score is below this threshold (for CI)",
        min=0,
        max=100,
    ),
    save: bool = typer.Option(True, "--save/--no-save", help="Record the run in audit history"),
) -> None:
    """Audit one domain (or a file of domains) and print a scored report."""
    if (domain is None) == (domains_file is None):
        raise typer.BadParameter("Provide either DOMAIN or --file, not both")
    if domains_file is not None:
        _audit_batch(domains_file, json_out=json_out, min_score=min_score, save=save, html=html)
        return

    site, findings = asyncio.run(run_audit(domain))
    card = score(findings)
    data = report.payload(site.domain, findings, card)
    if json_out:
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        typer.echo(report.render_text(site.domain, findings, card))
    if html is not None:
        html.write_text(report.render_html(site.domain, findings, card), encoding="utf-8")
        typer.echo(f"\nHTML report written to {html}")
    if save:
        history.save_run(site.domain, data)
    if min_score is not None and (card.today.percent or 0) < min_score:
        typer.echo(f"Score {card.today.percent or 0} is below --min-score {min_score}", err=True)
        raise typer.Exit(1)


MAX_PARALLEL_SITES = 4


def _read_domains(domains_file: Path) -> list[str]:
    domains = [
        line.strip()
        for line in domains_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not domains:
        raise typer.BadParameter(f"{domains_file} contains no domains")
    return domains


def _run_audits(domains: list[str]) -> list[tuple[Site, list[Finding]]]:
    async def run_all() -> list[tuple[Site, list[Finding]]]:
        gate = asyncio.Semaphore(MAX_PARALLEL_SITES)

        async def one(entry: str) -> tuple[Site, list[Finding]]:
            async with gate:
                return await run_audit(entry)

        return list(await asyncio.gather(*(one(entry) for entry in domains)))

    return asyncio.run(run_all())


def _audit_batch(
    domains_file: Path, *, json_out: bool, min_score: int | None, save: bool, html: Path | None
) -> None:
    domains = _read_domains(domains_file)
    results = []
    payloads: dict[str, dict] = {}
    for site, findings in _run_audits(domains):
        card = score(findings)
        results.append((site.domain, findings, card))
        payloads[site.domain] = report.payload(site.domain, findings, card)
        if save:
            history.save_run(site.domain, payloads[site.domain])
    results.sort(key=lambda item: item[2].today.percent or 0, reverse=True)

    if html is not None:
        html.write_text(report.render_benchmark_html(results), encoding="utf-8")
        typer.echo(f"Benchmark HTML written to {html}", err=json_out)

    if json_out:
        batch = [payloads[domain] for domain, _, _ in results]
        typer.echo(json.dumps(batch, indent=2, ensure_ascii=False))
    else:
        width = max(len(domain) for domain, _, _ in results)
        typer.echo(f"rank  {'domain'.ljust(width)}  today  future  fixes")
        for rank, (domain, findings, card) in enumerate(results, start=1):
            fixes = sum(1 for f in findings if f.fix and f.status.value in ("warn", "fail"))
            today = card.today.percent if card.today.percent is not None else "-"
            future = card.future.percent if card.future.percent is not None else "-"
            typer.echo(
                f"{str(rank).ljust(4)}  {domain.ljust(width)}  {str(today).ljust(5)}  {str(future).ljust(6)}  {fixes}"
            )

    if min_score is not None:
        failing = [
            domain
            for domain, _, card in results
            if (card.today.percent or 0) < min_score
        ]
        if failing:
            typer.echo(f"Below --min-score {min_score}: {', '.join(failing)}", err=True)
            raise typer.Exit(1)


@app.command()
def simulate(
    domain: str = typer.Argument(..., help="Domain to test with a simulated agent"),
    model: str = typer.Option("claude-opus-4-8", "--model", help="Claude model to simulate with"),
    json_out: bool = typer.Option(False, "--json", help="Emit the simulation report as JSON"),
) -> None:
    """Have Claude attempt real customer tasks using only what an agent can extract from the site."""
    try:
        import anthropic
    except ImportError:
        typer.echo(
            "The simulate command needs the AI extra: uv sync --extra ai (and Anthropic API credentials)",
            err=True,
        )
        raise typer.Exit(2)
    from beacon.simulate import simulate_domain

    no_credentials = (
        "No valid Anthropic credentials — set ANTHROPIC_API_KEY or run `ant auth login`"
    )
    client = anthropic.Anthropic()
    try:
        typer.echo(simulate_domain(domain, client, model, json_out=json_out))
    except (TypeError, anthropic.AuthenticationError):
        typer.echo(no_credentials, err=True)
        raise typer.Exit(2)


@app.command()
def diff(
    domain: str = typer.Argument(..., help="Domain with at least two recorded audits"),
) -> None:
    """Compare the two most recent recorded audits of a domain."""
    key = httpx.URL(normalize_base_url(domain)).host
    runs = history.load_runs(key, limit=2)
    if len(runs) < 2:
        typer.echo(
            f"Need two recorded runs for {key}, found {len(runs)} — run `beacon audit {key}` (history saves automatically)",
            err=True,
        )
        raise typer.Exit(2)
    typer.echo(history.diff_runs(runs[0], runs[1]))


_INTERVAL_UNITS = {"": 60, "s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_interval(text: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([smhd]?)", text.strip().lower())
    if not match:
        raise typer.BadParameter(f"Can't parse interval {text!r} — use e.g. 45m, 6h, 1d")
    return float(match[1]) * _INTERVAL_UNITS[match[2]]


@app.command()
def watch(
    domain: str = typer.Argument(None, help="Domain or URL to re-audit on a schedule"),
    domains_file: Path = typer.Option(
        None, "--file", "-f", help="Watch every domain in this file (one per line)"
    ),
    interval: str = typer.Option(
        "6h", "--interval", "-i", help="Time between audits: 30m, 6h, 1d (bare number = minutes)"
    ),
    once: bool = typer.Option(
        False, "--once", help="Run one cycle and exit; exit code 3 if anything changed (for cron/CI)"
    ),
    webhook: str = typer.Option(
        None, "--webhook", help="POST a JSON change notification to this URL when a domain changes"
    ),
) -> None:
    """Re-audit on a schedule and report what changed since the previous recorded run."""
    if (domain is None) == (domains_file is None):
        raise typer.BadParameter("Provide either DOMAIN or --file, not both")
    domains = _read_domains(domains_file) if domains_file is not None else [domain]
    seconds = _parse_interval(interval)

    while True:
        any_changes = _watch_cycle(domains, webhook)
        if once:
            raise typer.Exit(3 if any_changes else 0)
        typer.echo(f"Next audit in {interval} — Ctrl-C to stop.")
        try:
            time.sleep(seconds)
        except KeyboardInterrupt:
            typer.echo("Watch stopped.")
            return


def _watch_cycle(domains: list[str], webhook: str | None) -> bool:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    any_changes = False
    for site, findings in _run_audits(domains):
        card = score(findings)
        previous = history.load_runs(site.domain, limit=1)
        current = report.payload(site.domain, findings, card)
        history.save_run(site.domain, current)
        today = card.today.percent if card.today.percent is not None else "n/a"
        if not previous:
            typer.echo(f"[{stamp}] {site.domain}: baseline recorded (today {today})")
            continue
        summary = history.change_summary(previous[0], current)
        if not summary["has_changes"]:
            typer.echo(f"[{stamp}] {site.domain}: no changes (today {today})")
            continue
        any_changes = True
        diff_text = history.diff_runs(previous[0], current)
        typer.echo(f"[{stamp}] {site.domain}: CHANGED")
        typer.echo("\n".join(f"  {line}" for line in diff_text.splitlines()))
        if webhook:
            _notify_webhook(webhook, {**summary, "diff": diff_text})
    return any_changes


def _notify_webhook(url: str, payload: dict) -> None:
    try:
        response = httpx.post(
            url, json=payload, headers={"User-Agent": USER_AGENT}, timeout=15.0
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        typer.echo(f"  webhook notification failed: {error}", err=True)


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
        output.write_text(text, encoding="utf-8")
        typer.echo(f"Wrote {output} — review the draft before publishing it at /llms.txt")
    else:
        typer.echo(text)


@generate_app.command("mcp")
def mcp(
    spec: str = typer.Argument(..., help="Path or URL to an OpenAPI spec (JSON or YAML)"),
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
        raw = Path(spec).read_text(encoding="utf-8")
    try:
        spec_data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            spec_data = yaml.safe_load(raw)
        except yaml.YAMLError as error:
            raise typer.BadParameter(f"Spec is neither valid JSON nor YAML: {error}") from error
    if not isinstance(spec_data, dict) or not spec_data.get("paths"):
        raise typer.BadParameter("Spec has no `paths` — is this really an OpenAPI document?")

    files = scaffold_mcp_server(spec_data, server_name=name)
    output.mkdir(parents=True, exist_ok=True)
    existing = [str(output / filename) for filename in files if (output / filename).exists()]
    if existing:
        raise typer.BadParameter(f"{', '.join(existing)} already exist(s) — refusing to overwrite")
    for filename, content in files.items():
        (output / filename).write_text(content, encoding="utf-8")
    typer.echo(f"Scaffolded MCP server in {output}/ — review server.py before deploying")


if __name__ == "__main__":
    app()
