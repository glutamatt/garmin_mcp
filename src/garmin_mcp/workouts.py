"""
Workout functions for Garmin Connect MCP Server

Uses FastMCP Context for session state.
"""
import json
from typing import Union

from mcp.server.fastmcp import Context

from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all workout-related tools with the MCP server app"""

    @app.tool()
    async def get_workouts(ctx: Context) -> str:
        """Get all workouts"""
        try:
            client = await get_client(ctx)
            workouts = client.get_workouts()
            if not workouts:
                return "No workouts"

            curated = []
            for w in workouts:
                curated.append({
                    "id": w.get("workoutId"),
                    "name": w.get("workoutName"),
                    "sport": w.get("sportType", {}).get("sportTypeKey"),
                    "created": w.get("createdDate"),
                })

            return json.dumps({"count": len(curated), "workouts": curated}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_workout_by_id(workout_id: Union[int, str], ctx: Context) -> str:
        """Get workout details

        Args:
            workout_id: Workout ID or UUID
        """
        try:
            client = await get_client(ctx)
            workout_str = str(workout_id)

            if '-' in workout_str:
                # UUID - training plan workout
                url = f"workout-service/fbt-adaptive/{workout_str}"
                response = client.garth.get("connectapi", url)
                if response.status_code != 200:
                    return f"No workout with UUID {workout_str}"
                workout = response.json()
            else:
                workout = client.get_workout_by_id(int(workout_str))

            if not workout:
                return f"No workout {workout_id}"

            curated = {
                "id": workout.get("workoutId"),
                "name": workout.get("workoutName"),
                "sport": workout.get("sportType", {}).get("sportTypeKey") if workout.get("sportType") else None,
                "description": workout.get("description"),
                "estimated_duration_sec": workout.get("estimatedDuration") or workout.get("estimatedDurationInSecs"),
                "estimated_distance_m": workout.get("estimatedDistance") or workout.get("estimatedDistanceInMeters"),
            }

            segments = workout.get("workoutSegments", [])
            if segments:
                curated["segment_count"] = len(segments)
                curated["segments"] = []
                for seg in segments:
                    steps = seg.get("workoutSteps", [])
                    curated["segments"].append({
                        "order": seg.get("segmentOrder"),
                        "step_count": len(steps),
                    })

            return json.dumps({k: v for k, v in curated.items() if v is not None}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_scheduled_workouts(start_date: str, end_date: str, ctx: Context) -> str:
        """Get scheduled workouts between dates

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            query = {
                "query": f'query{{workoutScheduleSummariesScalar(startDate:"{start_date}", endDate:"{end_date}")}}'
            }
            result = client.query_garmin_graphql(query)

            if not result or "data" not in result:
                return "No scheduled workouts"

            scheduled = result.get("data", {}).get("workoutScheduleSummariesScalar", [])
            if not scheduled:
                return f"No workouts between {start_date} and {end_date}"

            curated = []
            for s in scheduled:
                curated.append({
                    "date": s.get("scheduleDate"),
                    "name": s.get("workoutName"),
                    "sport": s.get("workoutType"),
                    "completed": s.get("associatedActivityId") is not None,
                    "workout_id": s.get("workoutId"),
                })

            return json.dumps({"count": len(curated), "scheduled": curated}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_training_plan_workouts(calendar_date: str, ctx: Context) -> str:
        """Get training plan workouts for the week

        Args:
            calendar_date: Reference date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            query = {
                "query": f'query{{trainingPlanScalar(calendarDate:"{calendar_date}", lang:"en-US", firstDayOfWeek:"monday")}}'
            }
            result = client.query_garmin_graphql(query)

            if not result or "data" not in result:
                return "No training plan data"

            plan_data = result.get("data", {}).get("trainingPlanScalar", {})
            plans = plan_data.get("trainingPlanWorkoutScheduleDTOS", [])

            if not plans:
                return f"No training plan for {calendar_date}"

            workouts = []
            plan_names = []
            for plan in plans:
                name = plan.get("planName")
                if name and name not in plan_names:
                    plan_names.append(name)

                for w in plan.get("workoutScheduleSummaries", []):
                    workouts.append({
                        "date": w.get("scheduleDate"),
                        "name": w.get("workoutName"),
                        "workout_uuid": w.get("workoutUuid"),
                        "completed": w.get("associatedActivityId") is not None,
                    })

            return json.dumps({
                "training_plans": plan_names,
                "count": len(workouts),
                "workouts": workouts
            }, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def schedule_workout(workout_id: int, calendar_date: str, ctx: Context) -> str:
        """Schedule a workout

        Args:
            workout_id: Workout ID
            calendar_date: Date (YYYY-MM-DD)
        """
        try:
            client = await get_client(ctx)
            url = f"workout-service/schedule/{workout_id}"
            response = client.garth.post("connectapi", url, json={"date": calendar_date})

            if response.status_code == 200:
                return json.dumps({"success": True, "workout_id": workout_id, "date": calendar_date}, indent=2)
            return json.dumps({"success": False, "status": response.status_code}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def upload_workout(workout_data: dict, ctx: Context) -> str:
        """Upload a workout

        Args:
            workout_data: Workout structure (name, sportType, workoutSegments)
        """
        try:
            client = await get_client(ctx)
            result = client.upload_workout(workout_data)

            if isinstance(result, dict):
                return json.dumps({
                    "success": True,
                    "workout_id": result.get("workoutId"),
                    "name": result.get("workoutName"),
                }, indent=2)
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    return app
