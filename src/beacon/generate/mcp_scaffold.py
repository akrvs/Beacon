"""Generate a runnable MCP server scaffold from an OpenAPI (JSON) spec.

Emits one MCP tool per operation, forwarding to the business's existing API.
Auth is wired from the spec's `securitySchemes` (apiKey, HTTP bearer/basic,
OAuth2 access tokens) as environment variables. The output is a reviewable
starting point, not a finished product: rate limits, token refresh, and which
operations to expose are decisions the owner must make.
"""

from __future__ import annotations

import json
import keyword
import re
from dataclasses import dataclass

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

    auth = _build_auth(spec)
    server_py = _SERVER_TEMPLATE.format(
        name=name,
        base_url=_lit(base_url),
        tool_count=len(tools),
        tools="\n\n".join(tools),
        extra_imports=auth.imports,
        env_block=auth.env_block,
        auth_body=auth.body,
    )
    return {
        "server.py": server_py,
        "pyproject.toml": _PYPROJECT_TEMPLATE.format(name=name),
        "README.md": _README_TEMPLATE.format(
            name=name,
            title=info.get("title", name),
            tool_count=len(tools),
            auth_section=auth.readme,
            env_exports=" ".join(f"{var}=..." for var in auth.env_vars),
            env_json=", ".join(f'"{var}": "..."' for var in auth.env_vars),
        ),
    }


@dataclass
class _Auth:
    imports: str
    env_block: str
    body: str
    readme: str
    env_vars: list[str]


def _referenced_schemes(spec: dict) -> dict[str, dict]:
    """Security schemes referenced by the spec (all defined ones if none are referenced)."""
    defined = {
        scheme_name: scheme
        for scheme_name, scheme in (
            ((spec.get("components") or {}).get("securitySchemes") or {}).items()
        )
        if isinstance(scheme, dict)
    }
    referenced: set[str] = set()
    security_blocks = list(spec.get("security") or [])
    for path_item in (spec.get("paths") or {}).values():
        if not isinstance(path_item, dict):
            continue
        for method in _METHODS:
            operation = path_item.get(method)
            if isinstance(operation, dict):
                security_blocks += list(operation.get("security") or [])
    for requirement in security_blocks:
        if isinstance(requirement, dict):
            referenced.update(requirement)
    picked = {name: scheme for name, scheme in defined.items() if name in referenced}
    return picked or defined


