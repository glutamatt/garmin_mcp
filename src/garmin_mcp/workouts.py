"""
Workout-related functions for Garmin Connect MCP Server
"""
import json
import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# =============================================================================
# PYDANTIC MODELS - JSON Schema for AI agents
# =============================================================================

class SportType(BaseModel):
    """Sport type definition."""
    sportTypeId: int = Field(description="1=running, 2=cycling, 5=swimming")
    sportTypeKey: Literal["running", "cycling", "swimming", "other"] = Field(
        description="Sport type key"
    )


class StepType(BaseModel):
    """Workout step type definition."""
    stepTypeId: int = Field(
        description="1=warmup, 2=cooldown, 3=interval, 4=recovery, 5=rest, 6=repeat, 7=other"
    )
    stepTypeKey: Literal["warmup", "cooldown", "interval", "recovery", "rest", "repeat", "other"] = Field(
        description="Step type key"
    )


class EndCondition(BaseModel):
    """Step end condition (duration or distance)."""
    conditionTypeId: int = Field(
        description="1=lap.button, 2=time, 3=distance"
    )
    conditionTypeKey: Literal["lap.button", "time", "distance"] = Field(
        description="Condition type key"
    )


class TargetType(BaseModel):
    """Target type for intensity.

    Examples by type:
    - no.target: No intensity guidance
    - heart.rate.zone: Use zoneNumber 1-5 (Zone 1=easy, Zone 5=max)
    - power.zone: Use zoneNumber 1-7 for cycling power zones
    - pace.zone: Use targetValueOne/Two in m/s (INVERTED: One > Two)
    - heart.rate.bpm: Use targetValueOne/Two in BPM (unofficial, may not work)
    """
    workoutTargetTypeId: int = Field(
        description="1=no.target, 4=heart.rate.zone, 5=power.zone, 6=pace.zone, 7=heart.rate.bpm (unofficial)"
    )
    workoutTargetTypeKey: Literal[
        "no.target", "heart.rate.zone", "power.zone", "pace.zone", "heart.rate.bpm"
    ] = Field(
        description="Target type key. heart.rate.bpm is unofficial and may not work on all devices"
    )


class WorkoutStep(BaseModel):
    """A single workout step (warmup, interval, cooldown, etc.).

    TARGET TYPE EXAMPLES:
    - no.target: {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"}
    - heart.rate.zone: Use zoneNumber (1-5), e.g. zoneNumber=3 for Zone 3
    - power.zone: Use zoneNumber (1-7), e.g. zoneNumber=4 for Zone 4
    - pace.zone: INVERTED values - targetValueOne=faster (e.g. 3.33 m/s = 5:00/km),
                 targetValueTwo=slower (e.g. 2.78 m/s = 6:00/km)
    - heart.rate.bpm: targetValueOne=max BPM, targetValueTwo=min BPM (unofficial)
    """
    stepOrder: int = Field(description="Order of this step (1, 2, 3...)")
    stepType: StepType = Field(description="Type of step")
    endCondition: EndCondition = Field(description="How the step ends")
    endConditionValue: Optional[float] = Field(
        default=None,
        description="Duration in seconds (for time) or distance in meters (for distance)"
    )
    targetType: Optional[TargetType] = Field(
        default=None,
        description="Intensity target type. See class docstring for examples per type."
    )
    zoneNumber: Optional[int] = Field(
        default=None,
        description="Zone number: HR zones 1-5 (1=easy, 5=max), power zones 1-7"
    )
    targetValueOne: Optional[float] = Field(
        default=None,
        description="For pace.zone: FASTER pace in m/s (e.g. 3.33 = 5:00/km). For heart.rate.bpm: max BPM"
    )
    targetValueTwo: Optional[float] = Field(
        default=None,
        description="For pace.zone: SLOWER pace in m/s (e.g. 2.78 = 6:00/km). For heart.rate.bpm: min BPM"
    )


class RepeatGroup(BaseModel):
    """A repeat group containing multiple steps to repeat."""
    stepOrder: int = Field(description="Order of this repeat group")
    stepType: StepType = Field(
        default=StepType(stepTypeId=6, stepTypeKey="repeat"),
        description="Must be repeat type"
    )
    numberOfIterations: int = Field(description="Number of times to repeat")
    workoutSteps: List[WorkoutStep] = Field(description="Steps to repeat")


class WorkoutSegment(BaseModel):
    """A workout segment containing steps."""
    segmentOrder: int = Field(default=1, description="Segment order (usually 1)")
    sportType: SportType = Field(description="Sport type for this segment")
    workoutSteps: List[Union[WorkoutStep, RepeatGroup]] = Field(
        description="List of steps or repeat groups"
    )


