"""The stdio MCP server speaks JSON-RPC and exposes the audit tools."""

import json

from beacon import history
from beacon.mcp_server import handle, main


def _request(method, params=None, id=1):
    return {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}


def test_initialize_and_tools_list():
    init = handle(_request("initialize", {}))
    assert init["result"]["serverInfo"]["name"] == "beacon"
    assert "tools" in init["result"]["capabilities"]

    listing = handle(_request("tools/list", {}))
    names = {tool["name"] for tool in listing["result"]["tools"]}
    assert names == {"score_site", "audit_site", "site_trend"}
    for tool in listing["result"]["tools"]:
        assert tool["inputSchema"]["type"] == "object"


def test_notifications_get_no_response():
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_and_tool_errors():
    bad_method = handle(_request("resources/list", {}, id=7))
    assert bad_method["error"]["code"] == -32601

    bad_tool = handle(
        _request("tools/call", {"name": "nope", "arguments": {}}, id=8)
    )
    assert bad_tool["error"]["code"] == -32602


def test_missing_required_argument_is_reported():
    response = handle(_request("tools/call", {"name": "score_site", "arguments": {}}, id=9))
    assert response["error"]["code"] == -32602


def test_trend_tool_reads_local_history(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    history.save_run("shop.example", {"domain": "shop.example", "score_today": 40})
    history.save_run("shop.example", {"domain": "shop.example", "score_today": 60})

    response = handle(
        _request("tools/call", {"name": "site_trend", "arguments": {"domain": "shop.example"}})
    )
    text = response["result"]["content"][0]["text"]
    assert "40" in text and "60" in text


def test_trend_without_history_is_a_clean_tool_error(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_HOME", str(tmp_path))
    response = handle(
        _request("tools/call", {"name": "site_trend", "arguments": {"domain": "none.example"}})
    )
    assert "isError" not in response["result"]
    assert "No recorded audits" in response["result"]["content"][0]["text"]


def test_main_loop_parses_lines_and_skips_notifications(monkeypatch, capsys):
    lines = [
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        "not json at all",
        json.dumps(_request("initialize", {})),
        "",
    ]
    monkeypatch.setattr("sys.stdin", iter(lines))
    main()
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 2
    parse_error = json.loads(out[0])
    assert parse_error["error"]["code"] == -32700
    saved = json.loads(out[1])
    assert saved["id"] == 1
    assert saved["result"]["serverInfo"]["name"] == "beacon"