def _build_auth(spec: dict) -> _Auth:
    schemes = _referenced_schemes(spec)
    if not schemes:
        return _Auth(
            imports="",
            env_block=(
                'API_KEY = os.environ.get("API_KEY", "")'
                "  # spec declares no securitySchemes; generic bearer stub"
            ),
            body=(
                '    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}\n'
                "    return headers, {}"
            ),
            readme=(
                "The spec declares no `securitySchemes`, so the scaffold ships a generic\n"
                "`API_KEY` bearer stub — replace `_auth()` with your real auth."
            ),
            env_vars=["API_KEY"],
        )

    env_lines: list[str] = []
    body: list[str] = []
    readme_rows: list[str] = []
    env_vars: list[str] = []
    needs_base64 = False
    used_env: set[str] = set()

    def declare(var: str, comment: str) -> str:
        var = _unique(var, used_env)
        env_lines.append(f'{var} = os.environ.get("{var}", "")  # {_comment(comment)}')
        env_vars.append(var)
        return var

    for scheme_name, scheme in schemes.items():
        base = _slug(scheme_name).upper() or "AUTH"
        scheme_type = (scheme.get("type") or "").lower()
        if scheme_type == "apikey":
            param = scheme.get("name") or "X-API-Key"
            location = scheme.get("in") or "header"
            var = declare(base, f"{scheme_name}: apiKey in {location} '{param}'")
            body.append(f"    if {var}:")
            if location == "query":
                body.append(f"        params[{_lit(param)}] = {var}")
            elif location == "cookie":
                body.append(f'        headers["Cookie"] = {_lit(param + "=")} + {var}')
            else:
                body.append(f"        headers[{_lit(param)}] = {var}")
            readme_rows.append(f"- `{var}` — API key sent as {location} `{param}` ({scheme_name}).")
        elif scheme_type == "http" and (scheme.get("scheme") or "").lower() == "basic":
            user_var = declare(f"{base}_USERNAME", f"{scheme_name}: HTTP basic")
            pass_var = declare(f"{base}_PASSWORD", f"{scheme_name}: HTTP basic")
            body += [
                f"    if {user_var}:",
                f'        credentials = base64.b64encode(f"{{{user_var}}}:{{{pass_var}}}".encode()).decode()',
                '        headers["Authorization"] = f"Basic {credentials}"',
            ]
            needs_base64 = True
            readme_rows.append(
                f"- `{user_var}` / `{pass_var}` — HTTP basic credentials ({scheme_name})."
            )
        elif scheme_type == "http":
            http_scheme = scheme.get("scheme") or "bearer"
            prefix = "Bearer" if http_scheme.lower() == "bearer" else http_scheme
            var = declare(f"{base}_TOKEN", f"{scheme_name}: HTTP {http_scheme}")
            body += [
                f"    if {var}:",
                f'        headers["Authorization"] = f"{_fstr(prefix)} {{{var}}}"',
            ]
            readme_rows.append(f"- `{var}` — HTTP {http_scheme} token ({scheme_name}).")
        elif scheme_type in ("oauth2", "openidconnect"):
            var = declare(f"{base}_TOKEN", f"{scheme_name}: {scheme_type} access token")
            body += [
                f"    if {var}:",
                f'        headers["Authorization"] = f"Bearer {{{var}}}"',
            ]
            readme_rows.append(
                f"- `{var}` — OAuth access token ({scheme_name}); obtaining and refreshing "
                "it is outside this server, which only sends it as a bearer token."
            )
        else:
            body.append(
                f"    # TODO: security scheme '{_comment(scheme_name)}' "
                f"(type {_comment(scheme_type) or 'unknown'}) needs manual wiring"
            )
            readme_rows.append(
                f"- `{scheme_name}` (type `{scheme_type or 'unknown'}`) is not auto-wired — "
                "add it to `_auth()` yourself."
            )

    body.append("    return headers, params")
    return _Auth(
        imports="import base64\n" if needs_base64 else "",
        env_block="\n".join(env_lines),
        body="\n".join(
            ["    headers: dict[str, str] = {}", "    params: dict[str, str] = {}", *body]
        ),
        readme=(
            "Auth is wired from the spec's `securitySchemes`. Set the variable(s) for\n"
            "the scheme your API actually uses:\n\n" + "\n".join(readme_rows)
        ),
        env_vars=env_vars,
    )


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
    used_args = {"body"}
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
                "arg": _unique(_slug(raw_name) or "arg", used_args),
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
    docstring = "\n    ".join(_doc("\n".join(doc_lines)).splitlines())

    path_args = {p["name"]: p["arg"] for p in params if p["in"] == "path"}
    pieces: list[str] = []
    interpolated = False
    for index, segment in enumerate(re.split(r"\{([^{}]*)\}", path)):
        if index % 2 and segment in path_args:
            pieces.append("{" + path_args[segment] + "}")
            interpolated = True
        elif index % 2:
            pieces.append("{{" + _fstr(segment) + "}}")
        else:
            pieces.append(_fstr(segment))
    literal = "".join(pieces)
    if interpolated:
        path_expr = f'f"{literal}"'
    else:
        path_expr = f'"{literal.replace("{{", "{").replace("}}", "}")}"'

    query_items = ", ".join(
        f'{_lit(p["name"])}: {p["arg"]}' for p in params if p["in"] == "query"
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
    if keyword.iskeyword(text):
        text = f"{text}_"
    return text


def _lit(text: str) -> str:
    """A safe double-quoted Python string literal for spec-derived text."""
    return json.dumps(text)


def _fstr(text: str) -> str:
    """Spec-derived text escaped for embedding inside a generated f-string."""
    return _lit(text)[1:-1].replace("{", "{{").replace("}", "}}")


def _comment(text: str) -> str:
    return " ".join(text.split())


def _doc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


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
deploying: remove tools you don't want agents to call, and check that
`_auth()` matches how your API actually issues credentials.
"""

{extra_imports}import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("{name}")

API_BASE_URL = os.environ.get("API_BASE_URL", {base_url})
{env_block}


def _auth() -> tuple[dict, dict]:
    """Auth headers and query params from the spec's security schemes."""
{auth_body}


async def _request(method: str, path: str, params: dict | None = None, json_body: dict | None = None) -> str:
    headers, auth_params = _auth()
    params = {{key: value for key, value in (params or {{}}).items() if value is not None}}
    params.update(auth_params)
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
API_BASE_URL=https://your-api.example {env_exports} uv run python server.py
```

## Auth

{auth_section}

## Connect from Claude (or any MCP client)

```json
{{
  "mcpServers": {{
    "{name}": {{
      "command": "uv",
      "args": ["run", "--directory", "/path/to/this/dir", "python", "server.py"],
      "env": {{"API_BASE_URL": "https://your-api.example", {env_json}}}
    }}
  }}
}}
```

## Before you ship it

- Delete tools you don't want agents to call (especially writes).
- Check `_auth()` — the env-var wiring covers the spec's schemes, but token
  refresh and OAuth flows are yours to implement.
- Add input validation for anything destructive.
"""
