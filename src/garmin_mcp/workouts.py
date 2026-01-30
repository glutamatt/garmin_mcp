"""
Workout-related functions for Garmin Connect MCP Server
"""
import json
import datetime
from typing import Any, Dict, List, Optional, Union

# The garmin_client will be set by the main file
garmin_client = None


def configure(client):
    """Configure the module with the Garmin client instance"""
    global garmin_client
    garmin_client = client


def _curate_workout_summary(workout: dict) -> dict:
    """Extract essential workout metadata for list views"""
    sport_type = workout.get('sportType', {})

    summary = {
        "id": workout.get('workoutId'),
        "name": workout.get('workoutName'),
        "sport": sport_type.get('sportTypeKey'),
        "provider": workout.get('workoutProvider'),
        "created_date": workout.get('createdDate'),
        "updated_date": workout.get('updatedDate'),
    }

    # Add optional fields if present
    if workout.get('description'):
        summary['description'] = workout.get('description')

    if workout.get('estimatedDuration'):
        summary['estimated_duration_seconds'] = workout.get('estimatedDuration')

    if workout.get('estimatedDistance'):
        summary['estimated_distance_meters'] = workout.get('estimatedDistance')

    # Remove None values
    return {k: v for k, v in summary.items() if v is not None}


def _curate_workout_segment(segment: dict) -> dict:
    """Extract essential segment information"""
    curated = {
        "order": segment.get('segmentOrder'),
        "type": segment.get('type'),
    }

    # Duration
    if segment.get('duration'):
        curated['duration_seconds'] = segment.get('duration')
    elif segment.get('durationType'):
        curated['duration_type'] = segment.get('durationType')

    # Target/Intensity
    if segment.get('targetType'):
        curated['target_type'] = segment.get('targetType')
    if segment.get('targetValue'):
        curated['target_value'] = segment.get('targetValue')
    if segment.get('intensityType'):
        curated['intensity'] = segment.get('intensityType')

    # Distance if applicable
    if segment.get('distance'):
        curated['distance_meters'] = segment.get('distance')

    # Repeat count for intervals
    if segment.get('repeatCount'):
        curated['repeat_count'] = segment.get('repeatCount')

    return {k: v for k, v in curated.items() if v is not None}


def _curate_workout_details(workout: dict) -> dict:
    """Extract detailed workout information with segments but without verbose step data"""
    sport_type = workout.get('sportType', {})

    details = {
        "id": workout.get('workoutId'),
        "name": workout.get('workoutName'),
        "sport": sport_type.get('sportTypeKey'),
        "provider": workout.get('workoutProvider'),
        "created_date": workout.get('createdDate'),
        "updated_date": workout.get('updatedDate'),
    }

    # Optional fields
    if workout.get('description'):
        details['description'] = workout.get('description')

    if workout.get('estimatedDuration'):
        details['estimated_duration_seconds'] = workout.get('estimatedDuration')

    if workout.get('estimatedDistance'):
        details['estimated_distance_meters'] = workout.get('estimatedDistance')

    if workout.get('avgTrainingSpeed'):
        details['avg_training_speed_mps'] = workout.get('avgTrainingSpeed')

    # Curate segments (remove verbose step details)
    segments = workout.get('workoutSegments', [])
    if segments:
        details['segments'] = [_curate_workout_segment(seg) for seg in segments]
        details['segment_count'] = len(segments)

    # Remove None values
    return {k: v for k, v in details.items() if v is not None}


def _curate_scheduled_workout(scheduled: dict) -> dict:
    """Extract essential scheduled workout information"""
    workout = scheduled.get('workout', {})
    sport_type = workout.get('sportType', {})

    summary = {
        "date": scheduled.get('date'),
        "workout_id": workout.get('workoutId'),
        "name": workout.get('workoutName'),
        "sport": sport_type.get('sportTypeKey'),
        "provider": workout.get('workoutProvider'),
        "completed": scheduled.get('completed', False),
    }

    # Optional fields
    if workout.get('estimatedDuration'):
        summary['estimated_duration_seconds'] = workout.get('estimatedDuration')

    if workout.get('estimatedDistance'):
        summary['estimated_distance_meters'] = workout.get('estimatedDistance')

    # Remove None values
    return {k: v for k, v in summary.items() if v is not None}


