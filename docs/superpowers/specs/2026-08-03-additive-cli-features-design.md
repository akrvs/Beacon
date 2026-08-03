# Twelve additive CLI features — design

Date: 2026-08-03
Status: approved

## Goal

Extend Beacon with twelve small, strictly additive features. Existing behavior
must not change: every feature is a new flag, command, or config key, and with
none of them used the tool behaves exactly as before. Each feature lands in its
own commit with a test; a final docs commit updates the README.

## Constraints

- No changes to existing command semantics, output formats, or exit codes.
- Commit messages: one line, conventional prefix (`feat:` / `docs:`), no
  emojis, no body, no attribution trailers.
- Each feature ships with at least one test in the existing pytest suite
  (CliRunner + respx + `BEACON_HOME` isolation, as in `tests/test_cli.py`).

## Features

### Audit / report

1. `audit --csv PATH`
   Mirrors `--html`/`--md` plumbing. With `--file`: ranking CSV with columns
   rank, domain, today, future, fixes. Single domain: findings CSV with
   columns layer, id, status, tier, summary, fix. Implemented as
   `report.render_csv` and `report.render_ranking_csv` using the stdlib `csv`
   module writing to `io.StringIO`.

2. `audit --fail-only`
   Terminal text report only. `report.render_text` gains a keyword-only
   `fail_only: bool = False` that skips PASS and INFO findings. The score is
   computed from all findings before filtering, so numbers are identical.
   JSON, HTML, and Markdown outputs are unaffected.

3. `beacon score DOMAIN`
   New command. Runs a fresh audit, prints only the bare today-score integer
   (`n/a` prints as `n/a`, exit 0 either way). Saves to history like `audit`
   (respects `--save/--no-save`).

4. `audit.ignore` in beacon.toml
   `[audit] ignore = ["finding-id", ...]` — a list of finding IDs removed from
   results before scoring. Applied inside `run_audit` in `cli.py`, the single
   shared entry point, so `audit`, `compare`, `score`, and `watch` all agree
   and history diffs never see phantom added/removed checks. No config key,
   no change.

### Generators / outputs

5. `generate sitemap`
   New generate command: fetches the homepage, collects same-host links via
   `discover.homepage_links`, dedupes, and emits a sitemap.xml (homepage
   first) using `xml.etree.ElementTree`. `-o/--output` like the other
   generators; stdout by default.

6. `compare --html PATH`
   New option on `compare`. Reuses `report.render_benchmark_html` with the
   two results — the ranked table plus per-check matrix already is the
   head-to-head layout. No new render code.

7. `badge --md`
   New flag on `badge`: instead of the JSON, emit the ready-to-paste
   Markdown line `![agent visibility](https://img.shields.io/endpoint?url=...)`.
   Optional `--url` supplies the hosted location of the badge JSON
   (URL-encoded into the shields endpoint); without it a
   `<BADGE-JSON-URL>` placeholder is used. `--output` still works.

8. `generate llms-full`
   New generate command producing an llms-full.txt companion: the same
   curated page selection as `generate llms-txt`, but each section carries
   the full extracted page text (selectolax text extraction as in
   `simulate.py`), separated by `---` dividers. Lives in
   `generate/llmstxt.py` beside the existing generator to share helpers.

### Watch / history / CI

9. `watch --badge PATH`
   Single-domain watch only (`--file` + `--badge` is a usage error). After
   every cycle the shields endpoint JSON is rewritten from the fresh score.
   The badge payload builder is extracted from the `badge` command into a
   shared helper so both paths emit identical JSON.

10. `history` index column + `diff --from/--to`
    `beacon history <domain>` gains a leading `#` column numbering runs with
    1 = newest. `beacon diff <domain>` gains `--from N --to M` (defaults 2
    and 1, which is exactly the current latest-vs-previous behavior) to diff
    any two recorded runs by those indexes.

11. `audit --parallel N`
    The existing hardcoded `MAX_PARALLEL_SITES = 4` bound for `--file` batch
    audits becomes configurable: `--parallel` flag, `audit.parallel` config
    fallback, default 4. Minimum 1.

12. `beacon config`
    New command that reports which beacon.toml was loaded (project-local,
    `$BEACON_HOME`, or none), prints the resolved known keys
    (`audit.min_score`, `audit.only`, `audit.skip`, `audit.ignore`,
    `audit.parallel`, `watch.interval`, `watch.webhook`), and warns about
    unknown sections or keys. `config.py` gains a `find_config() -> Path |
    None` helper so the command and `load_config` agree on the search order.

## Error handling

- New flags validate through Typer (`BadParameter`) exactly like existing
  ones: conflicting flags, bad indexes, `--badge` with `--file`.
- `diff --from/--to` indexes beyond recorded history exit 2 with the same
  style of message the command uses today.

## Testing

One focused test (or small set) per feature, following the existing
CliRunner/respx patterns. The full suite must stay green after every commit.

## Commit plan

Twelve `feat:` commits in the order above, then one `docs:` commit for the
README and test-count badge.
