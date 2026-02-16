"""
Activity tools — MCP registration layer.

Thin wrappers: get_client → api call → json.dumps.
5 tools (was 13 in activity_management.py).
"""

import json

from fastmcp import Context
from garmin_mcp.client_factory import get_client
from garmin_mcp.api import activities as api


def register_tools(app):
    """Register all activity tools with the MCP server app."""

    @app.tool()
    async def get_activities(
        ctx: Context,
        start_date: str = None,
        end_date: str = None,
        activity_type: str = "",
        start: int = 0,
        limit: int = 20,
    ) -> str:
        """Get activities by date range OR pagination.

        For date-based: provide start_date + end_date (+ optional activity_type filter).
        For pagination: provide start index + limit (newest first).

        Args:
            start_date: Start date in YYYY-MM-DD format (date range mode)
            end_date: End date in YYYY-MM-DD format (date range mode)
            activity_type: Optional filter (e.g., 'running', 'cycling')
            start: Starting index for pagination (default 0)
            limit: Max activities to return (default 20, max 100)
        """
        try:
            return json.dumps(
                api.get_activities(get_client(ctx), start_date, end_date, activity_type, start, limit),
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_activity(activity_id: int, ctx: Context) -> str:
        """Detailed activity info: timing, distance, HR, cadence, power, training effect, weather.

        Use get_activities to find activity IDs first.

        Args:
            activity_id: Numeric activity ID
        """
        try:
            return json.dumps(api.get_activity(get_client(ctx), activity_id), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_activity_splits(activity_id: int, ctx: Context) -> str:
        """Per-lap splits: distance, duration, pace, HR, cadence, power per lap.

        Args:
            activity_id: Numeric activity ID
        """
        try:
            return json.dumps(api.get_activity_splits(get_client(ctx), activity_id), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_activity_hr_in_timezones(activity_id: int, ctx: Context) -> str:
        """Time spent in each heart rate zone (zone 1-5) during an activity.

        Args:
            activity_id: Numeric activity ID
        """
        try:
            return json.dumps(api.get_activity_hr_in_timezones(get_client(ctx), activity_id), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_activity_types(ctx: Context) -> str:
        """All available activity type codes (reference data for filtering)."""
        try:
            return json.dumps(api.get_activity_types(get_client(ctx)), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    return app
