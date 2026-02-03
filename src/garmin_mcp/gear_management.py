"""
Gear management functions for Garmin Connect MCP Server
"""
import json
import datetime
from typing import Any, Dict, List, Optional, Union

from fastmcp import Context

from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all gear management tools with the MCP server app"""

    @app.tool()
    async def get_gear(user_profile_id: str, ctx: Context) -> str:
        """Get all gear registered with the user account

        Args:
            user_profile_id: User profile ID (can be obtained from get_device_last_used)
        """
        try:
            client = await get_client(ctx)
            gear_list = client.get_gear(user_profile_id)
            if not gear_list:
                return "No gear found."

            # Curate the response
            curated = {
                "count": len(gear_list),
                "gear": []
            }

            for g in gear_list:
                gear_item = {
                    "uuid": g.get('uuid'),
                    "display_name": g.get('displayName'),
                    "model_name": g.get('modelName'),
                    "brand_name": g.get('brandName'),
                    "gear_type": g.get('gearTypePk'),
                    "maximum_distance_meters": g.get('maximumDistanceMeter'),
                    "current_distance_meters": g.get('gearStatusDTOList', [{}])[0].get('totalDistanceInMeters') if g.get('gearStatusDTOList') else None,
                    "date_begun": g.get('dateBegun'),
                    "date_retired": g.get('dateRetired'),
                    "notified": g.get('notified'),
                }
                # Remove None values
                gear_item = {k: v for k, v in gear_item.items() if v is not None}
                curated["gear"].append(gear_item)

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving gear: {str(e)}"

    @app.tool()
    async def get_gear_defaults(user_profile_id: str, ctx: Context) -> str:
        """Get default gear settings

        Args:
            user_profile_id: User profile ID (can be obtained from get_device_last_used)
        """
        try:
            client = await get_client(ctx)
            defaults = client.get_gear_defaults(user_profile_id)
            if not defaults:
                return "No gear defaults found."

            # Curate the response - remove internal IDs
            curated = {}
            for key, value in defaults.items():
                if key not in ['userProfileNumber', 'userId']:
                    curated[key] = value

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving gear defaults: {str(e)}"

    @app.tool()
    async def get_gear_stats(gear_uuid: str, ctx: Context) -> str:
        """Get statistics for specific gear

        Args:
            gear_uuid: UUID of the gear item
        """
        try:
            client = await get_client(ctx)
            stats = client.get_gear_stats(gear_uuid)
            if not stats:
                return f"No stats found for gear with UUID {gear_uuid}."

            # Curate the stats
            curated = {
                "uuid": gear_uuid,
                "total_activities": stats.get('totalActivities'),
                "total_distance_meters": stats.get('totalDistance'),
                "total_duration_seconds": stats.get('totalDuration'),
                "total_ascent_meters": stats.get('totalAscent'),
                "total_descent_meters": stats.get('totalDescent'),
                "last_activity_date": stats.get('lastActivityDate'),
            }

            # Remove None values
            curated = {k: v for k, v in curated.items() if v is not None}

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving gear stats: {str(e)}"

    @app.tool()
    async def add_gear_to_activity(activity_id: int, gear_uuid: str, ctx: Context) -> str:
        """Associate gear with an activity

        Links a specific piece of gear (like shoes, bike, etc.) to an activity.

        Args:
            activity_id: ID of the activity
            gear_uuid: UUID of the gear to add (get from get_gear)
        """
        try:
            client = await get_client(ctx)
            result = client.add_gear_to_activity(activity_id, gear_uuid)

            return json.dumps({
                "success": True,
                "activity_id": activity_id,
                "gear_uuid": gear_uuid,
                "message": "Gear successfully added to activity"
            }, indent=2)
        except Exception as e:
            return f"Error adding gear to activity: {str(e)}"

    @app.tool()
    async def remove_gear_from_activity(activity_id: int, gear_uuid: str, ctx: Context) -> str:
        """Remove gear association from an activity

        Unlinks a specific piece of gear from an activity.

        Args:
            activity_id: ID of the activity
            gear_uuid: UUID of the gear to remove
        """
        try:
            client = await get_client(ctx)
            result = client.remove_gear_from_activity(activity_id, gear_uuid)

            return json.dumps({
                "success": True,
                "activity_id": activity_id,
                "gear_uuid": gear_uuid,
                "message": "Gear successfully removed from activity"
            }, indent=2)
        except Exception as e:
            return f"Error removing gear from activity: {str(e)}"

    return app
