"""Render an audit as JSON or a human-readable terminal report."""

from __future__ import annotations

import html
from datetime import datetime, timezone

from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.scoring import ScoreCard

_STATUS_MARK = {
    Status.PASS: "✓ PASS",
    Status.WARN: "! WARN",
    Status.FAIL: "✗ FAIL",
    Status.INFO: "i INFO",
}

_LAYER_TITLE = {
    Layer.CRAWL_POLICY: "Crawl policy",
    Layer.CONTENT: "AI-readable content",
    Layer.API_MCP: "API / MCP availability",
    Layer.CHECKOUT: "Agent checkout readiness",
}


def payload(domain: str, findings: list[Finding], card: ScoreCard) -> dict:
    return {
        "domain": domain,
        "audited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **card.to_dict(),
        "findings": [f.to_dict() for f in findings],
    }


def render_text(domain: str, findings: list[Finding], card: ScoreCard) -> str:
    lines = [
        f"Beacon audit — {domain}",
        "=" * (15 + len(domain)),
        "",
        f"Agent visibility today : {_fmt(card.today.percent)}",
        f"Future readiness       : {_fmt(card.future.percent)}",
    ]
    for layer in Layer:
        layer_findings = [f for f in findings if f.layer is layer]
        if not layer_findings:
            continue
        lines += ["", f"{_LAYER_TITLE[layer]}", "-" * len(_LAYER_TITLE[layer])]
        for finding in layer_findings:
            tier_tag = " [future]" if finding.tier is Tier.FUTURE else ""
            lines.append(f"  {_STATUS_MARK[finding.status]}{tier_tag}  {finding.summary}")
            if finding.evidence:
                lines.append(f"           evidence: {finding.evidence}")
            if finding.fix and finding.status in (Status.WARN, Status.FAIL):
                lines.append(f"           fix: {finding.fix}")
    fixes = [f for f in findings if f.fix and f.status in (Status.WARN, Status.FAIL)]
    if fixes:
        lines += ["", f"{len(fixes)} concrete fix(es) listed above."]
    return "\n".join(lines)


def _fmt(percent: int | None) -> str:
    return f"{percent}/100" if percent is not None else "n/a (no checks in this tier yet)"


def render_markdown(domain: str, findings: list[Finding], card: ScoreCard) -> str:
    audited = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Beacon audit — {domain}",
        "",
        f"Audited {audited}",
        "",
        f"- Agent visibility today: **{_fmt(card.today.percent)}**",
        f"- Future readiness: {_fmt(card.future.percent)}",
    ]
    for layer in Layer:
        layer_findings = [f for f in findings if f.layer is layer]
        if not layer_findings:
            continue
        lines += ["", f"## {_LAYER_TITLE[layer]}", "", "| Status | Check | Summary | Fix |", "|---|---|---|---|"]
        for finding in layer_findings:
            status = finding.status.value.upper()
            if finding.tier is Tier.FUTURE:
                status += " (future)"
            summary = finding.summary
            if finding.evidence:
                summary += f" — evidence: {finding.evidence}"
            fix = finding.fix if finding.fix and finding.status in (Status.WARN, Status.FAIL) else ""
            lines.append(
                f"| {status} | {_md_cell(finding.id)} | {_md_cell(summary)} | {_md_cell(fix)} |"
            )
    return "\n".join(lines) + "\n"


def render_ranking_markdown(results: list[tuple[str, list[Finding], ScoreCard]]) -> str:
    audited = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Beacon benchmark — {len(results)} domains",
        "",
        f"Audited {audited}",
        "",
        "| # | Domain | Today | Future | Fixes |",
        "|---|---|---|---|---|",
    ]
    for rank, (domain, findings, card) in enumerate(results, start=1):
        fixes = sum(1 for f in findings if f.fix and f.status in (Status.WARN, Status.FAIL))
        lines.append(
            f"| {rank} | {_md_cell(domain)} | {_num(card.today.percent)}"
            f" | {_num(card.future.percent)} | {fixes} |"
        )
    return "\n".join(lines) + "\n"


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


_HTML_STATUS = {
    Status.PASS: ("PASS", "pass"),
    Status.WARN: ("WARN", "warn"),
    Status.FAIL: ("FAIL", "fail"),
    Status.INFO: ("INFO", "info"),
}


