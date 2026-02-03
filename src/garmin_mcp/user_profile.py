"""
User Profile functions for Garmin Connect MCP Server
"""
import json
import datetime
from typing import Any, Dict, List, Optional, Union

from fastmcp import Context

from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all user profile tools with the MCP server app"""

    @app.tool()
    async def get_full_name(ctx: Context) -> str:
        """Get user's full name from profile"""
        try:
            client = get_client(ctx)
            full_name = client.get_full_name()
            if isinstance(full_name, (dict, list)):
                return json.dumps(full_name, indent=2)
            return str(full_name)
        except Exception as e:
            return f"Error retrieving user's full name: {str(e)}"

    @app.tool()
    async def get_unit_system(ctx: Context) -> str:
        """Get user's preferred unit system from profile"""
        try:
            client = get_client(ctx)
            unit_system = client.get_unit_system()
            if isinstance(unit_system, (dict, list)):
                return json.dumps(unit_system, indent=2)
            return str(unit_system)
        except Exception as e:
            return f"Error retrieving unit system: {str(e)}"

    @app.tool()
    async def get_user_profile(ctx: Context) -> str:
        """Get user profile information"""
        try:
            client = get_client(ctx)
            profile = client.get_user_profile()
            if not profile:
                return "No user profile information found."
            return json.dumps(profile, indent=2)
        except Exception as e:
            return f"Error retrieving user profile: {str(e)}"

    @app.tool()
    async def get_userprofile_settings(ctx: Context) -> str:
        """Get user profile settings"""
        try:
            client = get_client(ctx)
            settings = client.get_userprofile_settings()
            if not settings:
                return "No user profile settings found."
            return json.dumps(settings, indent=2)
        except Exception as e:
            return f"Error retrieving user profile settings: {str(e)}"

    return app
