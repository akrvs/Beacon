import httpx
import respx

from agentready.checks.base import Status
from agentready.checks.content import ContentCheck
from agentready.fetch import Fetcher, Site

BASE = "https://shop.example"

GOOD_PAGE = """<!doctype html>
<html><head>
  <title>Acme Widgets</title>
  <meta name="description" content="Widgets shipped worldwide">
  <script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "Organization", "name": "Acme"}
  </script>
</head><body>
  <main><h1>Acme Widgets</h1>
    <p>""" + "quality widgets for every need " * 25 + """</p>
    <form action="/subscribe">
      <label for="email">Email</label><input id="email" type="email">
      <button type="submit">Subscribe</button>
    </form>
  </main>
</body></html>"""

JS_SHELL = """<!doctype html>
<html><head><title>App</title></head>
<body><div id="root"></div><script src="/bundle.js"></script></body></html>"""

UNLABELED_FORM = """<!doctype html>
<html><head><title>T</title><meta name="description" content="d"></head>
<body><main><h1>T</h1><p>""" + "words " * 150 + """</p>
<form><input type="text"><input type="text"></form></main></body></html>"""


def make_site() -> Site:
    client = httpx.AsyncClient(follow_redirects=True)
    return Site(BASE, fetcher=Fetcher(BASE, client=client))


async def run_on(html: str, status_code: int = 200):
    respx.get(BASE).respond(status_code, text=html, headers={"content-type": "text/html"})
    site = make_site()
    findings = await ContentCheck().run(site)
    await site.aclose()
    return {f.id: f for f in findings}


@respx.mock
async def test_good_page_passes_everything():
    findings = await run_on(GOOD_PAGE)
    assert findings["content-extractable"].status is Status.PASS
    assert findings["structured-data"].status is Status.PASS
    assert "Organization" in findings["structured-data"].evidence
    assert findings["page-metadata"].status is Status.PASS
    assert findings["semantic-landmarks"].status is Status.PASS
    assert findings["forms-operable"].status is Status.PASS


@respx.mock
async def test_js_shell_fails_extraction_and_structure():
    findings = await run_on(JS_SHELL)
    assert findings["content-extractable"].status is Status.FAIL
    assert findings["structured-data"].status is Status.FAIL
    assert findings["page-metadata"].status is Status.WARN
    assert findings["semantic-landmarks"].status is Status.FAIL
    assert findings["forms-operable"].status is Status.INFO


@respx.mock
async def test_unlabeled_form_fails():
    findings = await run_on(UNLABELED_FORM)
    assert findings["forms-operable"].status is Status.FAIL


@respx.mock
async def test_unreachable_homepage_is_single_fail():
    findings = await run_on("blocked", status_code=403)
    assert set(findings) == {"homepage-reachable"}
    assert findings["homepage-reachable"].status is Status.FAIL
