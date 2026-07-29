"""AI-readable content checks: can an agent's text extraction and form
handling actually use this page? Audits the homepage as a representative page."""

from __future__ import annotations

import json

from selectolax.parser import HTMLParser

from beacon.checks.base import Finding, Layer, Status, Tier
from beacon.fetch import Site


class ContentCheck:
    id = "content"
    layer = Layer.CONTENT

    async def run(self, site: Site) -> list[Finding]:
        response = await site.homepage()
        if response is None or response.status_code >= 400:
            status = "unreachable" if response is None else f"HTTP {response.status_code}"
            return [
                Finding(
                    id="homepage-reachable",
                    layer=self.layer,
                    tier=Tier.TODAY,
                    status=Status.FAIL,
                    weight=3,
                    summary=f"Homepage could not be fetched ({status}) — nothing else can be evaluated",
                    fix="Ensure the homepage returns HTTP 200 to non-browser user agents (check bot blocking/WAF rules)",
                )
            ]

        tree = HTMLParser(response.text)
        return [
            self._extractability(response.text),
            self._structured_data(tree),
            self._metadata(tree),
            self._landmarks(tree),
            self._forms(tree),
        ]

    def _extractability(self, html: str) -> Finding:
        stripped = HTMLParser(html)
        for node in stripped.css("script, style, noscript, template"):
            node.decompose()
        text = (stripped.body.text(separator=" ") if stripped.body else "").split()
        words = len(text)
        if words >= 100:
            return Finding(
                id="content-extractable",
                layer=self.layer,
                tier=Tier.TODAY,
                status=Status.PASS,
                weight=3,
                summary=f"Page text is server-rendered and extractable ({words} words without executing JavaScript)",
            )
        status = Status.WARN if words >= 20 else Status.FAIL
        return Finding(
            id="content-extractable",
            layer=self.layer,
            tier=Tier.TODAY,
            status=status,
            weight=3,
            summary=f"Only {words} words of text are visible without JavaScript — most agents see a near-empty page",
            fix="Server-render or pre-render key content (SSR/SSG) so text agents get real content in the initial HTML",
        )

    def _structured_data(self, tree: HTMLParser) -> Finding:
        types: list[str] = []
        for node in tree.css('script[type="application/ld+json"]'):
            try:
                data = json.loads(node.text())
            except (json.JSONDecodeError, TypeError):
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    for entry in item.get("@graph", [item]):
                        if isinstance(entry, dict) and entry.get("@type"):
                            declared = entry["@type"]
                            types.extend(declared if isinstance(declared, list) else [declared])
        if types:
            return Finding(
                id="structured-data",
                layer=self.layer,
                tier=Tier.TODAY,
                status=Status.PASS,
                weight=3,
                summary="schema.org JSON-LD present — agents get machine-readable facts, not just prose",
                evidence=", ".join(dict.fromkeys(types))[:200],
            )
        if tree.css_first("[itemscope]") is not None:
            return Finding(
                id="structured-data",
                layer=self.layer,
                tier=Tier.TODAY,
                status=Status.WARN,
                weight=3,
                summary="Only microdata markup found — JSON-LD is the format agents and search parse most reliably",
                fix="Add schema.org JSON-LD (Organization on the homepage; Product/Offer on product pages)",
            )
        return Finding(
            id="structured-data",
            layer=self.layer,
            tier=Tier.TODAY,
            status=Status.FAIL,
            weight=3,
            summary="No schema.org structured data found — agents must guess prices, availability, and identity from prose",
            fix="Add schema.org JSON-LD (Organization on the homepage; Product/Offer on product pages)",
        )

    def _metadata(self, tree: HTMLParser) -> Finding:
        title = tree.css_first("title")
        has_title = title is not None and bool(title.text(strip=True))
        description = tree.css_first('meta[name="description"]')
        has_description = description is not None and bool(
            (description.attributes.get("content") or "").strip()
        )
        if has_title and has_description:
            return Finding(
                id="page-metadata",
                layer=self.layer,
                tier=Tier.TODAY,
                status=Status.PASS,
                weight=1,
                summary="Title and meta description are present",
            )
        missing = [
            name
            for name, present in [("title", has_title), ("meta description", has_description)]
            if not present
        ]
        return Finding(
            id="page-metadata",
            layer=self.layer,
            tier=Tier.TODAY,
            status=Status.WARN if len(missing) == 1 else Status.FAIL,
            weight=1,
            summary=f"Missing {' and '.join(missing)} — the first thing any agent reads about a page",
            fix="Add a descriptive <title> and <meta name=\"description\"> to every page",
        )

    def _landmarks(self, tree: HTMLParser) -> Finding:
        has_main = tree.css_first("main, [role=main]") is not None
        has_h1 = tree.css_first("h1") is not None
        if has_main and has_h1:
            return Finding(
                id="semantic-landmarks",
                layer=self.layer,
                tier=Tier.TODAY,
                status=Status.PASS,
                weight=1,
                summary="Semantic landmarks (<main>, <h1>) let agents locate the primary content",
            )
        return Finding(
            id="semantic-landmarks",
            layer=self.layer,
            tier=Tier.TODAY,
            status=Status.WARN if (has_main or has_h1) else Status.FAIL,
            weight=1,
            summary="Weak semantic structure — agents fall back to heuristics to find the main content",
            fix="Wrap primary content in <main> and give each page exactly one <h1>",
        )

    def _forms(self, tree: HTMLParser) -> Finding:
        labeled_ids = {
            node.attributes.get("for")
            for node in tree.css("label[for]")
            if node.attributes.get("for")
        }
        fields = tree.css(
            "form input:not([type=hidden]):not([type=submit]), form select, form textarea"
        )
        if not fields:
            return Finding(
                id="forms-operable",
                layer=self.layer,
                tier=Tier.TODAY,
                status=Status.INFO,
                weight=0,
                summary="No forms on the homepage — form operability not evaluated on this page",
            )
        unlabeled = [
            field
            for field in fields
            if not (
                field.attributes.get("aria-label")
                or field.attributes.get("aria-labelledby")
                or field.attributes.get("placeholder")
                or field.attributes.get("id") in labeled_ids
                or field.attributes.get("name")
            )
        ]
        if not unlabeled:
            return Finding(
                id="forms-operable",
                layer=self.layer,
                tier=Tier.TODAY,
                status=Status.PASS,
                weight=2,
                summary=f"All {len(fields)} form field(s) are labeled — an agent can fill them reliably",
            )
        return Finding(
            id="forms-operable",
            layer=self.layer,
            tier=Tier.TODAY,
            status=Status.WARN if len(unlabeled) < len(fields) else Status.FAIL,
            weight=2,
            summary=f"{len(unlabeled)} of {len(fields)} form field(s) have no label, name, or aria-label — agents must guess what goes where",
            fix="Give every form field a <label for>, name, or aria-label",
        )
