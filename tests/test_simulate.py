import httpx
import respx

from beacon.fetch import Fetcher, Site
from beacon.simulate import (
    SimulationReport,
    TaskResult,
    build_prompt,
    gather_agent_view,
    render_simulation,
    run_simulation,
)

BASE = "https://shop.example"

HOMEPAGE = (
    "<html><head><title>Acme</title><script>var x=1;</script></head>"
    "<body><main><h1>Acme Widgets</h1><p>We sell widgets worldwide.</p>"
    '<a href="/products/widget">Widget</a></main></body></html>'
)
PRODUCT = (
    "<html><body><main><h1>Widget</h1><p>Price: $19.99 — In stock.</p>"
    "<button>Add to cart</button></main></body></html>"
)


def make_site() -> Site:
    client = httpx.AsyncClient(follow_redirects=True)
    return Site(BASE, fetcher=Fetcher(BASE, client=client))


@respx.mock
async def test_gather_agent_view_strips_scripts_and_finds_product_page():
    respx.get(f"{BASE}/robots.txt").respond(404)
    respx.get(f"{BASE}/sitemap.xml").respond(404)
    respx.get(f"{BASE}/products/widget").respond(200, text=PRODUCT)
    respx.get(BASE).respond(200, text=HOMEPAGE)

    site = make_site()
    pages = await gather_agent_view(site)
    await site.aclose()

    assert set(pages) == {BASE, f"{BASE}/products/widget"}
    assert "We sell widgets worldwide." in pages[BASE]
    assert "var x=1" not in pages[BASE]  # scripts are not agent-visible
    assert "$19.99" in pages[f"{BASE}/products/widget"]


def test_prompt_contains_pages_and_tasks():
    prompt = build_prompt("shop.example", {"https://shop.example": "We sell widgets."})
    assert "shop.example" in prompt
    assert "We sell widgets." in prompt
    assert "exact price and availability" in prompt
    assert "extraction_score" in prompt


class FakeParsed:
    def __init__(self, report):
        self.parsed_output = report


class FakeClient:
    def __init__(self, report):
        self.report = report
        self.calls = []

        class Messages:
            def __init__(self, outer):
                self.outer = outer

            def parse(self, **kwargs):
                self.outer.calls.append(kwargs)
                return FakeParsed(self.outer.report)

        self.messages = Messages(self)


def make_report() -> SimulationReport:
    return SimulationReport(
        business_summary="Sells widgets worldwide",
        tasks=[
            TaskResult(task="Identify the business", answer="Widget shop", status="answered"),
            TaskResult(task="Find a price", answer="Not visible", status="unanswerable"),
        ],
        extraction_score=55,
        missing_information=["Product prices in server-rendered HTML"],
    )


def test_run_simulation_calls_claude_with_structured_output():
    client = FakeClient(make_report())
    report = run_simulation("shop.example", {"u": "text"}, client, "claude-opus-4-8")
    assert report.extraction_score == 55
    (call,) = client.calls
    assert call["model"] == "claude-opus-4-8"
    assert call["output_format"] is SimulationReport
    assert call["thinking"] == {"type": "adaptive"}


def test_render_simulation_readable():
    text = render_simulation("shop.example", {"u": "t"}, make_report())
    assert "55/100" in text
    assert "✓ [answered]" in text and "✗ [unanswerable]" in text
    assert "Product prices in server-rendered HTML" in text
