"""
Garmin Connect MCP Server

Session-based authentication using FastMCP Context.
Each MCP connection has isolated session state.

Usage:
1. Call garmin_login_tool(email, password) to authenticate
   - Returns tokens to caller for persistence (cookies, etc.)
   - Stores tokens in MCP session for this connection

2. Or call set_garmin_session(tokens) to restore a session
   - Use tokens from previous login
   - After this, all data tools work

3. Call any data tool (get_stats, get_activities, etc.)
   - Tools automatically use session tokens via Context
"""

from mcp.server.fastmcp import FastMCP

# Import tool registration modules
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
from garmin_mcp import workout_templates
from garmin_mcp import data_management
from garmin_mcp import womens_health


def main():
    """Initialize the MCP server and register all tools."""

    # Create the MCP app
    app = FastMCP("Garmin Connect MCP")

    # Register authentication and common tools
    app = auth_tool.register_tools(app)

    # Register data tools (all use ctx: Context pattern)
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

    # Register resources (workout templates)
    app = workout_templates.register_resources(app)

    # Run the MCP server
    app.run()


if __name__ == "__main__":
    main()
