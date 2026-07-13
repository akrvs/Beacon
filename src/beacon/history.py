"""Persist audit runs per domain and diff consecutive runs.

Runs live under $BEACON_HOME/history/<domain>/<utc timestamp>.json
(default BEACON_HOME: $XDG_DATA_HOME/beacon or ~/.local/share/beacon).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def history_dir() -> Path:
    root = os.environ.get("BEACON_HOME")
    if root is None:
        data_home = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        root = str(Path(data_home) / "beacon")
    return Path(root) / "history"


def save_run(domain: str, payload: dict) -> Path:
    directory = history_dir() / domain
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = directory / f"{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def load_runs(domain: str, limit: int = 2) -> list[dict]:
    """Most recent runs for a domain, oldest first."""
    directory = history_dir() / domain
    if not directory.is_dir():
        return []
    files = sorted(directory.glob("*.json"))[-limit:]
    return [json.loads(path.read_text()) for path in files]


def diff_runs(old: dict, new: dict) -> str:
    lines = [
        f"Beacon diff — {new.get('domain', '?')}",
        f"{old.get('audited_at', '?')}  →  {new.get('audited_at', '?')}",
        "",
        _score_line("Agent visibility today", old.get("score_today"), new.get("score_today")),
        _score_line("Future readiness      ", old.get("score_future"), new.get("score_future")),
    ]
    old_findings = {f["id"]: f for f in old.get("findings", [])}
    new_findings = {f["id"]: f for f in new.get("findings", [])}

    changed = [
        (fid, old_findings[fid]["status"], finding["status"], finding["summary"])
        for fid, finding in new_findings.items()
        if fid in old_findings and old_findings[fid]["status"] != finding["status"]
    ]
    added = [f for fid, f in new_findings.items() if fid not in old_findings]
    removed = [f for fid, f in old_findings.items() if fid not in new_findings]

    if changed:
        lines.append("")
        lines.append("Changed:")
        for fid, before, after, summary in changed:
            lines.append(f"  {fid}: {before.upper()} → {after.upper()}  {summary}")
    if added:
        lines.append("")
        lines.append("New checks:")
        lines += [f"  + {f['id']} [{f['status']}]" for f in added]
    if removed:
        lines.append("")
        lines.append("Removed checks:")
        lines += [f"  - {f['id']} [was {f['status']}]" for f in removed]
    if not (changed or added or removed):
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
