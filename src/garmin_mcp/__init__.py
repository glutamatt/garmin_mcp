"""
Modular MCP Server for Garmin Connect Data

Stateless architecture: tokens passed per-request via _meta.context.sport_platform_token
Login via garmin_login tool → tokens returned in response → stored in JWT by frontend

3-layer architecture:
  SDK (garminconnect fork) → API (garmin_mcp.api.*) → Tools (garmin_mcp.*.py)
"""

import sys

from fastmcp import FastMCP

# Import tool modules (3-layer architecture)
from garmin_mcp import health
from garmin_mcp import activities
from garmin_mcp import training
from garmin_mcp import workouts
from garmin_mcp import profile
from garmin_mcp import gear
from garmin_mcp import body_data
from garmin_mcp import womens_health
from garmin_mcp import calendar
from garmin_mcp import auth_tool


def main():
    """Initialize the MCP server and register all tools"""

    print("Garmin MCP v2: 3-layer architecture, per-request token loading.", file=sys.stderr)

    # Create the MCP app
    app = FastMCP("Garmin Connect v2.0")

    # Register all tools (50 total)
    app = auth_tool.register_tools(app)
    app = health.register_tools(app)
    app = activities.register_tools(app)
    app = training.register_tools(app)
    app = workouts.register_tools(app)
    app = profile.register_tools(app)
    app = gear.register_tools(app)
    app = body_data.register_tools(app)
    app = womens_health.register_tools(app)
    app = calendar.register_tools(app)

    # Run the MCP server
    app.run()


if __name__ == "__main__":
    main()
