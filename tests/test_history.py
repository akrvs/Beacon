from beacon import history


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
