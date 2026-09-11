def main() -> None:
    print(
        "SyntHire: run `synthire-mock` to start the mock Workday tenant, "
        "and `synthire-mcp` to start the MCP server."
    )


def run_mock_tenant() -> None:
    import uvicorn

    from .config import MOCK_TENANT_HOST, MOCK_TENANT_PORT

    uvicorn.run("synthire.mock_tenant.app:app", host=MOCK_TENANT_HOST, port=MOCK_TENANT_PORT, reload=True)


def run_mcp_server() -> None:
    from .mcp_server.server import main as mcp_main

    mcp_main()
