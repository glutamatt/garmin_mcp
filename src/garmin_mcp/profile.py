"""
Profile & Devices tools — MCP registration layer.

Thin wrappers: get_client → api call → json.dumps.
4 tools (was 10 in user_profile.py + devices.py).
"""

import json

from fastmcp import Context
from garmin_mcp.client_factory import get_client
from garmin_mcp.api import profile as api
from garmin_mcp.api import capabilities as api_capabilities


def register_tools(app):
    """Register all profile tools with the MCP server app."""

    @app.tool()
    async def get_full_name(ctx: Context) -> str:
        """Get user's full display name from their Garmin profile.

        Returns the name as a plain string (e.g. "Jean Dupont"), not JSON.
        """
        try:
            return api.get_full_name(get_client(ctx))
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_user_profile(ctx: Context) -> str:
        """User profile: name, weight, height, VO2max, lactate threshold, unit system + HR zones (Z1-Z5) + power zones (Z1-Z7)."""
        try:
            return json.dumps(api.get_user_profile(get_client(ctx)), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_hr_zones(ctx: Context) -> str:
        """Athlete's HR and power zone boundaries (Z1-Z5 for HR, Z1-Z7 for power).

        Fetched from the latest activity's zone data. Returns low_bpm per HR zone
        and low_watts per power zone. Use this to classify efforts by zone.
        """
        try:
            return json.dumps(api.get_hr_zones(get_client(ctx)), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_devices(ctx: Context) -> str:
        """All Garmin devices with last-used and primary-training flags baked in.

        Enriched: combines device list + last-used + primary training device detection.
        """
        try:
            return json.dumps(api.get_devices(get_client(ctx)), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

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
