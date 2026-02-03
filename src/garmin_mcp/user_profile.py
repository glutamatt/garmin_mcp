"""
User Profile functions for Garmin Connect MCP Server

Uses FastMCP Context for session state.
"""
import json

from mcp.server.fastmcp import Context

from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all user profile tools with the MCP server app"""

    @app.tool()
    async def get_full_name(ctx: Context) -> str:
        """Get user's full name"""
        try:
            client = await get_client(ctx)
            return json.dumps({"full_name": client.get_full_name()}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_unit_system(ctx: Context) -> str:
        """Get user's preferred unit system"""
        try:
            client = await get_client(ctx)
            return json.dumps({"unit_system": client.get_unit_system()}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_user_profile(ctx: Context) -> str:
        """Get user profile information"""
        try:
            client = await get_client(ctx)
            profile = client.get_user_profile()
            if not profile:
                return "No user profile found"
            return json.dumps(profile, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_userprofile_settings(ctx: Context) -> str:
        """Get user profile settings"""
        try:
            client = await get_client(ctx)
            settings = client.get_userprofile_settings()
            if not settings:
                return "No settings found"
            return json.dumps(settings, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    return app
