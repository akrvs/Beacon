"""Simulated agent task-completion (optional AI layer).

Fetches the site exactly as a text agent sees it — server-rendered HTML,
no JavaScript — then asks Claude to complete realistic customer tasks from
that text alone and grade how much information was extractable. This measures
what the audit's Tier-1 checks approximate: can an agent actually *use* the
site today?

Requires the `ai` extra (`uv sync --extra ai`) and Anthropic API credentials.
"""

from __future__ import annotations

import asyncio
from typing import Literal

import httpx
from pydantic import BaseModel
from selectolax.parser import HTMLParser

from beacon.checks.product import PRODUCT_PATH_HINTS
from beacon.discover import crawlable_urls
from beacon.fetch import Site

MAX_CHARS_PER_PAGE = 8000

TASKS = [
    "Identify what this business sells or does, and for whom",
    "Find one specific product or service with its exact price and availability",
    "Determine how a customer would buy, book, or sign up, step by step",
]


class TaskResult(BaseModel):
    task: str
    answer: str
    status: Literal["answered", "partial", "unanswerable"]


class SimulationReport(BaseModel):
    business_summary: str
    tasks: list[TaskResult]
    extraction_score: int
    missing_information: list[str]


async def gather_agent_view(site: Site) -> dict[str, str]:
    """The pages a text agent would read, reduced to what it can actually see."""
    pages: dict[str, str] = {}
    homepage = await site.homepage()
    if homepage is not None and homepage.status_code < 400:
        pages[site.base_url] = _extract_text(homepage.text)

    for url in await crawlable_urls(site):
        path = httpx.URL(url).path.lower()
        if any(hint in path for hint in PRODUCT_PATH_HINTS) and path.rstrip("/").count("/") >= 2:
            response = await site.get(url)
            if response is not None and response.status_code < 400:
                pages[url] = _extract_text(response.text)
            break
    return pages


def _extract_text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript, template, svg"):
        node.decompose()
    text = tree.body.text(separator=" ") if tree.body else ""
    return " ".join(text.split())[:MAX_CHARS_PER_PAGE]


def build_prompt(domain: str, pages: dict[str, str]) -> str:
    sections = "\n\n".join(
        f"=== PAGE: {url} ===\n{text if text else '(no extractable text)'}"
        for url, text in pages.items()
    )
    task_list = "\n".join(f"{i}. {task}" for i, task in enumerate(TASKS, start=1))
    return (
        f"You are simulating an AI shopping/booking agent visiting {domain}. "
        "Below is the ONLY information available to you: the text an agent extracts "
        "from the site's server-rendered HTML, with no JavaScript executed.\n\n"
        f"{sections}\n\n"
        "Using ONLY the text above (no prior knowledge about this business), attempt these tasks:\n"
        f"{task_list}\n\n"
        "For each task report your answer and whether it was fully answered, partial, or "
        "unanswerable from the text. Then give an extraction_score from 0-100 for how usable "
        "this site is for an autonomous agent today, and list the concrete pieces of "
        "missing_information the site should expose (in text or structured data) to fix the gaps."
    )


def run_simulation(domain: str, pages: dict[str, str], client, model: str) -> SimulationReport:
    response = client.messages.parse(
        model=model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": build_prompt(domain, pages)}],
        output_format=SimulationReport,
    )
    return response.parsed_output


def render_simulation(domain: str, pages: dict[str, str], report: SimulationReport) -> str:
    marks = {"answered": "✓", "partial": "!", "unanswerable": "✗"}
    lines = [
        f"Beacon agent simulation — {domain}",
        "=" * (26 + len(domain)),
        "",
        f"Pages read as an agent : {len(pages)}",
        f"Extraction score       : {report.extraction_score}/100",
        "",
        f"What the agent understood: {report.business_summary}",
        "",
    ]
    for result in report.tasks:
        lines.append(f"  {marks.get(result.status, '?')} [{result.status}] {result.task}")
        lines.append(f"      → {result.answer}")
    if report.missing_information:
        lines += ["", "Missing information to expose:"]
        lines += [f"  - {item}" for item in report.missing_information]
    return "\n".join(lines)


async def fetch_pages(domain: str) -> tuple[str, dict[str, str]]:
    site = Site(domain)
    try:
        pages = await gather_agent_view(site)
    finally:
        await site.aclose()
    return site.domain, pages


def simulate_domain(domain: str, client, model: str) -> str:
    host, pages = asyncio.run(fetch_pages(domain))
    if not pages:
        return f"Could not fetch any pages from {host} — nothing to simulate."
    report = run_simulation(host, pages, client, model)
    return render_simulation(host, pages, report)
