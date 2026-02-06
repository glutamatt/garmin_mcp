"""
Modular MCP Server for Garmin Connect Data

Stateless architecture: tokens passed per-request via _meta.context.sport_platform_token
Login via garmin_login tool → tokens returned in response → stored in JWT by frontend
"""

import sys

from fastmcp import FastMCP

# Import all modules
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
from garmin_mcp import auth_tool


def main():
    """Initialize the MCP server and register all tools"""

    print("Garmin MCP: stateless mode - per-request token loading from JWT.", file=sys.stderr)

    # Create the MCP app
    app = FastMCP("Garmin Connect v1.0")

    # Register all tools
    app = auth_tool.register_tools(app)
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

    # Run the MCP server
    app.run()


if __name__ == "__main__":
    main()
