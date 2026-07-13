"""Generate a runnable MCP server scaffold from an OpenAPI (JSON) spec.

Emits one MCP tool per operation, forwarding to the business's existing API.
The output is a reviewable starting point, not a finished product: auth, rate
limits, and which operations to expose are decisions the owner must make.
"""

from __future__ import annotations

import json
import re

MAX_TOOLS = 40

_TYPE_MAP = {
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "string": "str",
    "array": "list",
    "object": "dict",
}

_METHODS = ("get", "post", "put", "patch", "delete")


def scaffold_mcp_server(spec: dict, server_name: str | None = None) -> dict[str, str]:
    """Return {filename: content} for the generated server project."""
    info = spec.get("info", {})
    name = server_name or _slug(info.get("title") or "api") or "api"
    base_url = (spec.get("servers") or [{}])[0].get("url", "https://api.example.com")

    tools: list[str] = []
    used_names: set[str] = set()
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        shared_params = path_item.get("parameters", [])
        for method in _METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            if len(tools) >= MAX_TOOLS:
                break
            tools.append(
                _render_tool(method, path, operation, shared_params, used_names)
            )

    server_py = _SERVER_TEMPLATE.format(
        name=name,
        base_url=base_url,
        tool_count=len(tools),
        tools="\n\n".join(tools),
    )
    return {
        "server.py": server_py,
        "pyproject.toml": _PYPROJECT_TEMPLATE.format(name=name),
        "README.md": _README_TEMPLATE.format(
            name=name, title=info.get("title", name), tool_count=len(tools)
        ),
    }


def _render_tool(
    method: str,
    path: str,
    operation: dict,
    shared_params: list,
    used_names: set[str],
) -> str:
    tool_name = _unique(
        _slug(operation.get("operationId") or f"{method}_{path}"), used_names
    )

    params = []
    seen = set()
    for param in list(shared_params) + list(operation.get("parameters", [])):
        if not isinstance(param, dict):
            continue
        location = param.get("in")
        raw_name = param.get("name", "")
        if location not in ("path", "query") or not raw_name or raw_name in seen:
            continue
        seen.add(raw_name)
        params.append(
            {
                "arg": _slug(raw_name) or "arg",
                "name": raw_name,
                "in": location,
                "required": location == "path" or bool(param.get("required")),
                "type": _TYPE_MAP.get((param.get("schema") or {}).get("type"), "str"),
                "description": (param.get("description") or "").strip(),
            }
        )

    has_body = isinstance(operation.get("requestBody"), dict)
    body_required = has_body and bool(operation["requestBody"].get("required"))

    signature_parts = [f"{p['arg']}: {p['type']}" for p in params if p["required"]]
    if body_required:
        signature_parts.append("body: dict")
    signature_parts += [
        f"{p['arg']}: {p['type']} | None = None" for p in params if not p["required"]
    ]
    if has_body and not body_required:
        signature_parts.append("body: dict | None = None")

    doc_lines = [
        operation.get("summary") or f"{method.upper()} {path}",
    ]
    description = (operation.get("description") or "").strip()
    if description and description != doc_lines[0]:
        doc_lines += ["", description]
    param_docs = [f"    {p['arg']}: {p['description']}" for p in params if p["description"]]
    if param_docs:
        doc_lines += ["", "Args:"] + param_docs
    docstring = "\n    ".join("\n".join(doc_lines).splitlines())

    fstring_path = path
    for p in params:
        if p["in"] == "path":
            fstring_path = fstring_path.replace("{" + p["name"] + "}", "{" + p["arg"] + "}")
    path_expr = f'f"{fstring_path}"' if "{" in fstring_path else f'"{fstring_path}"'

    query_items = ", ".join(
        f'"{p["name"]}": {p["arg"]}' for p in params if p["in"] == "query"
    )
    call_args = [f"path={path_expr}"]
    if query_items:
        call_args.append(f"params={{{query_items}}}")
    if has_body:
        call_args.append("json_body=body")

    signature = ", ".join(signature_parts)
    call = ",\n        ".join([f'method="{method.upper()}"'] + call_args)
    return (
        f"@mcp.tool()\n"
        f"async def {tool_name}({signature}) -> str:\n"
        f'    """{docstring}"""\n'
        f"    return await _request(\n        {call},\n    )"
    )


def _slug(text: str) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    if text and text[0].isdigit():
        text = f"op_{text}"
    return text


def _unique(name: str, used: set[str]) -> str:
    candidate = name or "op"
    counter = 2
    while candidate in used:
        candidate = f"{name}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate


_SERVER_TEMPLATE = '''"""MCP server for {name} — generated by Beacon from an OpenAPI spec.

{tool_count} tool(s) forwarding to the API at API_BASE_URL. Review before
deploying: remove tools you don't want agents to call, and wire in real auth.
"""

import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("{name}")

API_BASE_URL = os.environ.get("API_BASE_URL", "{base_url}")
API_KEY = os.environ.get("API_KEY", "")


async def _request(method: str, path: str, params: dict | None = None, json_body: dict | None = None) -> str:
    headers = {{"Authorization": f"Bearer {{API_KEY}}"}} if API_KEY else {{}}
    params = {{key: value for key, value in (params or {{}}).items() if value is not None}}
    async with httpx.AsyncClient(base_url=API_BASE_URL, headers=headers, timeout=30.0) as client:
        response = await client.request(method, path, params=params, json=json_body)
        response.raise_for_status()
        return response.text


{tools}


if __name__ == "__main__":
    mcp.run()
'''

_PYPROJECT_TEMPLATE = """[project]
name = "{name}-mcp-server"
version = "0.1.0"
description = "MCP server generated by Beacon"
requires-python = ">=3.11"
dependencies = ["mcp>=1.2", "httpx>=0.27"]
"""

_README_TEMPLATE = """# {title} — MCP server

Generated by [Beacon](https://github.com/akrvs/Beacon). {tool_count} tool(s)
wrapping your existing API so MCP-speaking agents can call it directly.

## Run

```bash
uv sync
API_BASE_URL=https://your-api.example API_KEY=... uv run python server.py
```

## Connect from Claude (or any MCP client)

```json
{{
  "mcpServers": {{
    "{name}": {{
      "command": "uv",
      "args": ["run", "--directory", "/path/to/this/dir", "python", "server.py"],
      "env": {{"API_BASE_URL": "https://your-api.example", "API_KEY": "..."}}
    }}
  }}
}}
```

## Before you ship it

- Delete tools you don't want agents to call (especially writes).
- Replace the bearer-token stub with your real auth.
- Add input validation for anything destructive.
"""
