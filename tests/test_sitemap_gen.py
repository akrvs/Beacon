import respx
from typer.testing import CliRunner

from beacon.cli import app

runner = CliRunner()

BASE = "https://shop.example"


@respx.mock
def test_generate_sitemap_from_homepage_links():
    html = (
        '<a href="/products">P</a><a href="/about">A</a>'
        '<a href="https://other.example/x">X</a><a href="/products">dup</a>'
    )
    respx.get(f"{BASE}/robots.txt").respond(404)
    respx.get(BASE).respond(200, html=html)
    respx.get(url__startswith=BASE).respond(404)
    result = runner.invoke(app, ["generate", "sitemap", "shop.example"])
    assert result.exit_code == 0
    assert result.output.count("<loc>") == 3
    assert "<loc>https://shop.example/</loc>" in result.output
    assert "<loc>https://shop.example/products</loc>" in result.output
    assert "other.example" not in result.output


@respx.mock
def test_generate_sitemap_unreachable_homepage_still_lists_root():
    respx.get(url__startswith=BASE).respond(404)
    result = runner.invoke(app, ["generate", "sitemap", "shop.example"])
    assert result.exit_code == 0
    assert result.output.count("<loc>") == 1
