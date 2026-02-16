"""
Gear tools — shoes, bikes, accessories (3 tools).

Thin MCP wrappers over Garmin Connect gear API.
"""
import json
from fastmcp import Context
from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register gear tools with the MCP server app."""

    @app.tool()
    async def get_gear(user_profile_id: str, ctx: Context) -> str:
        """Get all gear (shoes, bikes, etc.) with usage stats.

        Returns gear name, brand, distance tracked, activity count, and retirement status.

        Args:
            user_profile_id: User profile ID (obtain from get_devices userProfileNumber field)
        """
        try:
            client = get_client(ctx)
            gear_list = client.get_gear(user_profile_id)
            if not gear_list:
                return json.dumps({"error": "No gear found."})

            curated = {"count": len(gear_list), "gear": []}
            for g in gear_list:
                gear_item = {
                    "uuid": g.get("uuid"),
                    "display_name": g.get("displayName"),
                    "model_name": g.get("modelName"),
                    "brand_name": g.get("brandName"),
                    "gear_type": g.get("gearTypePk"),
                    "maximum_distance_meters": g.get("maximumDistanceMeter"),
                    "current_distance_meters": (
                        g.get("gearStatusDTOList", [{}])[0].get("totalDistanceInMeters")
                        if g.get("gearStatusDTOList") else None
                    ),
                    "date_begun": g.get("dateBegun"),
                    "date_retired": g.get("dateRetired"),
                    "notified": g.get("notified"),
                }
                gear_item = {k: v for k, v in gear_item.items() if v is not None}
                curated["gear"].append(gear_item)

            return json.dumps(curated, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    async def add_gear_to_activity(activity_id: int, gear_uuid: str, ctx: Context) -> str:
        """Associate gear with an activity.

        Args:
            activity_id: ID of the activity
            gear_uuid: UUID of the gear to add (get from get_gear)
        """
        try:
            get_client(ctx).add_gear_to_activity(gear_uuid, activity_id)
            return json.dumps({
                "status": "success",
                "activity_id": activity_id,
                "gear_uuid": gear_uuid,
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    async def remove_gear_from_activity(activity_id: int, gear_uuid: str, ctx: Context) -> str:
        """Remove gear association from an activity.

        Args:
            activity_id: ID of the activity
            gear_uuid: UUID of the gear to remove
        """
        try:
            get_client(ctx).remove_gear_from_activity(gear_uuid, activity_id)
            return json.dumps({
                "status": "success",
                "activity_id": activity_id,
                "gear_uuid": gear_uuid,
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    return app
