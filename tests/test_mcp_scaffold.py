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
