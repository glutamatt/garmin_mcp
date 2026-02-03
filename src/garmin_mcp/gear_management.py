"""
Gear management functions for Garmin Connect MCP Server

Uses FastMCP Context for session state.
"""
import json

from mcp.server.fastmcp import Context

from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all gear management tools with the MCP server app"""

    @app.tool()
    async def get_gear(ctx: Context, include_stats: bool = True) -> str:
        """Get all gear

        Args:
            include_stats: Include usage statistics (default True)
        """
        try:
            client = await get_client(ctx)
            device_info = client.get_device_last_used()
            if not device_info:
                return "Could not get user profile"
            user_profile_id = device_info.get("userProfileNumber")

            gear_list = client.get_gear(user_profile_id)
            if not gear_list:
                return "No gear found"

            curated = []
            for g in gear_list:
                gear = {
                    "uuid": g.get("uuid"),
                    "name": g.get("displayName"),
                    "type": g.get("gearTypeName"),
                    "status": g.get("gearStatusName"),
                }
                if include_stats:
                    try:
                        stats = client.get_gear_stats(g.get("uuid"))
                        if stats:
                            gear["total_activities"] = stats.get("totalActivities")
                            gear["total_distance_km"] = round(stats.get("totalDistance", 0) / 1000, 1)
                    except Exception:
                        pass
                curated.append({k: v for k, v in gear.items() if v is not None})

            return json.dumps({"gear_count": len(curated), "gear": curated}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def add_gear_to_activity(activity_id: int, gear_uuid: str, ctx: Context) -> str:
        """Associate gear with an activity

        Args:
            activity_id: Activity ID
            gear_uuid: Gear UUID (from get_gear)
        """
        try:
            client = await get_client(ctx)
            client.add_gear_to_activity(activity_id, gear_uuid)
            return json.dumps({"success": True, "message": "Gear added to activity"}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def remove_gear_from_activity(activity_id: int, gear_uuid: str, ctx: Context) -> str:
        """Remove gear from an activity

        Args:
            activity_id: Activity ID
            gear_uuid: Gear UUID
        """
        try:
            client = await get_client(ctx)
            client.remove_gear_from_activity(activity_id, gear_uuid)
            return json.dumps({"success": True, "message": "Gear removed from activity"}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    return app
