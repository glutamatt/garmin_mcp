"""
Health & Wellness tools — MCP registration layer.

Thin wrappers: get_client → api call → json.dumps.
10 tools (was 28 in health_wellness.py).
"""

import json

from fastmcp import Context
from garmin_mcp.client_factory import get_client
from garmin_mcp.api import health as api


def register_tools(app):
    """Register all health tools with the MCP server app."""

    @app.tool()
    async def get_coaching_snapshot(date: str, ctx: Context) -> str:
        """Daily coaching overview in one call: stats, sleep, training readiness, body battery, HRV.

        Use this as the default first call for any daily health check-in.

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_coaching_snapshot(get_client(ctx), date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_stats(date: str, ctx: Context) -> str:
        """Daily activity stats: steps, calories, HR, stress, body battery, SpO2, respiration.

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_stats(get_client(ctx), date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_sleep(date: str, ctx: Context) -> str:
        """Curated sleep summary: score, phases, SpO2, respiration, HRV.

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_sleep(get_client(ctx), date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_stress(date: str, ctx: Context) -> str:
        """Curated stress summary: avg/max levels, distribution (rest/low/medium/high %).

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_stress(get_client(ctx), date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_heart_rate(date: str, ctx: Context) -> str:
        """Curated HR summary: resting, min, max, avg, 7-day resting trend.

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_heart_rate(get_client(ctx), date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_respiration(date: str, ctx: Context) -> str:
        """Curated respiration: lowest, highest, avg waking, avg sleep breaths per minute.

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_respiration(get_client(ctx), date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_body_battery(start_date: str, end_date: str, ctx: Context) -> str:
        """Body battery: charge/drain per day with activity events and feedback.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_body_battery(get_client(ctx), start_date, end_date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_spo2_data(date: str, ctx: Context) -> str:
        """SpO2 (blood oxygen): avg, lowest, latest, sleep avg, 7-day trend.

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_spo2(get_client(ctx), date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_training_readiness(date: str, ctx: Context) -> str:
        """Training readiness: score, contributing factors (sleep, recovery, HRV, load, stress).

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_training_readiness(get_client(ctx), date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_body_composition(start_date: str, ctx: Context, end_date: str = None) -> str:
        """Body composition data for a date or range.

        Args:
            start_date: Date in YYYY-MM-DD format (or start of range)
            end_date: Optional end date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_body_composition(get_client(ctx), start_date, end_date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    return app
