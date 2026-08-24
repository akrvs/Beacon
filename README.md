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
![tests](https://img.shields.io/badge/tests-113%20passing-brightgreen)

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
uv run beacon audit shop.example --md report.md     # Markdown report for issues/PRs
uv run beacon audit shop.example --csv report.csv   # CSV report (ranking CSV with --file)
uv run beacon audit shop.example --min-score 70     # CI gate: exit 1 below threshold
uv run beacon audit shop.example --only crawl_policy,content  # run a subset of layers
uv run beacon audit shop.example --skip checkout    # or skip layers instead
uv run beacon audit shop.example --fail-only        # show only WARN/FAIL findings
uv run beacon score shop.example                    # just the bare number, for scripts
uv run beacon audit --file domains.txt              # batch audit → ranking table
uv run beacon audit --file domains.txt --parallel 8 # widen the batch concurrency bound
uv run beacon audit --file rivals.txt --html bench.html  # competitor benchmark report
uv run beacon compare shop.example rival.example    # head-to-head terminal diff
uv run beacon compare shop.example rival.example --html versus.html  # shareable comparison
uv run beacon diff shop.example                     # what changed since the last audit
uv run beacon diff shop.example --from 3 --to 1     # any two runs by history index
uv run beacon history shop.example                  # recorded runs; --export and --prune
uv run beacon watch shop.example -i 6h              # scheduled re-audits, diff on change
uv run beacon watch --file rivals.txt --once        # one cycle (cron-friendly): exit 3 on change
uv run beacon watch shop.example --badge badge.json # keep the badge JSON fresh every cycle
uv run beacon badge shop.example -o badge.json      # shields.io endpoint JSON from the last audit
uv run beacon badge shop.example --md --url https://you.example/badge.json  # README badge line
uv run beacon config                                # resolved beacon.toml + unknown keys
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
uv run beacon generate llms-full shop.example -o llms-full.txt  # full-text companion file
uv run beacon generate robots-txt shop.example             # unblock agent fetchers, keep training bots
uv run beacon generate sitemap shop.example -o sitemap.xml # homepage links → sitemap.xml draft
uv run beacon generate schema shop.example                 # Product JSON-LD draft from a product page
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
were detected; `--html status.html` rewrites a self-updating status page
(the benchmark layout when watching a file of domains) every cycle.

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
uv run beacon simulate shop.example --json   # machine-readable verdicts
```

## [ Loadout ] — architecture

```
src/beacon/
├── cli.py              audit · score · compare · watch · diff · history · badge · config · simulate · generate
├── config.py           beacon.toml defaults (audit.min_score/only/skip/ignore/parallel, watch.interval/webhook)
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
    ├── llmstxt.py      sitemap → curated llms.txt and full-text llms-full.txt drafts
    ├── robotstxt.py    corrected robots.txt: agent fetchers allowed, training rules kept
    ├── schema.py       product page → Product/Offer JSON-LD draft
    ├── sitemapxml.py   homepage links → sitemap.xml draft
    └── mcp_scaffold.py OpenAPI spec → runnable FastMCP server project
```

## [ Patch Notes ] — hardening round

- In-flight requests are awaited on shutdown instead of abandoned, so a
  Ctrl-C mid-audit no longer leaves orphaned connections behind
- robots.txt rules compile once per rule and match every sitemap URL from
  cache - large sitemaps audit noticeably faster
- Audit runs land on disk atomically (temp file + rename): a crash mid-write
  can never leave a truncated JSON that breaks later `diff`, `history`, or
  `badge` reads

## [ New Weapons ]

- **Score trend lines** — `beacon history` ends with a block-character
  sparkline of your recent scores, and watch mode appends the same trend to
  every change line. Progress you can see at a glance.
- **Webhook embeds** — `watch --webhook` detects Discord and Slack endpoints
  and ships formatted embeds/text instead of raw JSON; anything else still
  gets the machine-readable payload.
- **Plugin checks** — installed packages can register extra checks via the
  `beacon.checks` entry-point group: expose a class with `id`, `layer`, and an
  async `run(site)`. Malformed plugins are skipped, never fatal.
- **CI badge workflow** — `.github/workflows/badge.yml` re-audits
  `$BEACON_BADGE_DOMAIN` nightly (or on demand), refreshes `badge.json` +
  `badge.md`, and commits them. Set the repo variable and it runs itself.

## [ Rules of Engagement ]

- Honest user agent (`BeaconBot/0.1`), no browser impersonation
- Read-only GETs, response-cached, rate-limited — one polite pass per audit
- Obeys the target's robots.txt for its own crawling: discovered pages the
  site disallows for BeaconBot are never fetched
- SPA catch-alls that answer 200-HTML to everything are detected, not counted
- Builds readiness and discovery; never touches payments
