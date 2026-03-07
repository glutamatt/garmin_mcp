"""
Modular MCP Server for Garmin Connect Data

Stateless architecture: tokens passed per-request via _meta.context.sport_platform_token
Login via garmin_login tool → tokens returned in response → stored in JWT by frontend

3-layer architecture:
  SDK (garminconnect fork) → API (garmin_mcp.api.*) → Tools (garmin_mcp.*.py)

CLI endpoint:
  POST /cli — bash-style CLI for AI agents (fewer tokens, filesystem clipboard)
"""


def main():
    """Initialize and run the MCP server."""
    from garmin_mcp.server import create_app
    app = create_app()
    app.run()


if __name__ == "__main__":
    main()