def register_tools(app):
    """Register all workout-related tools with the MCP server app"""

    @app.tool()
    async def get_workouts() -> str:
        """Get all workouts with curated summary list

        Returns a count and list of workout summaries with essential metadata only.
        For detailed workout information including segments, use get_workout_by_id.
        """
        try:
            workouts = garmin_client.get_workouts()
            if not workouts:
                return "No workouts found."

            # Curate the workout list
            curated = {
                "count": len(workouts),
                "workouts": [_curate_workout_summary(w) for w in workouts]
            }

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving workouts: {str(e)}"

    @app.tool()
    async def get_workout_by_id(workout_id: int) -> str:
        """Get detailed information for a specific workout

        Returns workout details including segments and structure.
        Use get_workouts to get a list of available workout IDs.

        Args:
            workout_id: ID of the workout to retrieve
        """
        try:
            workout = garmin_client.get_workout_by_id(workout_id)
            if not workout:
                return f"No workout found with ID {workout_id}."

            # Return curated details with segments but without verbose step data
            curated = _curate_workout_details(workout)
            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving workout: {str(e)}"

    @app.tool()
    async def download_workout(workout_id: int) -> str:
        """Download a workout as a FIT file

        Downloads the workout in FIT format. The binary data cannot be returned
        directly through the MCP interface, but this confirms the workout is available.

        Args:
            workout_id: ID of the workout to download
        """
        try:
            workout_data = garmin_client.download_workout(workout_id)
            if not workout_data:
                return f"No workout data found for workout with ID {workout_id}."

            # Return information about the download
            data_size = len(workout_data) if isinstance(workout_data, (bytes, bytearray)) else 0
            return json.dumps({
                "workout_id": workout_id,
                "format": "FIT",
                "size_bytes": data_size,
                "message": "Workout data is available in FIT format. Use Garmin Connect API to save to file."
            }, indent=2)
        except Exception as e:
            return f"Error downloading workout: {str(e)}"

    @app.tool()
    async def upload_workout(workout_data: dict) -> str:
        """Upload a workout from JSON data

        Creates a new workout in Garmin Connect from structured workout data.

        Args:
            workout_data: Dictionary containing workout structure (name, sport type, segments, etc.)
        """
        try:
            workout_json = json.dumps(workout_data)
            result = garmin_client.upload_workout(workout_json)

            # Curate the response
            if isinstance(result, dict):
                curated = {
                    "workout_id": result.get('workoutId'),
                    "name": result.get('workoutName'),
                    "status": "uploaded",
                }
                # Remove None values
                curated = {k: v for k, v in curated.items() if v is not None}
                return json.dumps(curated, indent=2)

            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error uploading workout: {str(e)}"

    @app.tool()
    async def upload_activity(file_path: str) -> str:
        """Upload an activity from a file

        Note: File upload operations are not supported in the MCP server implementation.
        Use the Garmin Connect web interface or mobile app to upload activity files.

        Args:
            file_path: Path to the activity file (.fit, .gpx, .tcx)
        """
        try:
            return json.dumps({
                "status": "not_supported",
                "message": "Activity upload from file path is not supported in this MCP server implementation.",
                "file_path": file_path,
                "alternatives": [
                    "Use Garmin Connect web interface",
                    "Use Garmin Connect mobile app",
                    "Use garminconnect Python library directly"
                ]
            }, indent=2)
        except Exception as e:
            return f"Error uploading activity: {str(e)}"

    @app.tool()
    async def get_scheduled_workouts(start_date: str, end_date: str) -> str:
        """Get scheduled workouts between two dates with curated summary list

        Returns workouts that have been scheduled on the Garmin Connect calendar,
        including their scheduled dates and completion status.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        try:
            # Query for scheduled workouts using GraphQL
            query = {
                "query": f'query{{workoutScheduleSummariesScalar(startDate:"{start_date}", endDate:"{end_date}")}}'
            }
            result = garmin_client.query_garmin_graphql(query)

            if not result or "data" not in result:
                return "No scheduled workouts found or error querying data."

            scheduled = result.get("data", {}).get("workoutScheduleSummariesScalar", [])

            if not scheduled:
                return f"No workouts scheduled between {start_date} and {end_date}."

            # Curate the scheduled workout list
            curated = {
                "count": len(scheduled),
                "date_range": {"start": start_date, "end": end_date},
                "scheduled_workouts": [_curate_scheduled_workout(s) for s in scheduled]
            }

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving scheduled workouts: {str(e)}"

    @app.tool()
    async def get_training_plan_workouts(calendar_date: str) -> str:
        """Get training plan workouts for a specific date

        Returns workouts from your active training plan scheduled for the given date.

        Args:
            calendar_date: Date in YYYY-MM-DD format
        """
        try:
            # Query for training plan workouts using GraphQL
            query = {
                "query": f'query{{trainingPlanScalar(calendarDate:"{calendar_date}", lang:"en-US", firstDayOfWeek:"monday")}}'
            }
            result = garmin_client.query_garmin_graphql(query)

            if not result or "data" not in result:
                return "No training plan data found or error querying data."

            plan_data = result.get("data", {}).get("trainingPlanScalar", {})
            workouts = plan_data.get("trainingPlanWorkoutScheduleDTOS", [])

            if not workouts:
                return f"No training plan workouts scheduled for {calendar_date}."

            # Curate training plan data
            curated = {
                "date": calendar_date,
                "plan_name": plan_data.get('trainingPlanName'),
                "count": len(workouts),
                "workouts": []
            }

            for w in workouts:
                workout = w.get('workout', {})
                sport_type = workout.get('sportType', {})

                workout_summary = {
                    "date": w.get('scheduledDate'),
                    "workout_id": workout.get('workoutId'),
                    "name": workout.get('workoutName'),
                    "sport": sport_type.get('sportTypeKey'),
                    "completed": w.get('completed', False),
                }

                if workout.get('estimatedDuration'):
                    workout_summary['estimated_duration_seconds'] = workout.get('estimatedDuration')

                if workout.get('estimatedDistance'):
                    workout_summary['estimated_distance_meters'] = workout.get('estimatedDistance')

                # Remove None values
                workout_summary = {k: v for k, v in workout_summary.items() if v is not None}
                curated["workouts"].append(workout_summary)

            # Remove None values from top level
            curated = {k: v for k, v in curated.items() if v is not None}

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving training plan workouts: {str(e)}"

    @app.tool()
    async def schedule_workout(workout_id: int, calendar_date: str) -> str:
        """Schedule a workout to a specific calendar date

        This adds an existing workout from your Garmin workout library
        to your Garmin Connect calendar on the specified date.

        Args:
            workout_id: ID of the workout to schedule (get IDs from get_workouts)
            calendar_date: Date to schedule the workout in YYYY-MM-DD format
        """
        try:
            url = f"workout-service/schedule/{workout_id}"
            response = garmin_client.garth.post("connectapi", url, json={"date": calendar_date})

            if response.status_code == 200:
                return json.dumps({
                    "status": "success",
                    "workout_id": workout_id,
                    "scheduled_date": calendar_date,
                    "message": f"Successfully scheduled workout {workout_id} for {calendar_date}"
                }, indent=2)
            else:
                return json.dumps({
                    "status": "failed",
                    "workout_id": workout_id,
                    "scheduled_date": calendar_date,
                    "http_status": response.status_code,
                    "message": f"Failed to schedule workout: HTTP {response.status_code}"
                }, indent=2)
        except Exception as e:
            return f"Error scheduling workout: {str(e)}"

    @app.tool()
    async def get_fbt_adaptive_workout_details(workout_uuid: str) -> str:
        """Get detailed structure of an FBT adaptive coaching workout

        Returns complete workout details including intervals, pace/HR zones,
        and step-by-step instructions for workouts from adaptive training plans.

        Args:
            workout_uuid: UUID of the workout (from training plan)
        """
        try:
            workout = garmin_client.get_fbt_adaptive_workout(workout_uuid)
            if not workout:
                return f"No workout found with UUID {workout_uuid}"

            # Curate to essential fields
            curated = {
                "workout_uuid": workout.get('workoutUuid'),
                "workout_name": workout.get('workoutName'),
                "description": workout.get('description'),
                "sport_type": workout.get('sportType', {}).get('sportTypeKey'),
                "estimated_duration_seconds": workout.get('estimatedDurationInSecs'),
                "estimated_distance_meters": workout.get('estimatedDistanceInMeters'),
                "training_effect_label": workout.get('trainingEffectLabel'),
                "estimated_aerobic_effect": workout.get('estimatedTrainingEffect'),
                "estimated_anaerobic_effect": workout.get('estimatedAnaerobicTrainingEffect'),
                "workout_phrase": workout.get('workoutPhrase'),
                "priority_type": workout.get('priorityType'),
                "steps": []
            }

            # Parse workout steps
            segments = workout.get('workoutSegments', [])
            for segment in segments:
                steps = segment.get('workoutSteps', [])
                for step in steps:
                    step_data = _parse_workout_step(step)
                    if step_data:
                        curated['steps'].append(step_data)

            # Remove None values
            curated = {k: v for k, v in curated.items() if v is not None}

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving workout details: {str(e)}"

    @app.tool()
    async def get_adaptive_training_plan_full(plan_id: int) -> str:
        """Get complete adaptive training plan with phases and all workouts

        Returns full training plan details including:
        - Plan information (level, dates, frequency)
        - Current training phase (BASE/BUILD/PEAK/TAPER)
        - All scheduled workouts with dates and status
        - Phase timeline

        Args:
            plan_id: ID of the training plan
        """
        try:
            plan = garmin_client.get_adaptive_training_plan_by_id(plan_id)
            if not plan:
                return f"No training plan found with ID {plan_id}"

            # Curate plan info
            curated = {
                "plan_id": plan.get('trainingPlanId'),
                "name": plan.get('name'),
                "description": plan.get('description'),
                "category": plan.get('trainingPlanCategory'),
                "level": plan.get('trainingLevel', {}).get('levelKey'),
                "training_type": plan.get('trainingType', {}).get('typeKey'),
                "version": plan.get('trainingVersion', {}).get('versionName'),
                "status": plan.get('trainingStatus', {}).get('statusKey'),
                "duration_weeks": plan.get('durationInWeeks'),
                "avg_weekly_workouts": plan.get('avgWeeklyWorkouts'),
                "start_date": plan.get('startDate'),
                "end_date": plan.get('endDate'),
            }

            # Add current phase
            phases = plan.get('adaptivePlanPhases', [])
            current_phase = next((p for p in phases if p.get('currentPhase')), None)
            if current_phase:
                curated['current_phase'] = {
                    "phase": current_phase.get('trainingPhase'),
                    "start_date": current_phase.get('startDate'),
                    "end_date": current_phase.get('endDate'),
                }

            # Add all phases timeline
            curated['phases'] = []
            for phase in phases:
                curated['phases'].append({
                    "phase": phase.get('trainingPhase'),
                    "start_date": phase.get('startDate'),
                    "end_date": phase.get('endDate'),
                    "is_current": phase.get('currentPhase', False),
                })

            # Add upcoming workouts (next 7 days)
            today = datetime.datetime.now().date()
            task_list = plan.get('taskList', [])
            curated['upcoming_workouts'] = []

            for task in task_list:
                workout = task.get('taskWorkout', {})
                if not workout:
                    continue

                cal_date_str = task.get('calendarDate')
                if not cal_date_str:
                    continue

                try:
                    cal_date = datetime.datetime.strptime(cal_date_str, '%Y-%m-%d').date()
                    if cal_date >= today:
                        curated['upcoming_workouts'].append({
                            "date": cal_date_str,
                            "workout_name": workout.get('workoutName'),
                            "workout_description": workout.get('workoutDescription'),
                            "workout_uuid": workout.get('workoutUuid'),
                            "estimated_duration_seconds": workout.get('estimatedDurationInSecs'),
                            "training_effect_label": workout.get('trainingEffectLabel'),
                            "workout_phrase": workout.get('workoutPhrase'),
                            "rest_day": workout.get('restDay', False),
                            "status": workout.get('adaptiveCoachingWorkoutStatus'),
                        })
                except ValueError:
                    continue

            # Limit to next 10 workouts
            curated['upcoming_workouts'] = curated['upcoming_workouts'][:10]

            # Remove None values
            curated = {k: v for k, v in curated.items() if v is not None}

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving training plan: {str(e)}"

    @app.tool()
    async def get_adaptive_coaching_preferences() -> str:
        """Get user's adaptive coaching preferences and settings

        Returns user settings including available training days,
        preferred long run days, and coaching plan type.
        """
        try:
            settings = garmin_client.get_adaptive_coaching_settings()
            if not settings:
                return "No coaching settings found"

            curated = {
                "available_training_days": settings.get('availableTrainingDays', []),
                "preferred_long_run_days": settings.get('preferredLongTrainingDays', []),
                "preferred_swim_days": settings.get('preferredSwimTrainingDays', []),
                "coaching_plan_type": settings.get('adaptiveCoachingPlanType'),
            }

            # Remove None/empty values
            curated = {k: v for k, v in curated.items() if v}

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving coaching settings: {str(e)}"

    @app.tool()
    async def get_workout_compliance(start_date: str, end_date: str) -> str:
        """Get activities with workout compliance tracking

        Returns activities showing which planned workouts were completed,
        including compliance scores and training effect comparisons.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        try:
            activities = garmin_client.get_activities_with_compliance(start_date, end_date)
            if not activities:
                return f"No activities found between {start_date} and {end_date}"

            curated_activities = []
            for activity in activities:
                curated = {
                    "activity_id": activity.get('activityId'),
                    "name": activity.get('name'),
                    "date": activity.get('startLocal'),
                    "activity_type": activity.get('activityType'),
                    "workout_type": activity.get('workoutType'),
                    "adaptive_coaching_status": activity.get('adaptiveCoachingWorkoutStatus'),
                    "compliance_score": activity.get('workoutComplianceScore'),
                    "duration_seconds": activity.get('duration'),
                    "distance_meters": activity.get('distance'),
                    "avg_speed_mps": activity.get('avgSpeed'),
                    "aerobic_training_effect": activity.get('aerobicTrainingEffect'),
                    "training_effect_label": activity.get('trainingEffectLabel'),
                    "workout_uuid": activity.get('workoutUuid'),
                    "calendar_event_uuid": activity.get('calendarEventUuid'),
                }

                # Remove None values
                curated = {k: v for k, v in curated.items() if v is not None}
                curated_activities.append(curated)

            return json.dumps(curated_activities, indent=2)
        except Exception as e:
            return f"Error retrieving workout compliance: {str(e)}"

    return app


