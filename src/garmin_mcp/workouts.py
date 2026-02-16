"""
Workout tools — MCP registration layer.

Thin wrappers: get_client → api call → json.dumps.
8 tools (was 12 in workouts.py).
"""

import json

from fastmcp import Context
from garmin_mcp.client_factory import get_client
from garmin_mcp.api import workouts as api


def register_tools(app):
    """Register all workout tools with the MCP server app."""

    @app.tool()
    async def get_workouts(ctx: Context) -> str:
        """Get all workouts from the Garmin Connect library.

        Returns workout summaries with IDs for use with other workout tools.
        """
        try:
            return json.dumps(api.get_workouts(get_client(ctx)), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_workout_by_id(workout_id: int, ctx: Context) -> str:
        """Get detailed workout info including segments and structure.

        Use get_workouts to find workout IDs.

        Args:
            workout_id: ID of the workout to retrieve
        """
        try:
            return json.dumps(api.get_workout_by_id(get_client(ctx), workout_id), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def get_scheduled_workouts(start_date: str, end_date: str, ctx: Context) -> str:
        """Get workouts scheduled on the calendar between two dates.

        Returns schedule_id for each entry (needed for unschedule/reschedule).

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        try:
            return json.dumps(api.get_scheduled_workouts(get_client(ctx), start_date, end_date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def create_workout(workout_data: dict, ctx: Context, date: str = None) -> str:
        """Create a new workout and optionally schedule it on a date.

        If date is provided: creates + schedules in one atomic step (replaces old upload + schedule flow).
        If no date: creates in library only — use reschedule_workout later to add to calendar.

        Accepts simplified format: {workoutName, sport: "running", steps: [{stepOrder, stepType, endCondition, endConditionValue, ...}]}

        REPEAT GROUPS (use for intervals instead of duplicating steps):
        {stepOrder: 2, stepType: "repeat", numberOfIterations: 6, workoutSteps: [
          {stepOrder: 1, stepType: "interval", endCondition: "distance", endConditionValue: 800},
          {stepOrder: 2, stepType: "recovery", endCondition: "distance", endConditionValue: 200}
        ]}

        Step types: warmup, cooldown, interval, recovery, rest, repeat, other.
        End conditions: time (seconds), distance (meters), lap.button.
        Target types: no.target, heart.rate.zone (zoneNumber 1-5), pace.zone (targetValueOne=faster m/s, targetValueTwo=slower m/s), power.zone (zoneNumber 1-7).

        Args:
            workout_data: Workout structure (simplified or full Garmin format).
            date: Optional schedule date in YYYY-MM-DD format.
        """
        try:
            return json.dumps(api.create_workout(get_client(ctx), workout_data, date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def update_workout(workout_id: int, workout_data: dict, ctx: Context) -> str:
        """Replace an existing workout's definition (full replacement, not partial).

        Provide the complete workout structure. See create_workout for format details.

        Args:
            workout_id: ID of the workout to update (from get_workouts).
            workout_data: Complete workout structure.
        """
        try:
            return json.dumps(api.update_workout(get_client(ctx), workout_id, workout_data), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def delete_workout(workout_id: int, ctx: Context) -> str:
        """Delete a workout from the library and clean up all scheduled instances.

        Automatically unschedules all calendar entries for this workout before deletion.
        This action cannot be undone.

        Args:
            workout_id: ID of the workout to delete (NOT a schedule_id).
        """
        try:
            return json.dumps(api.delete_workout(get_client(ctx), workout_id), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def unschedule_workout(schedule_id: int, ctx: Context) -> str:
        """Remove a scheduled workout from the calendar WITHOUT deleting from library.

        Use this to cancel a planned session while keeping the workout for later.
        To move a workout to a different date, use reschedule_workout instead.

        Args:
            schedule_id: The schedule ID (from get_scheduled_workouts or create_workout). NOT the workout ID.
        """
        try:
            return json.dumps(api.unschedule_workout(get_client(ctx), schedule_id), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @app.tool()
    async def reschedule_workout(schedule_id: int, new_date: str, ctx: Context) -> str:
        """Move a scheduled workout to a different date.

        Args:
            schedule_id: The schedule ID (NOT the workout ID).
            new_date: New date in YYYY-MM-DD format.
        """
        try:
            return json.dumps(api.reschedule_workout(get_client(ctx), schedule_id, new_date), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    return app
