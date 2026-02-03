"""
Women's health functions for Garmin Connect MCP Server

Uses FastMCP Context for session state.
"""
import json

from mcp.server.fastmcp import Context

from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all women's health tools with the MCP server app"""

    @app.tool()
    async def get_pregnancy_summary(ctx: Context) -> str:
        """Get pregnancy summary data"""
        try:
            client = await get_client(ctx)
            summary = client.get_pregnancy_summary()
            if not summary:
                return "No pregnancy summary found"
            return json.dumps(summary, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_menstrual_data_for_date(date: str, ctx: Context) -> str:
        """Get menstrual data for a date

        Args:
            date: Date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            data = client.get_menstrual_data_for_date(date)
            if not data:
                return f"No menstrual data for {date}"
            return json.dumps(data, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_menstrual_calendar_data(start_date: str, end_date: str, ctx: Context) -> str:
        """Get menstrual calendar data between dates

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            data = client.get_menstrual_calendar_data(start_date, end_date)
            if not data:
                return f"No menstrual data between {start_date} and {end_date}"
            return json.dumps(data, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    return app
