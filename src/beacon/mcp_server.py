"""Minimal MCP (Model Context Protocol) server over stdio - zero dependencies.

Lets any MCP host (Claude Desktop, Cursor, ...) ask Beacon about a domain
without shelling out: `score_site`, `audit_site`, and `site_trend`. Speaks
newline-delimited JSON-RPC 2.0, the wire format of the official SDKs.

Run:  beacon-mcp   (or python -m beacon.mcp_server)
"""

from __future__ import annotations

import json
import sys
from typing import Any

import httpx

from beacon import history
from beacon.checks.base import Layer
from beacon.fetch import normalize_base_url
from beacon.scoring import score

SERVER_INFO = {"name": "beacon", "version": "0.1.0"}

_LAYERS = [layer.value for layer in Layer]

TOOL_SCHEMAS = {
    "score_site": {
        "description": "Audit a domain and return its agent-visibility score (x/100).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain or URL, e.g. example.com"}
            },
            "required": ["domain"],
        },
    },
    "audit_site": {
        "description": "Full agent-readiness audit as readable text (or JSON with detailed=true).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "detailed": {"type": "boolean", "description": "Return the raw JSON payload"},
            },
            "required": ["domain"],
        },
    },
    "site_trend": {
        "description": "Recent recorded scores for a domain, oldest first.",
        "inputSchema": {
            "type": "object",
            "properties": {"domain": {"type": "string"}},
            "required": ["domain"],
        },
    },
}


def _tool_names() -> list[str]:
    return list(TOOL_SCHEMAS)


def _run_score(domain: str) -> str:
    from beacon.cli import run_audit

    site, findings = _loop_run(lambda: run_audit(domain))
    card = score(findings)
    percent = card.today.percent
    return f"{percent}/100" if percent is not None else "n/a"


def _run_audit_text(domain: str, detailed: bool) -> str:
    from beacon import report
    from beacon.cli import run_audit

    def work():
        return run_audit(domain)

    site, findings = _loop_run(work)
    card = score(findings)
    payload = report.payload(site.domain, findings, card)
    if detailed:
        return json.dumps(payload, indent=2, ensure_ascii=False)
    return report.render_text(site.domain, findings, card)


def _run_trend(domain: str) -> str:
    key = httpx.URL(normalize_base_url(domain)).host
    runs = history.load_runs(key, limit=20)
    if not runs:
        return f"No recorded audits for {key} - run a local `beacon audit {key}` first."
    scores = [str(run.get("score_today")) for run in runs]
    line = history.sparkline([run.get("score_today") for run in runs])
    return f"{key}: {' '.join(scores)}" + (f"\n{line}" if line else "")


class _LoopRunner:
    """One persistent event loop so repeated tool calls stay cheap."""

    def __init__(self) -> None:
        self._loop = None

    def run(self, factory):
        import asyncio

        if self._loop is None:
            self._loop = asyncio.new_event_loop()
        return self._loop.run_until_complete(factory())


_runner = _LoopRunner()


def _loop_run(factory):
    return _runner.run(factory)


def _dispatch_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "score_site":
        return _run_score(str(arguments["domain"]))
    if name == "audit_site":
        return _run_audit_text(
            str(arguments["domain"]), bool(arguments.get("detailed", False))
        )
    if name == "site_trend":
        return _run_trend(str(arguments["domain"]))
    raise KeyError(name)


def handle(request: dict[str, Any]) -> dict[str, Any] | None:
    """One request in, one response out (None for notifications)."""
    method = request.get("method", "")
    request_id = request.get("id")
    if method.startswith("notifications/"):
        return None
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {
                "tools": [
                    {"name": name, **schema} for name, schema in TOOL_SCHEMAS.items()
                ]
            }
        elif method == "tools/call":
            params = request.get("params") or {}
            name = str(params.get("name"))
            arguments = params.get("arguments") or {}
            try:
                text = _dispatch_tool(name, arguments)
            except KeyError:
                return _error(request_id, -32602, f"unknown tool: {name}")
            except PermissionError as exc:
                return _tool_error(str(exc))
            except Exception as exc:  # noqa: BLE001 - surfaced to the host, not raised
                return _tool_error(f"{type(exc).__name__}: {exc}")
            result = {"content": [{"type": "text", "text": text}]}
        else:
            return _error(request_id, -32601, f"method not found: {method}")
    except KeyError as exc:
        return _error(request_id, -32602, f"missing parameter: {exc}")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_error(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": f"ERROR: {message}"}],
        "isError": True,
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            response = _error(None, -32700, "parse error")
        else:
            response = handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