def _parse_workout_step(step: dict) -> dict:
    """Helper function to parse a workout step into readable format."""
    step_type = step.get('type')

    if step_type == 'RepeatGroupDTO':
        # Handle repeat groups
        iterations = step.get('numberOfIterations')
        inner_steps = []
        for inner_step in step.get('workoutSteps', []):
            parsed = _parse_workout_step(inner_step)
            if parsed:
                inner_steps.append(parsed)

        return {
            "type": "repeat",
            "iterations": iterations,
            "steps": inner_steps
        }

    elif step_type == 'ExecutableStepDTO':
        # Handle regular steps
        step_data = {
            "type": step.get('stepType', {}).get('stepTypeKey'),
            "order": step.get('stepOrder'),
        }

        # Add duration/distance
        end_condition = step.get('endCondition', {}).get('conditionTypeKey')
        end_value = step.get('endConditionValue')

        if end_condition == 'time' and end_value:
            step_data['duration_seconds'] = end_value
        elif end_condition == 'distance' and end_value:
            step_data['distance_meters'] = end_value

        # Add target zones
        target_type = step.get('targetType', {}).get('workoutTargetTypeKey')
        if target_type == 'pace.zone':
            # Pace zones in m/s
            step_data['pace_min_mps'] = step.get('targetValueTwo')
            step_data['pace_max_mps'] = step.get('targetValueOne')
        elif target_type == 'heart.rate.zone':
            step_data['hr_min_bpm'] = step.get('targetValueTwo')
            step_data['hr_max_bpm'] = step.get('targetValueOne')

        # Remove None values
        step_data = {k: v for k, v in step_data.items() if v is not None}
        return step_data

    return None