def render_html(domain: str, findings: list[Finding], card: ScoreCard) -> str:
    """Self-contained shareable HTML report (no external assets, light/dark)."""
    audited = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = []
    for layer in Layer:
        layer_findings = [f for f in findings if f.layer is layer]
        if not layer_findings:
            continue
        rows = []
        for finding in layer_findings:
            label, css = _HTML_STATUS[finding.status]
            tier = '<span class="tier">future</span>' if finding.tier is Tier.FUTURE else ""
            evidence = (
                f'<div class="detail">evidence: {_esc(finding.evidence)}</div>'
                if finding.evidence
                else ""
            )
            fix = (
                f'<div class="detail fix">fix: {_esc(finding.fix)}</div>'
                if finding.fix and finding.status in (Status.WARN, Status.FAIL)
                else ""
            )
            rows.append(
                f'<li><span class="badge {css}">{label}</span>{tier}'
                f"<span>{_esc(finding.summary)}</span>{evidence}{fix}</li>"
            )
        sections.append(
            f"<section><h2>{_LAYER_TITLE[layer]}</h2><ul>{''.join(rows)}</ul></section>"
        )
    return _HTML_TEMPLATE.format(
        domain=_esc(domain),
        audited=audited,
        today=_fmt(card.today.percent),
        future=_fmt(card.future.percent),
        sections="".join(sections),
    )


def render_benchmark_html(results: list[tuple[str, list[Finding], ScoreCard]]) -> str:
    """Ranked side-by-side comparison of several audited domains (sales-ready HTML).

    `results` must already be sorted best-first, as `beacon audit --file` ranks them.
    """
    audited = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    domains = [domain for domain, _, _ in results]

    ranking_rows = []
    for rank, (domain, findings, card) in enumerate(results, start=1):
        fixes = sum(1 for f in findings if f.fix and f.status in (Status.WARN, Status.FAIL))
        layer_cells = "".join(
            f"<td>{_pct(card.layers.get(layer, {}).get(Tier.TODAY))}</td>" for layer in Layer
        )
        css = ' class="leader"' if rank == 1 else ""
        ranking_rows.append(
            f"<tr{css}><td>{rank}</td><td>{_esc(domain)}</td>"
            f"<td><strong>{_num(card.today.percent)}</strong></td>"
            f"<td>{_num(card.future.percent)}</td>{layer_cells}<td>{fixes}</td></tr>"
        )
    layer_headers = "".join(f"<th>{_LAYER_TITLE[layer]}</th>" for layer in Layer)

    by_domain = {domain: {f.id: f for f in findings} for domain, findings, _ in results}
    matrix_sections = []
    for layer in Layer:
        check_ids: list[str] = []
        for _, findings, _ in results:
            for finding in findings:
                if finding.layer is layer and finding.id not in check_ids:
                    check_ids.append(finding.id)
        if not check_ids:
            continue
        rows = []
        for check_id in check_ids:
            cells = []
            for domain in domains:
                finding = by_domain[domain].get(check_id)
                if finding is None:
                    cells.append('<td class="na">—</td>')
                else:
                    label, css = _HTML_STATUS[finding.status]
                    cells.append(
                        f'<td><span class="badge {css}" title="{_esc(finding.summary)}">'
                        f"{label}</span></td>"
                    )
            rows.append(f"<tr><td class=\"check\">{_esc(check_id)}</td>{''.join(cells)}</tr>")
        matrix_sections.append(
            f'<tr class="layer-row"><td colspan="{len(domains) + 1}">'
            f"{_LAYER_TITLE[layer]}</td></tr>" + "".join(rows)
        )
    domain_headers = "".join(f"<th>{_esc(domain)}</th>" for domain in domains)

    return _BENCHMARK_TEMPLATE.format(
        count=len(results),
        audited=audited,
        leader=_esc(domains[0]) if domains else "",
        layer_headers=layer_headers,
        ranking_rows="".join(ranking_rows),
        domain_headers=domain_headers,
        matrix_rows="".join(matrix_sections),
    )


_RANK = {Status.PASS: 2, Status.WARN: 1, Status.FAIL: 0}


