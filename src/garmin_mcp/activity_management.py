"""
Activity Management functions for Garmin Connect MCP Server

Uses FastMCP Context for session state.
"""

import json
from typing import Optional

from mcp.server.fastmcp import Context

from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all activity management tools with the MCP server app"""

    @app.tool()
    async def get_activities_by_date(
        start_date: str,
        end_date: str,
        ctx: Context,
        activity_type: str = "",
    ) -> str:
        """Get activities between dates, optionally filtered by type

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            activity_type: Optional filter (cycling, running, swimming)
        """
        try:
            client = await get_client(ctx)
            activities = client.get_activities_by_date(
                start_date, end_date, activity_type
            )
            if not activities:
                return f"No activities found between {start_date} and {end_date}" + (
                    f" for type '{activity_type}'" if activity_type else ""
                )

            curated = {
                "count": len(activities),
                "date_range": {"start": start_date, "end": end_date},
                "activities": [],
            }

            for a in activities:
                activity = {
                    "id": a.get("activityId"),
                    "name": a.get("activityName"),
                    "type": a.get("activityType", {}).get("typeKey"),
                    "start_time": a.get("startTimeLocal"),
                    "distance_meters": a.get("distance"),
                    "duration_seconds": a.get("duration"),
                    "calories": a.get("calories"),
                    "avg_hr_bpm": a.get("averageHR"),
                    "max_hr_bpm": a.get("maxHR"),
                    "steps": a.get("steps"),
                }
                activity = {k: v for k, v in activity.items() if v is not None}
                curated["activities"].append(activity)

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_activities_fordate(date: str, ctx: Context) -> str:
        """Get activities for a specific date

        Args:
            date: Date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            data = client.get_activities_fordate(date)
            if not data:
                return f"No activities found for {date}"

            activities_data = data.get("ActivitiesForDay", {})
            payload = activities_data.get("payload", [])

            if not payload:
                return f"No activities found for {date}"

            curated = {"date": date, "count": len(payload), "activities": []}

            for a in payload:
                activity = {
                    "id": a.get("activityId"),
                    "name": a.get("activityName"),
                    "type": a.get("activityType", {}).get("typeKey"),
                    "start_time": a.get("startTimeLocal"),
                    "distance_meters": a.get("distance"),
                    "duration_seconds": a.get("duration"),
                    "calories": a.get("calories"),
                    "avg_hr_bpm": a.get("averageHR"),
                    "steps": a.get("steps"),
                }
                activity = {k: v for k, v in activity.items() if v is not None}
                curated["activities"].append(activity)

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_activity(activity_id: int, ctx: Context) -> str:
        """Get activity details

        Args:
            activity_id: Activity ID
        """
        try:
            client = await get_client(ctx)
            activity = client.get_activity(activity_id)
            if not activity:
                return f"No activity found with ID {activity_id}"

            summary = activity.get("summaryDTO", {})
            activity_type = activity.get("activityTypeDTO", {})
            metadata = activity.get("metadataDTO", {})

            curated = {
                "id": activity.get("activityId"),
                "name": activity.get("activityName"),
                "type": activity_type.get("typeKey"),
                "start_time_local": summary.get("startTimeLocal"),
                "duration_seconds": summary.get("duration"),
                "moving_duration_seconds": summary.get("movingDuration"),
                "distance_meters": summary.get("distance"),
                "avg_speed_mps": summary.get("averageSpeed"),
                "max_speed_mps": summary.get("maxSpeed"),
                "avg_hr_bpm": summary.get("averageHR"),
                "max_hr_bpm": summary.get("maxHR"),
                "calories": summary.get("calories"),
                "avg_cadence": summary.get("averageRunCadence"),
                "steps": summary.get("steps"),
                "avg_power_watts": summary.get("averagePower"),
                "training_effect": summary.get("trainingEffect"),
                "anaerobic_training_effect": summary.get("anaerobicTrainingEffect"),
                "training_load": summary.get("activityTrainingLoad"),
                "lap_count": metadata.get("lapCount"),
            }

            curated = {k: v for k, v in curated.items() if v is not None}
            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_activity_splits(activity_id: int, ctx: Context) -> str:
        """Get splits for an activity

        Args:
            activity_id: Activity ID
        """
        try:
            client = await get_client(ctx)
            splits = client.get_activity_splits(activity_id)
            if not splits:
                return f"No splits found for activity {activity_id}"

            laps = splits.get("lapDTOs", [])

            curated = {
                "activity_id": splits.get("activityId"),
                "lap_count": len(laps),
                "laps": [],
            }

            for lap in laps:
                lap_data = {
                    "lap_number": lap.get("lapIndex"),
                    "distance_meters": lap.get("distance"),
                    "duration_seconds": lap.get("duration"),
                    "avg_speed_mps": lap.get("averageSpeed"),
                    "avg_hr_bpm": lap.get("averageHR"),
                    "max_hr_bpm": lap.get("maxHR"),
                    "calories": lap.get("calories"),
                    "avg_cadence": lap.get("averageRunCadence"),
                    "avg_power_watts": lap.get("averagePower"),
                }
                lap_data = {k: v for k, v in lap_data.items() if v is not None}
                curated["laps"].append(lap_data)

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_activity_typed_splits(activity_id: int, ctx: Context) -> str:
        """Get typed splits for an activity

        Args:
            activity_id: Activity ID
        """
        try:
            client = await get_client(ctx)
            typed_splits = client.get_activity_typed_splits(activity_id)
            if not typed_splits:
                return f"No typed splits found for activity {activity_id}"
            return json.dumps(typed_splits, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_activity_split_summaries(activity_id: int, ctx: Context) -> str:
        """Get split summaries for an activity

        Args:
            activity_id: Activity ID
        """
        try:
            client = await get_client(ctx)
            split_summaries = client.get_activity_split_summaries(activity_id)
            if not split_summaries:
                return f"No split summaries found for activity {activity_id}"
            return json.dumps(split_summaries, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_activity_weather(activity_id: int, ctx: Context) -> str:
        """Get weather data for an activity

        Args:
            activity_id: Activity ID
        """
        try:
            client = await get_client(ctx)
            weather = client.get_activity_weather(activity_id)
            if not weather:
                return f"No weather data found for activity {activity_id}"

            curated = {
                "activity_id": activity_id,
                "temperature_celsius": weather.get("temp"),
                "apparent_temperature_celsius": weather.get("apparentTemp"),
                "humidity_percent": weather.get("relativeHumidity"),
                "wind_speed_mps": weather.get("windSpeed"),
                "wind_direction_degrees": weather.get("windDirection"),
                "weather_type": weather.get("weatherTypeDTO", {}).get("weatherTypeName"),
            }

            curated = {k: v for k, v in curated.items() if v is not None}
            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_activity_hr_in_timezones(activity_id: int, ctx: Context) -> str:
        """Get heart rate in time zones for an activity

        Args:
            activity_id: Activity ID
        """
        try:
            client = await get_client(ctx)
            hr_zones = client.get_activity_hr_in_timezones(activity_id)
            if not hr_zones:
                return f"No HR zone data found for activity {activity_id}"
            return json.dumps(hr_zones, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_activity_gear(activity_id: int, ctx: Context) -> str:
        """Get gear data for an activity

        Args:
            activity_id: Activity ID
        """
        try:
            client = await get_client(ctx)
            gear = client.get_activity_gear(activity_id)
            if not gear:
                return f"No gear data found for activity {activity_id}"
            return json.dumps(gear, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_activity_exercise_sets(activity_id: int, ctx: Context) -> str:
        """Get exercise sets for strength training activity

        Args:
            activity_id: Activity ID
        """
        try:
            client = await get_client(ctx)
            exercise_sets = client.get_activity_exercise_sets(activity_id)
            if not exercise_sets:
                return f"No exercise sets found for activity {activity_id}"
            return json.dumps(exercise_sets, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def count_activities(ctx: Context) -> str:
        """Get total count of activities"""
        try:
            client = await get_client(ctx)
            count = client.count_activities()
            if count is None:
                return "Unable to retrieve activity count"
            return json.dumps({"total_activities": count}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_activities(ctx: Context, start: int = 0, limit: int = 20) -> str:
        """Get activities with pagination

        Args:
            start: Starting index (default 0)
            limit: Max results (default 20, max 100)
        """
        try:
            client = await get_client(ctx)
            limit = min(max(1, limit), 100)
            activities = client.get_activities(start, limit)
            if not activities:
                return f"No activities found at index {start}"

            curated = {
                "start": start,
                "limit": limit,
                "count": len(activities),
                "has_more": len(activities) == limit,
                "activities": [],
            }

            for a in activities:
                activity = {
                    "id": a.get("activityId"),
                    "name": a.get("activityName"),
                    "type": a.get("activityType", {}).get("typeKey"),
                    "start_time": a.get("startTimeLocal"),
                    "distance_meters": a.get("distance"),
                    "duration_seconds": a.get("duration"),
                    "calories": a.get("calories"),
                    "avg_hr_bpm": a.get("averageHR"),
                    "max_hr_bpm": a.get("maxHR"),
                }
                activity = {k: v for k, v in activity.items() if v is not None}
                curated["activities"].append(activity)

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_activity_types(ctx: Context) -> str:
        """Get all available activity types"""
        try:
            client = await get_client(ctx)
            activity_types = client.get_activity_types()
            if not activity_types:
                return "No activity types found"

            curated = {"count": len(activity_types), "activity_types": []}

            for at in activity_types:
                activity_type = {
                    "type_id": at.get("typeId"),
                    "type_key": at.get("typeKey"),
                    "display_name": at.get("displayName"),
                    "parent_type_id": at.get("parentTypeId"),
                }
                activity_type = {k: v for k, v in activity_type.items() if v is not None}
                curated["activity_types"].append(activity_type)

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    return app
