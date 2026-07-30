import json

from typer.testing import CliRunner

from beacon import history
from beacon.cli import app

runner = CliRunner()


def run_payload(score_today, findings):
    return {
        "domain": "shop.example",
        "audited_at": "2026-07-13T12:00:00+00:00",
        "score_today": score_today,
        "score_future": 10,
        "findings": findings,
    }


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    history.save_run("shop.example", run_payload(50, []))
    history.save_run("shop.example", run_payload(70, []))
    runs = history.load_runs("shop.example", limit=2)
    assert [run["score_today"] for run in runs] == [50, 70]  # oldest first
    assert history.load_runs("unknown.example") == []


def test_diff_reports_score_and_status_changes():
    old = run_payload(
        50,
        [
            {"id": "sitemap-available", "status": "fail", "summary": "No sitemap"},
            {"id": "robots-txt-present", "status": "pass", "summary": "robots ok"},
            {"id": "legacy-check", "status": "warn", "summary": "gone"},
        ],
    )
    new = run_payload(
        70,
        [
            {"id": "sitemap-available", "status": "pass", "summary": "Sitemap declared"},
            {"id": "robots-txt-present", "status": "pass", "summary": "robots ok"},
            {"id": "product-markup", "status": "warn", "summary": "new check"},
        ],
    )
    text = history.diff_runs(old, new)
    assert "50 → 70  (+20)" in text
    assert "sitemap-available: FAIL → PASS" in text
    assert "+ product-markup [warn]" in text
    assert "- legacy-check [was warn]" in text
    assert "robots-txt-present" not in text.replace("- legacy", "")  # unchanged is silent


def test_change_summary_flags_changes():
    old = run_payload(50, [{"id": "a", "status": "fail", "summary": "s"}])
    new = run_payload(70, [{"id": "a", "status": "pass", "summary": "s"}])
    summary = history.change_summary(old, new)
    assert summary["has_changes"] is True
    assert summary["score_today"] == {"old": 50, "new": 70}
    assert summary["changed"] == [{"id": "a", "before": "fail", "after": "pass", "summary": "s"}]

    same = run_payload(50, [{"id": "a", "status": "pass", "summary": "s"}])
    assert history.change_summary(same, same)["has_changes"] is False


def test_diff_no_changes():
    payload = run_payload(50, [{"id": "a", "status": "pass", "summary": "s"}])
    assert "No finding changes" in history.diff_runs(payload, payload)


def seed(monkeypatch, tmp_path, runs=3):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    for score_today in range(50, 50 + runs * 10, 10):
        history.save_run("shop.example", run_payload(score_today, []))


def test_history_lists_domains(tmp_path, monkeypatch):
    seed(monkeypatch, tmp_path)
    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "shop.example" in result.output
    assert "3" in result.output
    assert "70" in result.output


def test_history_lists_runs_for_domain(tmp_path, monkeypatch):
    seed(monkeypatch, tmp_path)
    result = runner.invoke(app, ["history", "shop.example"])
    assert result.exit_code == 0
    assert "Audit history — shop.example (3 run(s))" in result.output
    assert "2026-07-13T12:00:00+00:00" in result.output


def test_history_export_and_prune(tmp_path, monkeypatch):
    seed(monkeypatch, tmp_path)
    out = tmp_path / "runs.json"
    result = runner.invoke(app, ["history", "shop.example", "--export", str(out)])
    assert result.exit_code == 0
    exported = json.loads(out.read_text(encoding="utf-8"))
    assert [run["score_today"] for run in exported] == [50, 60, 70]

    result = runner.invoke(app, ["history", "shop.example", "--prune", "1"])
    assert result.exit_code == 0
    assert "Pruned 2 run(s), kept 1" in result.output
    assert [run["score_today"] for run in history.load_runs("shop.example", limit=5)] == [70]


def test_history_unknown_domain_exits_2(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    assert runner.invoke(app, ["history", "never.example"]).exit_code == 2


def test_history_prune_requires_domain(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    assert runner.invoke(app, ["history", "--prune", "1"]).exit_code != 0
