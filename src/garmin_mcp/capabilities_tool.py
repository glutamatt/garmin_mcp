"""
Device capabilities tool — MCP registration layer.

Thin wrapper: get_client → api call → json.dumps.
The frontend calls it once at login (`api/auth/login/route.ts`).
"""

import json

from fastmcp import Context
from garmin_mcp.client_factory import get_client
from garmin_mcp.api import capabilities as api_capabilities


def register_tools(app):
    """Register the device capabilities tool with the MCP server app."""

    @app.tool()
    async def get_device_capabilities(ctx: Context) -> str:
        """Device capability flags and list of tools unsupported by user's watch.

        Returns capabilities dict and disabled_tools list. Called once at login,
        cached client-side to filter tools before each chat request.
        """
        try:
            return json.dumps(api_capabilities.get_device_capabilities(get_client(ctx)), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    return app
