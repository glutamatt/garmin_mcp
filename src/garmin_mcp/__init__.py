"""
Modular MCP Server for Garmin Connect Data

Session-based authentication using FastMCP Context:
- Use garmin_login_tool() or set_garmin_session() to authenticate
- Tokens stored in MCP session context (isolated per mcp-session-id header)
- All data tools automatically use session tokens via Context

Supports two transport modes:
- stdio: For single-user local usage (default)
- http: For multi-user HTTP server deployment
"""

import os

from fastmcp import FastMCP

# Import all modules
from garmin_mcp import auth_tool
from garmin_mcp import activity_management
from garmin_mcp import health_wellness
from garmin_mcp import user_profile
from garmin_mcp import devices
from garmin_mcp import gear_management
from garmin_mcp import weight_management
from garmin_mcp import challenges
from garmin_mcp import training
from garmin_mcp import workouts
from garmin_mcp import data_management
from garmin_mcp import womens_health
from garmin_mcp import training_load


def create_app() -> FastMCP:
    """Create and configure the MCP app with all tools registered."""
    # Create the MCP app
    app = FastMCP("Garmin Connect v2.0")

    # Register authentication tools (login, set_session, logout, get_user_name, get_available_features)
    app = auth_tool.register_tools(app)

    # Register data tools from all modules
    app = activity_management.register_tools(app)
    app = health_wellness.register_tools(app)
    app = user_profile.register_tools(app)
    app = devices.register_tools(app)
    app = gear_management.register_tools(app)
    app = weight_management.register_tools(app)
    app = challenges.register_tools(app)
    app = training.register_tools(app)
    app = workouts.register_tools(app)
    app = data_management.register_tools(app)
    app = womens_health.register_tools(app)
    app = training_load.register_tools(app)

    return app


def main():
    """Initialize the MCP server and run with configured transport.

    Environment variables:
    - MCP_TRANSPORT: 'stdio' (default) or 'http'
    - MCP_HOST: Host to bind to (default: '0.0.0.0')
    - MCP_PORT: Port for HTTP transport (default: 8080)
    """
    app = create_app()

    transport = os.environ.get("MCP_TRANSPORT", "stdio")

    if transport == "http":
        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8080"))
        app.run(transport="http", host=host, port=port)
    else:
        # Default to stdio for backward compatibility
        app.run()


if __name__ == "__main__":
    main()
