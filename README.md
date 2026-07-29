```
██████╗ ███████╗ █████╗  ██████╗ ██████╗ ███╗   ██╗
██╔══██╗██╔════╝██╔══██╗██╔════╝██╔═══██╗████╗  ██║
██████╔╝█████╗  ███████║██║     ██║   ██║██╔██╗ ██║
██╔══██╗██╔══╝  ██╔══██║██║     ██║   ██║██║╚██╗██║
██████╔╝███████╗██║  ██║╚██████╗╚██████╔╝██║ ╚████║
╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝
                   a k r v s
```

> AI agents are already browsing, buying, and booking — and most sites are
> invisible to them. Beacon points at any domain, reads it the way an agent
> does, and hands back a scored report: what agents can see today, what
> they'll expect tomorrow, and the exact fixes in between. Then it forges the
> missing pieces itself. SEO was for crawlers. This is for the machines that
> act.

![status](https://img.shields.io/badge/status-ACTIVE-brightgreen)
![category](https://img.shields.io/badge/category-Agents%20%2F%20Discovery-9cf)
![difficulty](https://img.shields.io/badge/difficulty-Medium-yellow)
![python](https://img.shields.io/badge/python-3.12%2B-blue)
![tests](https://img.shields.io/badge/tests-53%20passing-brightgreen)

```
┌─[ TARGET ]──────────────────────────────────────────────────┐
│ codename   : beacon                                         │
│ category   : Agent Readiness / Audit & Generation           │
│ difficulty : Medium                                         │
│ stack      : Python 3.12 · httpx · selectolax · Typer       │
│ layers     : crawl policy · content · api/mcp · checkout    │
│ flags      : user [audit + llms.txt]   root [MCP scaffold]  │
│ status     : OWNED — audit · llms.txt · MCP scaffold live   │
└─────────────────────────────────────────────────────────────┘
```

## [ Briefing ]

Beacon audits a business's web presence for **agent-readiness** and generates
what's missing. The honest part: most "agent standards" (llms.txt, MCP
discovery, UCP/ACP/AP2) have close to zero confirmed consumption today. So
Beacon scores in two tiers and never mixes them:

- **Agent visibility today** — signals real agents actually use right now:
  robots.txt rules for live AI fetchers, schema.org JSON-LD, server-rendered
  text, labeled forms. This drives the headline score.
- **Future readiness** — llms.txt, MCP endpoints, agentic-commerce protocol
  signals. Reported separately, so unproven specs never inflate (or tank) the
  number a merchant acts on.

Protocol-agnostic by construction: every audit is a plugin implementing one
small `Check` protocol. Supporting the next protocol is one new file, not a
refactor. No payments are built here — readiness and discovery only.

## [ Recon ] — the four layers

```
crawl_policy   robots.txt AI-crawler rules (fetchers vs training bots) · sitemap · freshness
content        JS-free text extraction · schema.org JSON-LD · metadata · landmarks · form operability
               product-page deep audit: Product/Offer JSON-LD, price · currency · availability
api_mcp        llms.txt · OpenAPI discovery · MCP endpoint probes · platform detection   [future tier]
checkout       UCP / ACP / AP2 / x402 support signals                                    [future tier]
```

Every finding carries a status (`PASS / WARN / FAIL / INFO`), a weight, a tier,
and a **concrete fix** — the report is a work order, not a lecture.

## [ Foothold ] — install

```bash
git clone https://github.com/akrvs/Beacon.git && cd Beacon
uv sync --group dev
uv run beacon --help
```

## [ User Flag ] — audit a domain

```bash
uv run beacon audit shop.example                    # human report
uv run beacon audit shop.example --json             # machine report
uv run beacon audit shop.example --html report.html # shareable HTML report
uv run beacon audit shop.example --min-score 70     # CI gate: exit 1 below threshold
uv run beacon audit --file domains.txt              # batch audit → ranking table
uv run beacon audit --file rivals.txt --html bench.html  # competitor benchmark report
uv run beacon diff shop.example                     # what changed since the last audit
uv run beacon watch shop.example -i 6h              # scheduled re-audits, diff on change
uv run beacon watch --file rivals.txt --once        # one cycle (cron-friendly): exit 3 on change
```

```
Beacon audit — reddit.com
=========================

Agent visibility today : 33/100

Crawl policy
------------
  ✓ PASS  robots.txt is present and parseable
  ✗ FAIL  robots.txt fully blocks 8 live agent fetcher(s) — the site is invisible to those agents
           evidence: ChatGPT-User, OAI-SearchBot, Claude-User, ...
           fix: Unblock on-demand agent user-agents in robots.txt; ...
```

## [ Root Flag ] — generate the missing pieces

```bash
uv run beacon generate llms-txt shop.example -o llms.txt   # sitemap-driven draft
uv run beacon generate mcp openapi.json                    # runnable MCP server scaffold
```

The MCP scaffold is auth-aware: the spec's `securitySchemes` (apiKey in
header/query/cookie, HTTP bearer/basic, OAuth2 access tokens) are wired into
the generated server as environment variables, each documented in the
scaffold's README. No schemes in the spec → a clearly-labeled generic bearer
stub.

## [ Overwatch ] — watch mode

`beacon watch` re-audits on a schedule and prints a diff only when something
actually changed — new failures, fixed checks, score moves. `--webhook URL`
POSTs the change summary as JSON (Slack-webhook-shaped enough to pipe
anywhere); `--once` runs a single cycle for cron/CI and exits 3 when changes
were detected.

## [ Wargames ] — competitor benchmarking

`beacon audit --file rivals.txt --html bench.html` turns a batch audit into a
sales-ready single-file HTML benchmark: ranked score table with per-layer
breakdown, plus a check-by-check PASS/WARN/FAIL matrix across every domain —
"you fail where your competitor passes" at a glance.

## [ Oracle ] — simulate an agent

The audit checks signals; the oracle checks reality. `beacon simulate` fetches
the site exactly as a text agent sees it (server-rendered HTML, no JavaScript),
hands that text to Claude, and asks it to complete real customer tasks — what
does this business sell, find a price and availability, figure out how to buy.
You get per-task verdicts, an extraction score, and the concrete information
the site fails to expose. Evidence a merchant can't argue with.

```bash
uv sync --extra ai                        # optional AI layer (anthropic SDK)
export ANTHROPIC_API_KEY=sk-ant-...
uv run beacon simulate shop.example
```

## [ Loadout ] — architecture

```
src/beacon/
├── cli.py              audit · watch · diff · simulate · generate
├── fetch.py            polite client: honest UA, deduped, bounded concurrency
├── discover.py         sitemap walking (incl. index children) · homepage links
├── platform.py         Shopify/Woo/Wix/... detection → platform-aware fixes
├── checks/             all run in parallel against one shared fetch cache
│   ├── base.py         Check protocol · Finding · Tier — the plugin contract
│   ├── crawl_policy.py RFC 9309 robots parsing, AI-agent allowlist analysis
│   ├── content.py      what an agent's text extraction actually sees
│   ├── product.py      deep-audits a real product page's Product/Offer JSON-LD
│   ├── api_mcp.py      llms.txt / OpenAPI / MCP discovery probes
│   └── checkout.py     emerging commerce-protocol signals
├── scoring.py          two-tier weighted scoring — today vs future
├── report.py           terminal · JSON · self-contained HTML reports
├── history.py          per-domain run history → `beacon diff`
├── simulate.py         Claude-driven agent dry-run (optional `ai` extra)
└── generate/
    ├── llmstxt.py      sitemap → curated llms.txt draft
    └── mcp_scaffold.py OpenAPI spec → runnable FastMCP server project
```

## [ Rules of Engagement ]

- Honest user agent (`BeaconBot/0.1`), no browser impersonation
- Read-only GETs, response-cached, rate-limited — one polite pass per audit
- Obeys the target's robots.txt for its own crawling: discovered pages the
  site disallows for BeaconBot are never fetched
- SPA catch-alls that answer 200-HTML to everything are detected, not counted
- Builds readiness and discovery; never touches payments

## [ Loot ] — roadmap

- [x] Four-layer audit with two-tier scoring
- [x] llms.txt generator (sitemap-driven, homepage-link fallback)
- [x] MCP server scaffold from an OpenAPI spec
- [x] Product-page deep audit (Product/Offer JSON-LD, price extraction)
- [x] Platform-aware fixes (Shopify/Woo can't self-host MCP — say so)
- [x] Shareable HTML report (--html) and CI gate (--min-score)
- [x] Batch audits (`beacon audit --file domains.txt`) with a ranking table
- [x] Score history: store JSON runs, `beacon diff` between audits
- [x] YAML OpenAPI specs; HTTP/2 + tighter timeouts
- [x] Agentic-discovery sitemap check (Shopify ships sitemap_agentic_discovery.xml)
- [x] Simulated agent task-completion (`beacon simulate`, Claude-powered)
- [x] Auth-aware MCP scaffolds (OpenAPI securitySchemes → real auth wiring)
- [x] Watch mode: scheduled re-audits + diff/webhook notifications (`beacon watch`)
- [x] Competitor benchmarking report (batch + `--html`, ranked side-by-side)
- [x] Beacon obeys robots.txt for its own crawling (RFC 9309 path matching)
- [x] Sitemap freshness check (newest lastmod age)