class WorkoutData(BaseModel):
    """Complete workout structure for Garmin Connect.

    Example running workout with intervals:
    ```json
    {
        "workoutName": "5x400m Intervals",
        "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSteps": [
                {"stepOrder": 1, "stepType": {"stepTypeId": 1, "stepTypeKey": "warmup"},
                 "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
                 "endConditionValue": 600},
                {"stepOrder": 2, "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat"},
                 "numberOfIterations": 5,
                 "workoutSteps": [
                     {"stepOrder": 1, "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
                      "endCondition": {"conditionTypeId": 3, "conditionTypeKey": "distance"},
                      "endConditionValue": 400,
                      "targetType": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone"},
                      "zoneNumber": 4},
                     {"stepOrder": 2, "stepType": {"stepTypeId": 4, "stepTypeKey": "recovery"},
                      "endCondition": {"conditionTypeId": 3, "conditionTypeKey": "distance"},
                      "endConditionValue": 200}
                 ]},
                {"stepOrder": 3, "stepType": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
                 "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
                 "endConditionValue": 300}
            ]
        }]
    }
    ```
    """
    workoutName: str = Field(description="Name of the workout")
    description: Optional[str] = Field(default=None, description="Optional description")
    sportType: SportType = Field(description="Primary sport type")
    workoutSegments: List[WorkoutSegment] = Field(description="Workout segments containing steps")


# The garmin_client will be set by the main file
garmin_client = None


def configure(client):
    """Configure the module with the Garmin client instance"""
    global garmin_client
    garmin_client = client


def _normalize_workout_structure(workout_data: dict) -> dict:
    """Normalize workout structure to match Garmin API requirements.

    Transforms simplified workout structures (like those from AI coaches) into
    the complete structure expected by Garmin Connect API.

    Args:
        workout_data: Simplified workout structure

    Returns:
        Normalized workout structure ready for API upload
    """
    # Deep copy to avoid modifying the original
    import copy
    normalized = copy.deepcopy(workout_data)

    # Add required top-level fields with defaults
    normalized.setdefault('avgTrainingSpeed', 2.5)  # default ~4:00/km pace
    normalized.setdefault('estimatedDurationInSecs', 0)
    normalized.setdefault('estimatedDistanceInMeters', 0.0)
    normalized.setdefault('estimateType', None)

    # Add isWheelchair for running workouts
    sport_type = normalized.get('sportType', {})
    if sport_type.get('sportTypeKey') == 'running':
        normalized.setdefault('isWheelchair', False)

    # Ensure sportType has displayOrder
    if 'sportType' in normalized:
        normalized['sportType'].setdefault('displayOrder', 1)

    # Normalize workout segments and steps
    if 'workoutSegments' in normalized:
        for segment in normalized['workoutSegments']:
            # Ensure segment sportType has displayOrder
            if 'sportType' in segment:
                segment['sportType'].setdefault('displayOrder', 1)

            # Normalize all steps in the segment
            if 'workoutSteps' in segment:
                segment['workoutSteps'] = _normalize_steps(segment['workoutSteps'])

    return normalized


def _restructure_flat_repeats(steps: list) -> list:
    """Restructure flat repeat groups into nested structure.

    Coach Apex sends repeat groups in a flat structure using childStepId:
      [repeat{childStepId:3}, interval{stepId:3, childStepId:4}, recovery{stepId:4}]

    Garmin expects nested structure:
      [repeat{workoutSteps: [interval, recovery]}]

    Args:
        steps: Flat list of steps

    Returns:
        Restructured list with nested repeat groups
    """
    # Build stepId map for quick lookup
    step_map = {}
    for step in steps:
        if 'stepId' in step:
            step_map[step['stepId']] = step

    # Track which steps have been moved into repeat groups
    moved_step_ids = set()
    restructured = []

    for step in steps:
        # Skip if this step was already moved into a repeat group
        if step.get('stepId') in moved_step_ids:
            continue

        # Check if this is a repeat group without workoutSteps
        is_repeat = (step.get('stepType', {}).get('stepTypeKey') == 'repeat' or
                     step.get('numberOfIterations'))
        has_child_id = 'childStepId' in step
        has_workout_steps = 'workoutSteps' in step and step['workoutSteps']

        if is_repeat and has_child_id and not has_workout_steps:
            # This is a flat repeat that needs restructuring
            child_steps = []
            current_child_id = step.get('childStepId')

            # Follow the childStepId chain to collect all child steps
            while current_child_id and current_child_id in step_map:
                child_step = step_map[current_child_id]
                child_steps.append(child_step)
                moved_step_ids.add(current_child_id)

                # Check if this child points to another child
                next_child_id = child_step.get('childStepId')

                # Stop if next child points back (circular) or doesn't exist
                if not next_child_id or next_child_id in moved_step_ids:
                    break

                # For repeat groups: collect numberOfIterations worth of steps
                # But in practice, we collect until childStepId chain ends
                current_child_id = next_child_id

            # Add workoutSteps array to the repeat group
            step['workoutSteps'] = child_steps

        restructured.append(step)

    return restructured


def _normalize_steps(steps: list, step_id_counter: list = None) -> list:
    """Recursively normalize workout steps.

    Args:
        steps: List of workout steps
        step_id_counter: Mutable list with single int for tracking stepId across recursion

    Returns:
        Normalized steps with correct types and required fields
    """
    # Initialize step ID counter if not provided
    if step_id_counter is None:
        step_id_counter = [1]

    # First, restructure any flat repeat groups
    steps = _restructure_flat_repeats(steps)

    normalized_steps = []

    for step in steps:
        step_type_key = step.get('stepType', {}).get('stepTypeKey', '')

        # Determine correct type field
        if step_type_key == 'repeat' or step.get('numberOfIterations'):
            # This is a repeat group
            normalized_step = _normalize_repeat_group(step, step_id_counter)
        else:
            # This is an executable step
            normalized_step = _normalize_executable_step(step, step_id_counter)

        normalized_steps.append(normalized_step)

    return normalized_steps


