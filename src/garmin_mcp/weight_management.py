"""
Weight management functions for Garmin Connect MCP Server

Uses FastMCP Context for session state.
"""
import json
import datetime

from mcp.server.fastmcp import Context

from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all weight management tools with the MCP server app"""

    @app.tool()
    async def get_weigh_ins(start_date: str, end_date: str, ctx: Context) -> str:
        """Get weight measurements between dates

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            data = client.get_weigh_ins(start_date, end_date)
            if not data:
                return f"No weight data between {start_date} and {end_date}"

            daily_summaries = data.get("dailyWeightSummaries", [])
            if not daily_summaries:
                return f"No weight data between {start_date} and {end_date}"

            measurements = []
            for day in daily_summaries:
                for w in day.get("allWeightMetrics", []):
                    measurements.append({
                        "date": w.get("calendarDate"),
                        "weight_kg": round(w.get("weight", 0) / 1000, 2) if w.get("weight") else None,
                        "bmi": w.get("bmi"),
                        "body_fat_percent": w.get("bodyFat"),
                    })

            curated = {
                "date_range": {"start": start_date, "end": end_date},
                "count": len(measurements),
                "measurements": [{k: v for k, v in m.items() if v is not None} for m in measurements]
            }
            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def add_weigh_in(weight: float, ctx: Context, unit_key: str = "kg") -> str:
        """Add weight measurement

        Args:
            weight: Weight value
            unit_key: Unit ('kg' or 'lb')
        """
        try:
            client = await get_client(ctx)
            client.add_weigh_in(weight=weight, unitKey=unit_key)
            return json.dumps({"success": True, "weight": weight, "unit": unit_key}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def delete_weigh_ins(date: str, ctx: Context) -> str:
        """Delete weight measurements for a date

        Args:
            date: Date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            deleted = client.delete_weigh_ins(date, delete_all=True)
            return json.dumps({"success": True, "date": date, "deleted_count": deleted}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    return app
