"""
Modular MCP Server for Garmin Connect Data

Stateless architecture: tokens passed per-request via _meta.context.sport_platform_token
Login via garmin_login tool → tokens returned in response → stored in JWT by frontend

3-layer architecture:
  SDK (garminconnect fork) → API (garmin_mcp.api.*) → CLI (garmin_mcp.cli)

CLI endpoint:
  POST /cli — bash-style CLI for AI agents (fewer tokens, filesystem clipboard)

MCP tools (login only): garmin_login / garmin_logout (auth_tool.py),
get_device_capabilities (capabilities_tool.py).
"""


def main():
    """Initialize and run the MCP server."""
    from garmin_mcp.server import create_app
    app = create_app()
    app.run()


if __name__ == "__main__":
    main()