def render_compare(
    left: tuple[str, list[Finding], ScoreCard],
    right: tuple[str, list[Finding], ScoreCard],
) -> str:
    (left_domain, left_findings, left_card) = left
    (right_domain, right_findings, right_card) = right
    left_by_id = {f.id: f for f in left_findings}
    right_by_id = {f.id: f for f in right_findings}
    label_width = max(
        len("Agent visibility today"),
        *(len(f"  {f.id}") for f in left_findings + right_findings),
    )
    left_width = max(len(left_domain), 6)

    def row(label: str, a: str, b: str, marker: str = "") -> str:
        return f"{label.ljust(label_width)}  {a.ljust(left_width)}  {b}{marker}".rstrip()

    title = f"Beacon compare — {left_domain} vs {right_domain}"
    lines = [
        title,
        "=" * len(title),
        "",
        row("", left_domain, right_domain),
        row("Agent visibility today", _num(left_card.today.percent), _num(right_card.today.percent)),
        row("Future readiness", _num(left_card.future.percent), _num(right_card.future.percent)),
    ]

    left_wins = right_wins = 0
    for layer in Layer:
        check_ids: list[str] = []
        for finding in left_findings + right_findings:
            if finding.layer is layer and finding.id not in check_ids:
                check_ids.append(finding.id)
        if not check_ids:
            continue
        lines += ["", _LAYER_TITLE[layer], "-" * len(_LAYER_TITLE[layer])]
        for check_id in check_ids:
            a = left_by_id.get(check_id)
            b = right_by_id.get(check_id)
            a_rank = _RANK.get(a.status) if a is not None else None
            b_rank = _RANK.get(b.status) if b is not None else None
            marker = ""
            if a_rank is not None and b_rank is not None and a_rank != b_rank:
                if a_rank > b_rank:
                    left_wins += 1
                    marker = f"  <- {left_domain}"
                else:
                    right_wins += 1
                    marker = f"  <- {right_domain}"
            lines.append(row(f"  {check_id}", _status_word(a), _status_word(b), marker))

    lines += ["", f"{left_domain} leads on {left_wins} check(s), {right_domain} on {right_wins}."]
    return "\n".join(lines)


def _status_word(finding: Finding | None) -> str:
    return finding.status.value.upper() if finding is not None else "-"


def _num(percent: int | None) -> str:
    return str(percent) if percent is not None else "–"


def _pct(tier_score) -> str:
    percent = tier_score.percent if tier_score is not None else None
    return _num(percent)


_esc = html.escape


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Beacon audit — {domain}</title>
<style>
  :root {{
    --bg: #ffffff; --fg: #1a1d21; --muted: #5c6470; --line: #e3e6ea;
    --pass: #1a7f37; --warn: #9a6700; --fail: #cf222e; --info: #57606a;
    --chip-pass: #dafbe1; --chip-warn: #fff8c5; --chip-fail: #ffebe9; --chip-info: #eaeef2;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0d1117; --fg: #e6edf3; --muted: #8b949e; --line: #30363d;
      --pass: #3fb950; --warn: #d29922; --fail: #f85149; --info: #8b949e;
      --chip-pass: #12261e; --chip-warn: #272115; --chip-fail: #2d1618; --chip-info: #21262d;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--fg);
         font: 16px/1.5 system-ui, -apple-system, sans-serif; }}
  main {{ max-width: 860px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }}
  h1 {{ font-size: 1.4rem; margin: 0; }} h1 span {{ color: var(--muted); font-weight: 400; }}
  .meta {{ color: var(--muted); font-size: .85rem; margin-top: .25rem; }}
  .scores {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 1.75rem 0 .5rem; }}
  .tile {{ flex: 1 1 220px; border: 1px solid var(--line); border-radius: 10px; padding: 1rem 1.25rem; }}
  .tile .label {{ color: var(--muted); font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; }}
  .tile .value {{ font-size: 2.2rem; font-weight: 700; font-variant-numeric: tabular-nums; }}
  section {{ margin-top: 2rem; }}
  h2 {{ font-size: 1.05rem; border-bottom: 1px solid var(--line); padding-bottom: .4rem; }}
  ul {{ list-style: none; margin: 0; padding: 0; }}
  li {{ padding: .6rem 0; border-bottom: 1px solid var(--line); }}
  .badge {{ display: inline-block; font-size: .72rem; font-weight: 700; padding: .1rem .5rem;
           border-radius: 999px; margin-right: .6rem; vertical-align: 1px; }}
  .badge.pass {{ color: var(--pass); background: var(--chip-pass); }}
  .badge.warn {{ color: var(--warn); background: var(--chip-warn); }}
  .badge.fail {{ color: var(--fail); background: var(--chip-fail); }}
  .badge.info {{ color: var(--info); background: var(--chip-info); }}
  .tier {{ color: var(--muted); font-size: .72rem; border: 1px solid var(--line);
          border-radius: 999px; padding: .05rem .45rem; margin-right: .6rem; }}
  .detail {{ color: var(--muted); font-size: .85rem; margin: .25rem 0 0 .35rem;
            overflow-wrap: anywhere; }}
  .detail.fix {{ color: var(--fg); }}
  footer {{ color: var(--muted); font-size: .8rem; margin-top: 2.5rem; }}