def _normalize_repeat_group(step: dict, step_id_counter: list = None) -> dict:
    """Normalize a repeat group step."""
    if step_id_counter is None:
        step_id_counter = [1]

    normalized = step.copy()

    # Assign sequential stepId (API rejects null)
    if normalized.get('stepId') is None or not isinstance(normalized.get('stepId'), int):
        normalized['stepId'] = step_id_counter[0]
        step_id_counter[0] += 1

    # Set correct type if not already set or incorrect
    if normalized.get('type') != 'RepeatGroupDTO':
        normalized['type'] = 'RepeatGroupDTO'

    # Ensure stepType has displayOrder (only if missing)
    if 'stepType' in normalized and 'displayOrder' not in normalized['stepType']:
        normalized['stepType']['displayOrder'] = 6

    # Add required endCondition for iterations (only if missing)
    if 'endCondition' not in normalized:
        normalized['endCondition'] = {
            'conditionTypeId': 7,
            'conditionTypeKey': 'iterations',
            'displayOrder': 7,
            'displayable': False
        }

    # Set endConditionValue to number of iterations (only if missing)
    if 'numberOfIterations' in normalized and 'endConditionValue' not in normalized:
        normalized['endConditionValue'] = float(normalized['numberOfIterations'])

    # Add defaults only if missing
    normalized.setdefault('skipLastRestStep', True)
    normalized.setdefault('smartRepeat', False)

    # Recursively normalize child steps
    if 'workoutSteps' in normalized:
        normalized['workoutSteps'] = _normalize_steps(normalized['workoutSteps'], step_id_counter)

    return normalized


def _normalize_executable_step(step: dict, step_id_counter: list = None) -> dict:
    """Normalize an executable workout step."""
    if step_id_counter is None:
        step_id_counter = [1]

    normalized = step.copy()

    # Assign sequential stepId (API rejects null)
    if normalized.get('stepId') is None or not isinstance(normalized.get('stepId'), int):
        normalized['stepId'] = step_id_counter[0]
        step_id_counter[0] += 1

    # Set correct type - MUST be ExecutableStepDTO (not "WorkoutStep")
    normalized['type'] = 'ExecutableStepDTO'

    # Correct stepTypeId mapping - API requires specific IDs for each step type
    # This fixes issues where coaches send incorrect stepTypeId values
    step_type_id_map = {
        'warmup': 1,
        'cooldown': 2,
        'interval': 3,
        'recovery': 4,
        'rest': 5,
        'repeat': 6,
        'other': 7
    }

    if 'stepType' in normalized:
        step_type_key = normalized['stepType'].get('stepTypeKey', '')

        # Fix stepTypeId if it doesn't match the key
        if step_type_key in step_type_id_map:
            correct_id = step_type_id_map[step_type_key]
            if normalized['stepType'].get('stepTypeId') != correct_id:
                normalized['stepType']['stepTypeId'] = correct_id

        # Ensure displayOrder matches stepTypeId for executable steps
        if 'displayOrder' not in normalized['stepType']:
            if step_type_key in step_type_id_map:
                normalized['stepType']['displayOrder'] = step_type_id_map[step_type_key]

    # Ensure endCondition has displayOrder and displayable (only if missing)
    if 'endCondition' in normalized:
        if 'displayOrder' not in normalized['endCondition']:
            condition_key = normalized['endCondition'].get('conditionTypeKey', '')
            condition_display_map = {
                'lap.button': 1,
                'time': 2,
                'distance': 3,
                'calories': 4,
                'heart.rate': 6
            }
            if condition_key in condition_display_map:
                normalized['endCondition']['displayOrder'] = condition_display_map[condition_key]

        # displayable defaults to true for most conditions
        if 'displayable' not in normalized['endCondition']:
            normalized['endCondition']['displayable'] = True

    # Ensure targetType has displayOrder (only if missing)
    if 'targetType' in normalized and 'displayOrder' not in normalized['targetType']:
        target_key = normalized['targetType'].get('workoutTargetTypeKey', '')
        target_display_map = {
            'no.target': 1,
            'speed.zone': 2,
            'cadence': 3,
            'heart.rate.zone': 4,
            'power.zone': 5,
            'pace.zone': 6
        }
        if target_key in target_display_map:
            normalized['targetType']['displayOrder'] = target_display_map[target_key]
        else:
            normalized['targetType']['displayOrder'] = 1

    # Fix heart rate zone targeting: convert targetValueOne/Two to zoneNumber
    # Coaches often send targetValueOne=1, targetValueTwo=1 meaning "Zone 1"
    # but Garmin expects zoneNumber=1 with null targetValues
    if 'targetType' in normalized:
        target_key = normalized['targetType'].get('workoutTargetTypeKey', '')
        if target_key == 'heart.rate.zone':
            target_one = normalized.get('targetValueOne')
            target_two = normalized.get('targetValueTwo')
            # If both values are the same and between 1-5, it's a zone number
            if (target_one is not None and target_two is not None and
                target_one == target_two and 1 <= target_one <= 5):
                normalized['zoneNumber'] = int(target_one)
                normalized['targetValueOne'] = None
                normalized['targetValueTwo'] = None
        # Same fix for power zones
        elif target_key == 'power.zone':
            target_one = normalized.get('targetValueOne')
            target_two = normalized.get('targetValueTwo')
            if (target_one is not None and target_two is not None and
                target_one == target_two and 1 <= target_one <= 7):
                normalized['zoneNumber'] = int(target_one)
                normalized['targetValueOne'] = None
                normalized['targetValueTwo'] = None

    # Only add strokeType if completely missing (can be empty object {})
    if 'strokeType' not in normalized:
        normalized['strokeType'] = {}

    # Only add equipmentType if completely missing
    if 'equipmentType' not in normalized:
        normalized['equipmentType'] = {
            'equipmentTypeId': None,
            'equipmentTypeKey': None,
            'displayOrder': None
        }

    return normalized


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


