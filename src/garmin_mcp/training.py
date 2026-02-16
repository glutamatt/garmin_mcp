"""
Training & Performance tools — MCP registration layer.

Thin wrappers: get_client → api call → json.dumps.
7 tools (was 10+9 in training.py + challenges.py).
"""

import json

from fastmcp import Context
from garmin_mcp.client_factory import get_client
from garmin_mcp.api import training as api


def register_tools(app):
    """Register all training tools with the MCP server app."""

    @app.tool()
    async def get_max_metrics(date: str, ctx: Context) -> str:
        """VO2 max, fitness age, and lactate threshold in one response.

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_max_metrics(get_client(ctx), date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_hrv_data(date: str, ctx: Context) -> str:
        """HRV overnight summary: last night avg, weekly avg, baseline range, status.

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_hrv_data(get_client(ctx), date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_training_status(date: str, ctx: Context) -> str:
        """Training status: productive/maintaining/detraining, ACWR, VO2 max, load balance.

        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_training_status(get_client(ctx), date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_progress_summary(
        start_date: str, end_date: str, metric: str, ctx: Context
    ) -> str:
        """Progress summary for a metric between dates.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            metric: One of: distance, duration, elevationGain, movingDuration
        """
        try:
            return json.dumps(
                api.get_progress_summary(get_client(ctx), start_date, end_date, metric),
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_race_predictions(ctx: Context) -> str:
        """Race time predictions (5K, 10K, half marathon, marathon)."""
        try:
            return json.dumps(api.get_race_predictions(get_client(ctx)), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_goals(ctx: Context, goal_type: str = "active") -> str:
        """Garmin Connect goals.

        Args:
            goal_type: Type of goals: active, future, or past
        """
        try:
            return json.dumps(api.get_goals(get_client(ctx), goal_type), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_personal_record(ctx: Context) -> str:
        """Personal records across all activities (fastest 5K, longest run, etc.)."""
        try:
            return json.dumps(api.get_personal_record(get_client(ctx)), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    return app