</style>
</head>
<body>
<main>
  <h1>Beacon audit <span>— {domain}</span></h1>
  <div class="meta">{audited}</div>
  <div class="scores">
    <div class="tile"><div class="label">Agent visibility today</div><div class="value">{today}</div></div>
    <div class="tile"><div class="label">Future readiness</div><div class="value">{future}</div></div>
  </div>
  {sections}
  <footer>Generated by <a href="https://github.com/akrvs/Beacon">Beacon</a> — agent-readiness audits.</footer>
</main>
</body>
</html>
"""

_BENCHMARK_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Beacon benchmark — {count} domains</title>
<style>
  :root {{
    --bg: #ffffff; --fg: #1a1d21; --muted: #5c6470; --line: #e3e6ea;
    --pass: #1a7f37; --warn: #9a6700; --fail: #cf222e; --info: #57606a;
    --chip-pass: #dafbe1; --chip-warn: #fff8c5; --chip-fail: #ffebe9; --chip-info: #eaeef2;
    --leader: #f0f7ff;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0d1117; --fg: #e6edf3; --muted: #8b949e; --line: #30363d;
      --pass: #3fb950; --warn: #d29922; --fail: #f85149; --info: #8b949e;
      --chip-pass: #12261e; --chip-warn: #272115; --chip-fail: #2d1618; --chip-info: #21262d;
      --leader: #101a2b;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--fg);
         font: 16px/1.5 system-ui, -apple-system, sans-serif; }}
  main {{ max-width: 1020px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }}
  h1 {{ font-size: 1.4rem; margin: 0; }} h1 span {{ color: var(--muted); font-weight: 400; }}
  .meta {{ color: var(--muted); font-size: .85rem; margin-top: .25rem; }}
  h2 {{ font-size: 1.05rem; margin-top: 2.25rem; border-bottom: 1px solid var(--line);
       padding-bottom: .4rem; }}
  .scroll {{ overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .9rem; }}
  th, td {{ text-align: left; padding: .5rem .75rem; border-bottom: 1px solid var(--line);
           white-space: nowrap; }}
  th {{ color: var(--muted); font-size: .75rem; text-transform: uppercase; letter-spacing: .05em; }}
  td {{ font-variant-numeric: tabular-nums; }}
  tr.leader td {{ background: var(--leader); }}
  tr.layer-row td {{ color: var(--muted); font-size: .75rem; text-transform: uppercase;
                    letter-spacing: .05em; padding-top: 1.1rem; }}
  td.check {{ color: var(--muted); font-family: ui-monospace, monospace; font-size: .82rem; }}
  td.na {{ color: var(--muted); }}
  .badge {{ display: inline-block; font-size: .72rem; font-weight: 700; padding: .1rem .5rem;
           border-radius: 999px; }}
  .badge.pass {{ color: var(--pass); background: var(--chip-pass); }}
  .badge.warn {{ color: var(--warn); background: var(--chip-warn); }}
  .badge.fail {{ color: var(--fail); background: var(--chip-fail); }}
  .badge.info {{ color: var(--info); background: var(--chip-info); }}
  footer {{ color: var(--muted); font-size: .8rem; margin-top: 2.5rem; }}
</style>
</head>
<body>
<main>
  <h1>Beacon benchmark <span>— {count} domains, leader: {leader}</span></h1>
  <div class="meta">{audited}</div>

  <h2>Ranking (agent visibility today)</h2>
  <div class="scroll">
    <table>
      <thead><tr><th>#</th><th>Domain</th><th>Today</th><th>Future</th>{layer_headers}<th>Fixes</th></tr></thead>
      <tbody>{ranking_rows}</tbody>
    </table>
  </div>

  <h2>Check-by-check comparison</h2>
  <div class="scroll">
    <table>
      <thead><tr><th>Check</th>{domain_headers}</tr></thead>
      <tbody>{matrix_rows}</tbody>
    </table>
  </div>

  <footer>Generated by <a href="https://github.com/akrvs/Beacon">Beacon</a> — agent-readiness audits.</footer>
</main>
</body>
</html>
"""