def _deep_merge_workout(existing: dict, updates: dict) -> dict:
    """Deep merge user updates into existing workout, preserving Garmin metadata.

    This is needed because Garmin's update API requires the COMPLETE workout object
    including workoutId, ownerId, stepId values, author info, etc.

    Args:
        existing: Complete workout object from Garmin API
        updates: User's partial updates (may only have changed fields)

    Returns:
        Merged workout with user changes applied over existing data
    """
    import copy
    result = copy.deepcopy(existing)

    # Simple top-level fields to update
    for key in ['workoutName', 'description']:
        if key in updates:
            result[key] = updates[key]

    # Update sportType if provided
    if 'sportType' in updates:
        if 'sportType' not in result:
            result['sportType'] = {}
        result['sportType'].update(updates['sportType'])

    # Update workoutSegments if provided (complete replacement)
    if 'workoutSegments' in updates and updates['workoutSegments']:
        # User provided new segments - need to normalize them
        normalized_updates = _normalize_workout_structure(updates)
        result['workoutSegments'] = normalized_updates['workoutSegments']

    return result


def register_tools(app):
    """Register all workout-related tools with the MCP server app"""

    # =========================================================================
    # WORKOUT LIBRARY - CRUD operations on workouts
    # =========================================================================

    @app.tool()
    async def get_workouts() -> str:
        """List all workouts in your library.

        WHEN TO USE: Start here to see available workouts before scheduling or
        to find a workout_id for other operations.

        RETURNS: count and list of workout summaries (id, name, sport, dates).

        SEE ALSO: get_workout for full details, create_workout to add new.
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
    async def get_workout(workout_id: int) -> str:
        """Get detailed information for a specific workout.

        WHEN TO USE: After finding a workout_id from get_workouts, use this
        to see the full workout structure including segments.

        RETURNS: Workout details (id, name, sport, segments, duration, distance).

        Args:
            workout_id: ID of the workout (from get_workouts or create_workout).

        SEE ALSO: get_workouts to find workout IDs, download_workout for FIT file.
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
    async def create_workout(workout_data: WorkoutData) -> str:
        """Create a new workout in the Garmin Connect library.

        WHEN TO USE: To add a workout to the library without scheduling it.
        Use plan_workout instead if you want to create AND schedule in one step.

        RETURNS: workout_id, name, created_date, status message.

        Args:
            workout_data: Workout structure with JSON schema validation.

        SEE ALSO: plan_workout (create + schedule), schedule_workout (schedule existing),
                  update_workout (modify), delete_workout (remove).
        """
        try:
            # Convert Pydantic model to dict and normalize
            data_dict = workout_data.model_dump(exclude_none=True)
            normalized_data = _normalize_workout_structure(data_dict)

            # Upload the normalized workout
            workout_json = json.dumps(normalized_data)
            result = garmin_client.upload_workout(workout_json)

            # Curate the response
            if isinstance(result, dict):
                curated = {
                    "workout_id": result.get('workoutId'),
                    "name": result.get('workoutName'),
                    "created_date": result.get('createdDate'),
                    "status": "created",
                    "message": "Workout created. Use schedule_workout to add it to your calendar."
                }
                # Remove None values
                curated = {k: v for k, v in curated.items() if v is not None}
                return json.dumps(curated, indent=2)

            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error creating workout: {str(e)}"

    @app.tool()
    async def update_workout(workout_id: int, workout_data: WorkoutData) -> str:
        """Update an existing workout in the library.

        WHEN TO USE: To modify a workout's structure, name, or details.
        All scheduled instances will reflect the updated workout.

        NOTE: This fetches the existing workout first, merges your changes,
        and sends the complete object (required by Garmin API).

        RETURNS: workout_id, name, updated_date, status message.

        Args:
            workout_id: ID of the workout to update (from get_workouts).
            workout_data: Updated workout structure with JSON schema validation.

        SEE ALSO: get_workout to see current structure, create_workout for new workouts.
        """
        try:
            # Step 1: Fetch existing workout (Garmin API requires complete object)
            existing = garmin_client.get_workout_by_id(workout_id)
            if not existing:
                return json.dumps({
                    "status": "error",
                    "message": f"Workout {workout_id} not found"
                }, indent=2)

            # Step 2: Convert user's changes to dict
            data_dict = workout_data.model_dump(exclude_none=True)

            # Step 3: Deep merge user changes into existing workout
            merged = _deep_merge_workout(existing, data_dict)

            # Step 4: Ensure workoutId is in the body (required by API)
            merged['workoutId'] = workout_id

            # Step 5: Update via gc-api endpoint (web UI endpoint, not connectapi)
            # The library's update_workout uses connectapi which doesn't work reliably
            # Web UI uses: https://connect.garmin.com/gc-api/workout-service/workout/{id}
            url = f"/gc-api/workout-service/workout/{workout_id}"
            response = garmin_client.garth.put("connect", url, json=merged, api=True)

            # Handle response - might be empty on success
            if response.status_code in (200, 204):
                try:
                    result = response.json() if response.text else merged
                except Exception:
                    result = merged

                curated = {
                    "status": "updated",
                    "workout_id": result.get('workoutId', workout_id),
                    "workout_name": result.get('workoutName', merged.get('workoutName')),
                    "updated_date": result.get('updatedDate'),
                    "message": f"Workout '{merged.get('workoutName')}' updated"
                }
                curated = {k: v for k, v in curated.items() if v is not None}
                return json.dumps(curated, indent=2)
            else:
                return json.dumps({
                    "status": "error",
                    "message": f"Update failed with status {response.status_code}: {response.text}"
                }, indent=2)

        except Exception as e:
            return f"Error updating workout: {str(e)}"

    @app.tool()
    async def delete_workout(workout_id: int) -> str:
        """Delete a workout from the library.

        WHEN TO USE: To permanently remove a workout. WARNING: This also removes
        any scheduled calendar entries for this workout (cascade delete).

        RETURNS: workout_id, status, confirmation message.

        Args:
            workout_id: ID of the workout to delete (from get_workouts).

        SEE ALSO: unschedule_workout to remove from calendar without deleting.
        """
        try:
            success = garmin_client.delete_workout(workout_id)

            if success:
                return json.dumps({
                    "status": "deleted",
                    "workout_id": workout_id,
                    "message": f"Workout {workout_id} deleted from library"
                }, indent=2)
            else:
                return json.dumps({
                    "status": "failed",
                    "workout_id": workout_id,
                    "message": "Failed to delete workout"
                }, indent=2)

        except Exception as e:
            return f"Error deleting workout: {str(e)}"

    @app.tool()
    async def download_workout(workout_id: int) -> str:
        """Download a workout as a FIT file.

        WHEN TO USE: To export a workout for use on a Garmin device or other app.
        Note: Binary data cannot be returned directly through MCP.

        RETURNS: workout_id, format (FIT), size_bytes, availability message.

        Args:
            workout_id: ID of the workout to download (from get_workouts).

        SEE ALSO: get_workout for viewing workout details.
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

    # =========================================================================
    # SCHEDULING - Calendar scheduling operations
    # =========================================================================

    @app.tool()
    async def plan_workout(workout_data: WorkoutData, date: str) -> str:
        """Create and schedule a workout in one step (RECOMMENDED).

        WHEN TO USE: Primary tool for coaching. Creates a workout in the library
        and schedules it to the calendar in one operation. Use this instead of
        separate create_workout + schedule_workout calls.

        RETURNS: workout_id, schedule_id, calendar_date, status message.

        Args:
            workout_data: Workout structure with JSON schema validation. See WorkoutData model.
            date: Schedule date in YYYY-MM-DD format.

        SEE ALSO: get_readiness (check before planning), get_calendar (view schedule),
                  reschedule_workout (move date), unschedule_workout (cancel).
        """
        try:
            # Convert Pydantic model to dict and normalize
            data_dict = workout_data.model_dump(exclude_none=True)
            normalized_data = _normalize_workout_structure(data_dict)

            # Step 1: Create the workout
            workout_json = json.dumps(normalized_data)
            upload_result = garmin_client.upload_workout(workout_json)
            workout_id = upload_result.get('workoutId')

            if not workout_id:
                return json.dumps({
                    "status": "error",
                    "message": "Failed to create workout - no workout ID returned"
                }, indent=2)

            # Step 2: Schedule the workout
            schedule_result = garmin_client.schedule_workout(workout_id, date)

            # Return combined result
            curated = {
                "status": "planned",
                "workout_id": workout_id,
                "workout_name": upload_result.get('workoutName'),
                "schedule_id": schedule_result.get('workoutScheduleId'),
                "calendar_date": schedule_result.get('calendarDate'),
                "estimated_duration_seconds": upload_result.get('estimatedDurationInSecs'),
                "message": f"Workout '{upload_result.get('workoutName')}' created and scheduled for {date}"
            }
            curated = {k: v for k, v in curated.items() if v is not None}
            return json.dumps(curated, indent=2)

        except Exception as e:
            return f"Error planning workout: {str(e)}"

    @app.tool()
    async def schedule_workout(workout_id: int, date: str) -> str:
        """Schedule an existing workout for a specific date.

        WHEN TO USE: To add a workout from your library to the calendar.
        The workout must already exist (from create_workout or get_workouts).
        Use plan_workout instead to create and schedule in one step.

        RETURNS: schedule_id, workout_id, workout_name, calendar_date, status.

        Args:
            workout_id: ID of the workout to schedule (from get_workouts or create_workout).
            date: Schedule date in YYYY-MM-DD format.

        SEE ALSO: plan_workout (create + schedule), get_workouts (find workout_id),
                  reschedule_workout (move date), unschedule_workout (cancel).
        """
        try:
            result = garmin_client.schedule_workout(workout_id, date)

            # Curate the response
            if isinstance(result, dict):
                curated = {
                    "workout_schedule_id": result.get('workoutScheduleId'),
                    "workout_id": result.get('workout', {}).get('workoutId'),
                    "workout_name": result.get('workout', {}).get('workoutName'),
                    "calendar_date": result.get('calendarDate'),
                    "created_date": result.get('createdDate'),
                    "status": "scheduled"
                }
                # Remove None values
                curated = {k: v for k, v in curated.items() if v is not None}
                return json.dumps(curated, indent=2)

            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error scheduling workout: {str(e)}"

    @app.tool()
    async def reschedule_workout(schedule_id: int, new_date: str) -> str:
        """Move a scheduled workout to a different date.

        WHEN TO USE: When an athlete needs to adjust their training schedule
        by moving a workout to a new date.

        RETURNS: schedule_id, new_date, workout_name, status message.

        Args:
            schedule_id: The schedule ID (from get_calendar or plan_workout).
            new_date: New date in YYYY-MM-DD format.

        SEE ALSO: get_calendar (find schedule_id), unschedule_workout (cancel instead).
        """
        try:
            result = garmin_client.reschedule_workout(schedule_id, new_date)

            curated = {
                "status": "rescheduled",
                "schedule_id": schedule_id,
                "new_date": new_date,
                "workout_name": result.get('workout', {}).get('workoutName'),
                "message": f"Workout rescheduled to {new_date}"
            }
            curated = {k: v for k, v in curated.items() if v is not None}
            return json.dumps(curated, indent=2)

        except Exception as e:
            return f"Error rescheduling workout: {str(e)}"

    @app.tool()
    async def unschedule_workout(schedule_id: int) -> str:
        """Remove a scheduled workout from the calendar.

        WHEN TO USE: When an athlete needs to skip a planned workout.
        The workout remains in the library; only the calendar entry is removed.

        RETURNS: schedule_id, status, confirmation message.

        Args:
            schedule_id: The schedule ID (from get_calendar or plan_workout).

        SEE ALSO: delete_workout (remove from library entirely),
                  reschedule_workout (move to different date instead).
        """
        try:
            success = garmin_client.unschedule_workout(schedule_id)

            if success:
                return json.dumps({
                    "status": "unscheduled",
                    "schedule_id": schedule_id,
                    "message": f"Workout schedule {schedule_id} removed from calendar"
                }, indent=2)
            else:
                return json.dumps({
                    "status": "failed",
                    "schedule_id": schedule_id,
                    "message": "Failed to unschedule workout"
                }, indent=2)

        except Exception as e:
            return f"Error unscheduling workout: {str(e)}"

    @app.tool()
    async def get_scheduled_workouts(start_date: str, end_date: str) -> str:
        """Get scheduled workouts between two dates.

        WHEN TO USE: To see what workouts are scheduled in a date range.
        For a comprehensive calendar view including events and activities,
        use get_calendar instead.

        RETURNS: count, date_range, list of scheduled workouts (date, id, name, sport, completed).

        Args:
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.

        SEE ALSO: get_calendar (full calendar view), get_compliance (workout completion tracking).
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
    async def get_calendar(start_date: str, end_date: str) -> str:
        """Get comprehensive training calendar view (RECOMMENDED for overview).

        WHEN TO USE: Primary tool for understanding an athlete's schedule.
        Shows scheduled workouts, training plan items, events, and completed activities.

        RETURNS: date_range, total_days, calendar (list of days with items).

        Args:
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.

        SEE ALSO: get_scheduled_workouts (workouts only), get_training_plan (plan details),
                  plan_workout (add to calendar).
        """
        try:
            # Get scheduled workouts via GraphQL
            scheduled = garmin_client.get_scheduled_workouts_for_range(start_date, end_date)

            # Get calendar items (includes events, training plan workouts)
            calendar_items = garmin_client.get_calendar_items_for_range(start_date, end_date)

            # Organize by date
            by_date = {}

            # Process scheduled workouts
            for workout in scheduled:
                date = workout.get('scheduleDate')
                if date not in by_date:
                    by_date[date] = {"date": date, "items": []}

                by_date[date]["items"].append({
                    "type": "scheduled_workout",
                    "schedule_id": workout.get('scheduledWorkoutId'),
                    "workout_id": workout.get('workoutId'),
                    "workout_uuid": workout.get('workoutUuid'),
                    "name": workout.get('workoutName'),
                    "sport": workout.get('workoutType'),
                    "duration_seconds": workout.get('estimatedDurationInSecs'),
                    "training_plan": workout.get('tpPlanName'),
                    "is_rest_day": workout.get('isRestDay'),
                })

            # Process calendar items (events, training plan items)
            for item in calendar_items:
                date = item.get('date')
                item_type = item.get('itemType')

                # Skip if already have this from scheduled workouts
                if item_type == 'workout':
                    continue

                if date not in by_date:
                    by_date[date] = {"date": date, "items": []}

                if item_type == 'event':
                    by_date[date]["items"].append({
                        "type": "event",
                        "name": item.get('title'),
                        "is_race": item.get('isRace'),
                        "location": item.get('location'),
                    })
                elif item_type == 'activity':
                    by_date[date]["items"].append({
                        "type": "completed_activity",
                        "name": item.get('title'),
                        "sport": item.get('sportTypeKey'),
                        "duration_seconds": item.get('duration'),
                        "distance_meters": item.get('distance'),
                    })

            # Sort by date and convert to list
            result = {
                "date_range": {"start": start_date, "end": end_date},
                "total_days": len(by_date),
                "calendar": sorted(by_date.values(), key=lambda x: x["date"])
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error getting training calendar: {str(e)}"

    # =========================================================================
    # TRAINING PLANS - Adaptive coaching & plans
    # =========================================================================

    @app.tool()
    async def get_training_plan(calendar_date: str) -> str:
        """Get training plan workouts for a specific date.

        WHEN TO USE: To see workouts from an active Garmin training plan
        (e.g., 5K, 10K, marathon plans) scheduled for a given date.

        RETURNS: date, plan_name, count, list of workouts (date, id, name, sport, completed).

        Args:
            calendar_date: Date in YYYY-MM-DD format.

        SEE ALSO: get_adaptive_plan (full plan details), get_calendar (all calendar items).
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
    async def get_adaptive_plan(plan_id: int) -> str:
        """Get complete adaptive training plan with phases and workouts.

        WHEN TO USE: To see full details of a Garmin adaptive training plan
        including phases (BASE/BUILD/PEAK/TAPER), schedule, and upcoming workouts.

        RETURNS: plan info (id, name, level, dates), current_phase, phases list,
                 upcoming_workouts (next 10).

        Args:
            plan_id: ID of the training plan.

        SEE ALSO: get_training_plan (daily view), get_adaptive_workout (workout details),
                  get_coaching_preferences (user settings).
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
    async def get_adaptive_workout(workout_uuid: str) -> str:
        """Get detailed structure of an adaptive coaching workout.

        WHEN TO USE: To see the full step-by-step breakdown of a workout from
        an adaptive training plan, including intervals, zones, and instructions.

        RETURNS: workout details (uuid, name, sport, duration, training_effect),
                 steps (type, duration/distance, pace/HR targets).

        Args:
            workout_uuid: UUID of the workout (from get_adaptive_plan or get_training_plan).

        SEE ALSO: get_adaptive_plan (plan overview), get_workout (library workouts).
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
    async def get_coaching_preferences() -> str:
        """Get user's adaptive coaching preferences and settings.

        WHEN TO USE: To understand an athlete's preferred training days and
        coaching settings before planning workouts.

        RETURNS: available_training_days, preferred_long_run_days, preferred_swim_days,
                 coaching_plan_type.

        SEE ALSO: get_readiness (current recovery state), get_adaptive_plan (active plan).
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

    # =========================================================================
    # ANALYTICS - Readiness, compliance, summaries
    # =========================================================================

    @app.tool()
    async def get_readiness() -> str:
        """Get current training readiness and recovery status (RECOMMENDED before planning).

        WHEN TO USE: Check this BEFORE planning workouts to ensure appropriate
        intensity based on athlete's recovery state.

        RETURNS: date, training_readiness (score, level, feedback), training_status
                 (status, load, vo2max), hrv (value, status, baseline),
                 sleep (score, duration, quality), recommendations.

        SEE ALSO: plan_workout (schedule based on readiness), get_weekly_summary (recent load).
        """
        try:
            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')

            # Get training readiness
            try:
                readiness = garmin_client.get_training_readiness(today)
            except Exception:
                readiness = None

            # Get training status
            try:
                status = garmin_client.get_training_status(today)
            except Exception:
                status = None

            # Get HRV
            try:
                hrv = garmin_client.get_hrv_data(today)
            except Exception:
                hrv = None

            # Get sleep
            try:
                sleep = garmin_client.get_sleep_data(today)
            except Exception:
                sleep = None

            curated = {
                "date": today,
                "training_readiness": None,
                "training_status": None,
                "hrv": None,
                "sleep": None,
                "recommendations": []
            }

            # Process readiness
            if readiness:
                curated["training_readiness"] = {
                    "score": readiness.get('score') or readiness.get('trainingReadinessScore'),
                    "level": readiness.get('level') or readiness.get('trainingReadinessLevel'),
                    "feedback": readiness.get('feedbackPhrase'),
                }

            # Process training status
            if status:
                curated["training_status"] = {
                    "status": status.get('trainingStatus') or status.get('status'),
                    "load_7day": status.get('weeklyTrainingLoad'),
                    "load_28day": status.get('monthlyTrainingLoad'),
                    "vo2max": status.get('vo2Max'),
                }

            # Process HRV
            if hrv:
                hrv_value = hrv.get('hrvValue') or hrv.get('lastNightAvg')
                if hrv_value:
                    curated["hrv"] = {
                        "value": hrv_value,
                        "status": hrv.get('status') or hrv.get('hrvStatus'),
                        "baseline": hrv.get('baseline') or hrv.get('weeklyAvg'),
                    }

            # Process sleep
            if sleep:
                curated["sleep"] = {
                    "score": sleep.get('overallScore') or sleep.get('sleepScores', {}).get('overall'),
                    "duration_seconds": sleep.get('sleepTimeSeconds'),
                    "quality": sleep.get('sleepQualityType'),
                }

            # Generate recommendations
            readiness_score = curated.get("training_readiness", {}).get("score")
            if readiness_score:
                if readiness_score >= 70:
                    curated["recommendations"].append("Good readiness - suitable for high intensity")
                elif readiness_score >= 50:
                    curated["recommendations"].append("Moderate readiness - consider moderate intensity")
                else:
                    curated["recommendations"].append("Low readiness - recommend easy/recovery workout or rest")

            # Remove None values
            curated = {k: v for k, v in curated.items() if v is not None}
            return json.dumps(curated, indent=2)

        except Exception as e:
            return f"Error getting athlete readiness: {str(e)}"

    @app.tool()
    async def get_compliance(start_date: str, end_date: str) -> str:
        """Get activities with workout compliance tracking.

        WHEN TO USE: To see which planned workouts were completed and how well
        the athlete followed the prescribed training.

        RETURNS: List of activities with compliance_score, workout_type,
                 adaptive_coaching_status, training_effect.

        Args:
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.

        SEE ALSO: get_weekly_summary (aggregated stats), get_calendar (planned vs actual).
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

    @app.tool()
    async def get_weekly_summary(week_end_date: str = None) -> str:
        """Get summary of training for a week (RECOMMENDED for weekly review).

        WHEN TO USE: For weekly coaching reviews to see training load,
        workout compliance, and activity breakdown.

        RETURNS: week dates, workouts (planned, completed, compliance_rate),
                 totals (activities, duration, distance), by_activity_type breakdown,
                 training_load.

        Args:
            week_end_date: End date of the week in YYYY-MM-DD format (default: today).

        SEE ALSO: get_compliance (detailed activity list), get_readiness (current state),
                  get_calendar (day-by-day view).
        """
        try:
            from datetime import datetime, timedelta

            if week_end_date:
                end_dt = datetime.strptime(week_end_date, '%Y-%m-%d')
            else:
                end_dt = datetime.now()

            start_dt = end_dt - timedelta(days=6)
            start_date = start_dt.strftime('%Y-%m-%d')
            end_date = end_dt.strftime('%Y-%m-%d')

            # Get scheduled workouts
            scheduled = garmin_client.get_scheduled_workouts_for_range(start_date, end_date)

            # Get activities with compliance
            try:
                activities = garmin_client.get_activities_with_compliance(start_date, end_date)
            except Exception:
                activities = []

            # Get weekly training load
            try:
                load = garmin_client.get_weekly_training_load(end_date, weeks=1)
            except Exception:
                load = None

            # Calculate stats
            planned_count = len(scheduled)
            completed_count = len([a for a in activities if a.get('adaptiveCoachingWorkoutStatus') == 'COMPLETED'])

            total_duration = sum(a.get('duration', 0) or 0 for a in activities)
            total_distance = sum(a.get('distance', 0) or 0 for a in activities)

            # Group activities by type
            by_type = {}
            for a in activities:
                atype = a.get('activityType') or 'other'
                if atype not in by_type:
                    by_type[atype] = {"count": 0, "duration_seconds": 0, "distance_meters": 0}
                by_type[atype]["count"] += 1
                by_type[atype]["duration_seconds"] += a.get('duration', 0) or 0
                by_type[atype]["distance_meters"] += a.get('distance', 0) or 0

            summary = {
                "week": {"start": start_date, "end": end_date},
                "workouts": {
                    "planned": planned_count,
                    "completed": completed_count,
                    "compliance_rate": round(completed_count / planned_count * 100, 1) if planned_count > 0 else None
                },
                "totals": {
                    "activities": len(activities),
                    "duration_seconds": total_duration,
                    "duration_hours": round(total_duration / 3600, 1),
                    "distance_meters": total_distance,
                    "distance_km": round(total_distance / 1000, 1)
                },
                "by_activity_type": by_type
            }

            if load:
                summary["training_load"] = {
                    "weekly_load": load.get('weeklyTrainingLoad'),
                    "load_status": load.get('loadStatus'),
                }

            # Remove None values recursively
            def clean_nones(d):
                if isinstance(d, dict):
                    return {k: clean_nones(v) for k, v in d.items() if v is not None}
                return d

            return json.dumps(clean_nones(summary), indent=2)

        except Exception as e:
            return f"Error getting weekly summary: {str(e)}"

    return app
