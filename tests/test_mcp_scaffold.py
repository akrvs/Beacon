import ast

from beacon.generate.mcp_scaffold import scaffold_mcp_server

SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "Acme Shop API"},
    "servers": [{"url": "https://api.acme.example/v1"}],
    "paths": {
        "/products": {
            "get": {
                "operationId": "listProducts",
                "summary": "List products",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer"},
                        "description": "Max results",
                    },
                    {"name": "X-Trace", "in": "header", "schema": {"type": "string"}},
                ],
            },
            "post": {
                "summary": "Create a product",
                "requestBody": {"required": True, "content": {"application/json": {}}},
            },
        },
        "/products/{productId}": {
            "parameters": [
                {"name": "productId", "in": "path", "required": True, "schema": {"type": "string"}}
            ],
            "get": {"operationId": "getProduct", "summary": "Get one product"},
        },
    },
}


def test_scaffold_generates_valid_python_with_expected_tools():
    files = scaffold_mcp_server(SPEC)
    assert set(files) == {"server.py", "pyproject.toml", "README.md"}
    server = files["server.py"]

    tree = ast.parse(server)  # must be syntactically valid Python
    tool_names = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name != "_request"
    ]
    assert tool_names == ["list_products", "post_products", "get_product"]

    assert 'FastMCP("acme_shop_api")' in server
    assert 'os.environ.get("API_BASE_URL", "https://api.acme.example/v1")' in server
    assert "async def list_products(limit: int | None = None)" in server
    assert "async def post_products(body: dict)" in server
    assert 'f"/products/{product_id}"' in server
    assert "X-Trace" not in server  # header params are not exposed as tool args


def test_no_security_schemes_falls_back_to_generic_bearer_stub():
    files = scaffold_mcp_server(SPEC)
    assert 'API_KEY = os.environ.get("API_KEY", "")' in files["server.py"]
    assert "no `securitySchemes`" in files["README.md"]


AUTH_SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "Secure API"},
    "security": [{"ApiKeyAuth": []}],
    "components": {
        "securitySchemes": {
            "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
            "QueryKey": {"type": "apiKey", "in": "query", "name": "api_key"},
            "BearerAuth": {"type": "http", "scheme": "bearer"},
            "BasicAuth": {"type": "http", "scheme": "basic"},
            "OAuth": {"type": "oauth2", "flows": {}},
        }
    },
    "paths": {
        "/things": {
            "get": {
                "operationId": "listThings",
                "security": [{"QueryKey": []}, {"BearerAuth": []}, {"BasicAuth": []}, {"OAuth": []}],
            }
        }
    },
}


def test_security_schemes_are_wired_as_env_vars():
    files = scaffold_mcp_server(AUTH_SPEC)
    server = files["server.py"]
    ast.parse(server)

    assert 'API_KEY_AUTH = os.environ.get("API_KEY_AUTH", "")' in server
    assert 'headers["X-API-Key"] = API_KEY_AUTH' in server
    assert 'params["api_key"] = QUERY_KEY' in server
    assert 'headers["Authorization"] = f"Bearer {BEARER_AUTH_TOKEN}"' in server
    assert "import base64" in server  # basic auth needs it
    assert "BASIC_AUTH_USERNAME" in server and "BASIC_AUTH_PASSWORD" in server
    assert 'headers["Authorization"] = f"Bearer {OAUTH_TOKEN}"' in server
    assert "API_KEY = " not in server  # generic stub replaced by real schemes

    readme = files["README.md"]
    assert "API_KEY_AUTH" in readme and "BEARER_AUTH_TOKEN" in readme


def test_only_referenced_schemes_are_wired():
    spec = {
        "info": {"title": "t"},
        "security": [{"Used": []}],
        "components": {
            "securitySchemes": {
                "Used": {"type": "http", "scheme": "bearer"},
                "Unused": {"type": "apiKey", "in": "header", "name": "X-Ignored"},
            }
        },
        "paths": {"/a": {"get": {"operationId": "op"}}},
    }
    server = scaffold_mcp_server(spec)["server.py"]
    assert "USED_TOKEN" in server
    assert "X-Ignored" not in server


def test_unknown_scheme_type_becomes_todo():
    spec = {
        "info": {"title": "t"},
        "components": {"securitySchemes": {"Tls": {"type": "mutualTLS"}}},
        "paths": {"/a": {"get": {"operationId": "op"}}},
    }
    files = scaffold_mcp_server(spec)
    ast.parse(files["server.py"])
    assert "needs manual wiring" in files["server.py"]
    assert "not auto-wired" in files["README.md"]


def test_hostile_spec_values_cannot_inject_code():
    spec = {
        "info": {"title": "t"},
        "servers": [{"url": 'https://x.example"); evil()  # '}],
        "security": [{"Key": []}, {"Bearer": []}, {"Cookie": []}],
        "components": {
            "securitySchemes": {
                "Key": {"type": "apiKey", "in": "header", "name": 'X"] = evil()  # '},
                "Bearer": {"type": "http", "scheme": 'b" + evil()  # '},
                "Cookie": {"type": "apiKey", "in": "cookie", "name": 'c"=evil()  # \n'},
            }
        },
        "paths": {
            '/a"{b}': {
                "get": {
                    "operationId": "from",
                    "summary": 'end """\nevil()\nx = """',
                    "description": 'back\\slash and """ breakout',
                    "parameters": [
                        {
                            "name": 'q"key',
                            "in": "query",
                            "schema": {"type": "string"},
                            "description": 'desc """ breakout',
                        },
                        {"name": "import", "in": "query", "schema": {"type": "string"}},
                    ],
                }
            },
            "/b/{id}/c{stray}": {
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "get": {"operationId": "getB"},
            },
        },
    }
    server = scaffold_mcp_server(spec)["server.py"]
    tree = ast.parse(server)
    for node in ast.walk(tree):
        assert not (isinstance(node, ast.Name) and node.id == "evil")
    assert "async def from_(" in server
    assert "import_: str | None = None" in server
    assert 'f"/b/{id}/c{{stray}}"' in server


def test_duplicate_operation_ids_are_deduped():
    spec = {
        "info": {"title": "t"},
        "paths": {
            "/a": {"get": {"operationId": "op"}},
            "/b": {"get": {"operationId": "op"}},
        },
    }
    server = scaffold_mcp_server(spec)["server.py"]
    assert "async def op(" in server
    assert "async def op_2(" in server
    ast.parse(server)
