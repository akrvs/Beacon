"""Persist audit runs per domain and diff consecutive runs.

Runs live under $BEACON_HOME/history/<domain>/<utc timestamp>.json
(default BEACON_HOME: $XDG_DATA_HOME/beacon or ~/.local/share/beacon).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from beacon.config import beacon_home


def history_dir() -> Path:
    return beacon_home() / "history"


def save_run(domain: str, payload: dict) -> Path:
    directory = history_dir() / domain
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = directory / f"{stamp}.json"
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def load_runs(domain: str, limit: int = 2) -> list[dict]:
    """Most recent runs for a domain, oldest first."""
    files = run_files(domain)[-limit:]
    return [json.loads(path.read_text(encoding="utf-8")) for path in files]


def run_files(domain: str) -> list[Path]:
    directory = history_dir() / domain
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def recorded_domains() -> list[str]:
    root = history_dir()
    if not root.is_dir():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def prune(domain: str, keep: int) -> int:
    files = run_files(domain)
    stale = files[: len(files) - keep] if keep else files
    for path in stale:
        path.unlink()
    return len(stale)


def change_summary(old: dict, new: dict) -> dict:
    """Machine-readable changes between two runs (drives diff_runs and watch mode)."""
    old_findings = {f["id"]: f for f in old.get("findings", [])}
    new_findings = {f["id"]: f for f in new.get("findings", [])}
    changed = [
        {
            "id": fid,
            "before": old_findings[fid]["status"],
            "after": finding["status"],
            "summary": finding["summary"],
        }
        for fid, finding in new_findings.items()
        if fid in old_findings and old_findings[fid]["status"] != finding["status"]
    ]
    added = [f for fid, f in new_findings.items() if fid not in old_findings]
    removed = [f for fid, f in old_findings.items() if fid not in new_findings]
    return {
        "domain": new.get("domain"),
        "from": old.get("audited_at"),
        "to": new.get("audited_at"),
        "score_today": {"old": old.get("score_today"), "new": new.get("score_today")},
        "score_future": {"old": old.get("score_future"), "new": new.get("score_future")},
        "changed": changed,
        "added": added,
        "removed": removed,
        "has_changes": bool(changed or added or removed)
        or old.get("score_today") != new.get("score_today")
        or old.get("score_future") != new.get("score_future"),
    }


def diff_runs(old: dict, new: dict) -> str:
    summary = change_summary(old, new)
    lines = [
        f"Beacon diff — {summary['domain'] or '?'}",
        f"{summary['from'] or '?'}  →  {summary['to'] or '?'}",
        "",
        _score_line(
            "Agent visibility today", summary["score_today"]["old"], summary["score_today"]["new"]
        ),
        _score_line(
            "Future readiness      ", summary["score_future"]["old"], summary["score_future"]["new"]
        ),
    ]
    if summary["changed"]:
        lines.append("")
        lines.append("Changed:")
        for change in summary["changed"]:
            lines.append(
                f"  {change['id']}: {change['before'].upper()} → {change['after'].upper()}"
                f"  {change['summary']}"
            )
    if summary["added"]:
        lines.append("")
        lines.append("New checks:")
        lines += [f"  + {f['id']} [{f['status']}]" for f in summary["added"]]
    if summary["removed"]:
        lines.append("")
        lines.append("Removed checks:")
        lines += [f"  - {f['id']} [was {f['status']}]" for f in summary["removed"]]
    if not (summary["changed"] or summary["added"] or summary["removed"]):
        lines += ["", "No finding changes between runs."]
    return "\n".join(lines)


def _score_line(label: str, old: int | None, new: int | None) -> str:
    if old == new:
        return f"{label} : {_fmt(new)} (no change)"
    delta = ""
    if isinstance(old, int) and isinstance(new, int):
        delta = f"  ({new - old:+d})"
    return f"{label} : {_fmt(old)} → {_fmt(new)}{delta}"


def _fmt(value: int | None) -> str:
    return str(value) if value is not None else "n/a"
