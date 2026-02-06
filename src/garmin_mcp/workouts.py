"""
Workout-related functions for Garmin Connect MCP Server
"""
import copy
import json
import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, Field

# The garmin_client will be set by the main file
garmin_client = None


def configure(client):
    """Configure the module with the Garmin client instance"""
    global garmin_client
    garmin_client = client


# =============================================================================
# PYDANTIC MODELS - JSON Schema for AI agents
# =============================================================================

class SportType(BaseModel):
    """Sport type definition."""
    sportTypeId: int = Field(description="1=running, 2=cycling, 5=swimming")
    sportTypeKey: str = Field(description="Sport type key: running, cycling, swimming, other")


class StepType(BaseModel):
    """Workout step type definition."""
    stepTypeId: int = Field(
        description="1=warmup, 2=cooldown, 3=interval, 4=recovery, 5=rest, 6=repeat, 7=other"
    )
    stepTypeKey: str = Field(description="Step type key: warmup, cooldown, interval, recovery, rest, repeat, other")


class EndCondition(BaseModel):
    """Step end condition (duration or distance)."""
    conditionTypeId: int = Field(description="1=lap.button, 2=time, 3=distance")
    conditionTypeKey: str = Field(description="Condition type key: lap.button, time, distance")


class TargetType(BaseModel):
    """Target type for intensity."""
    workoutTargetTypeId: int = Field(
        description="1=no.target, 4=heart.rate.zone, 5=power.zone, 6=pace.zone"
    )
    workoutTargetTypeKey: str = Field(
        description="Target type key: no.target, heart.rate.zone, power.zone, pace.zone"
    )


class WorkoutStep(BaseModel):
    """A single workout step (warmup, interval, cooldown, etc.)."""
    stepOrder: int = Field(description="Order of this step (1, 2, 3...)")
    stepType: StepType = Field(description="Type of step")
    endCondition: EndCondition = Field(description="How the step ends")
    endConditionValue: Optional[float] = Field(
        default=None,
        description="Duration in seconds (for time) or distance in meters (for distance)"
    )
    targetType: Optional[TargetType] = Field(default=None, description="Intensity target type")
    zoneNumber: Optional[int] = Field(default=None, description="Zone number: HR zones 1-5, power zones 1-7")
    targetValueOne: Optional[float] = Field(default=None, description="For pace.zone: FASTER pace in m/s")
    targetValueTwo: Optional[float] = Field(default=None, description="For pace.zone: SLOWER pace in m/s")


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
    workoutSteps: List[Union[WorkoutStep, RepeatGroup]] = Field(description="List of steps or repeat groups")


class WorkoutData(BaseModel):
    """Complete workout structure for Garmin Connect."""
    workoutName: str = Field(description="Name of the workout")
    description: Optional[str] = Field(default=None, description="Optional description")
    sportType: SportType = Field(description="Primary sport type")
    workoutSegments: List[WorkoutSegment] = Field(description="Workout segments containing steps")


# =============================================================================
# PREPROCESSING - Convert simplified AI output to full Garmin format
# =============================================================================

SPORT_TYPE_MAP = {
    'running': {'sportTypeId': 1, 'sportTypeKey': 'running'},
    'cycling': {'sportTypeId': 2, 'sportTypeKey': 'cycling'},
    'swimming': {'sportTypeId': 5, 'sportTypeKey': 'swimming'},
    'other': {'sportTypeId': 99, 'sportTypeKey': 'other'},
}

STEP_TYPE_MAP = {
    'warmup': {'stepTypeId': 1, 'stepTypeKey': 'warmup'},
    'cooldown': {'stepTypeId': 2, 'stepTypeKey': 'cooldown'},
    'interval': {'stepTypeId': 3, 'stepTypeKey': 'interval'},
    'recovery': {'stepTypeId': 4, 'stepTypeKey': 'recovery'},
    'rest': {'stepTypeId': 5, 'stepTypeKey': 'rest'},
    'repeat': {'stepTypeId': 6, 'stepTypeKey': 'repeat'},
    'other': {'stepTypeId': 7, 'stepTypeKey': 'other'},
}

CONDITION_TYPE_MAP = {
    'lap.button': {'conditionTypeId': 1, 'conditionTypeKey': 'lap.button'},
    'time': {'conditionTypeId': 2, 'conditionTypeKey': 'time'},
    'distance': {'conditionTypeId': 3, 'conditionTypeKey': 'distance'},
}

TARGET_TYPE_MAP = {
    'no.target': {'workoutTargetTypeId': 1, 'workoutTargetTypeKey': 'no.target'},
    'heart.rate.zone': {'workoutTargetTypeId': 4, 'workoutTargetTypeKey': 'heart.rate.zone'},
    'power.zone': {'workoutTargetTypeId': 5, 'workoutTargetTypeKey': 'power.zone'},
    'pace.zone': {'workoutTargetTypeId': 6, 'workoutTargetTypeKey': 'pace.zone'},
}


def _preprocess_sport_type(value) -> dict:
    """Convert string or dict sport type to full format."""
    if isinstance(value, str):
        return SPORT_TYPE_MAP.get(value, SPORT_TYPE_MAP['other']).copy()
    if isinstance(value, dict) and 'sportTypeId' in value:
        return value
    if isinstance(value, dict) and 'sportTypeKey' in value:
        return SPORT_TYPE_MAP.get(value['sportTypeKey'], SPORT_TYPE_MAP['other']).copy()
    return SPORT_TYPE_MAP['other'].copy()


def _preprocess_step(step: dict) -> dict:
    """Convert a simplified step to the full Garmin format."""
    result = {}

    result['stepOrder'] = step.get('stepOrder', 1)

    # stepType: string -> {stepTypeId, stepTypeKey}
    st = step.get('stepType', 'interval')
    if isinstance(st, str):
        result['stepType'] = STEP_TYPE_MAP.get(st, STEP_TYPE_MAP['other']).copy()
    else:
        result['stepType'] = st

    # endCondition: string -> {conditionTypeId, conditionTypeKey}
    ec = step.get('endCondition', step.get('endConditionType'))
    if isinstance(ec, str):
        result['endCondition'] = CONDITION_TYPE_MAP.get(ec, CONDITION_TYPE_MAP['lap.button']).copy()
    elif isinstance(ec, dict):
        result['endCondition'] = ec
    else:
        result['endCondition'] = CONDITION_TYPE_MAP['lap.button'].copy()

    if 'endConditionValue' in step and step['endConditionValue'] is not None:
        result['endConditionValue'] = step['endConditionValue']

    # targetType: string -> {workoutTargetTypeId, workoutTargetTypeKey}
    tt = step.get('targetType')
    if isinstance(tt, str):
        result['targetType'] = TARGET_TYPE_MAP.get(tt, TARGET_TYPE_MAP['no.target']).copy()
    elif isinstance(tt, dict) and 'workoutTargetTypeId' in tt:
        result['targetType'] = tt

    # Target values: handle both naming conventions
    for src, dst in [
        ('targetValueOne', 'targetValueOne'),
        ('targetValueTwo', 'targetValueTwo'),
        ('targetValueHigh', 'targetValueOne'),
        ('targetValueLow', 'targetValueTwo'),
    ]:
        if src in step and step[src] is not None and dst not in result:
            result[dst] = step[src]

    if 'zoneNumber' in step:
        result['zoneNumber'] = step['zoneNumber']

    # Repeat group fields
    if 'numberOfIterations' in step:
        result['numberOfIterations'] = step['numberOfIterations']
    if 'workoutSteps' in step:
        result['workoutSteps'] = [_preprocess_step(s) for s in step['workoutSteps']]

    return result


def _preprocess_workout_input(data: dict) -> dict:
    """Convert simplified AI-generated workout format to full Garmin-compatible format.

    Handles conversions like:
      - sport: "running" -> sportType: {sportTypeId: 1, sportTypeKey: "running"}
      - steps: [...] -> workoutSegments: [{workoutSteps: [...]}]
      - stepType: "interval" -> stepType: {stepTypeId: 3, stepTypeKey: "interval"}
      - endCondition: "time" -> endCondition: {conditionTypeId: 2, conditionTypeKey: "time"}
      - targetType: "heart.rate.zone" -> targetType: {workoutTargetTypeId: 4, ...}
      - targetValueHigh/targetValueLow -> targetValueOne/targetValueTwo
    """
    # Already in full format - has workoutSegments with proper structure
    if 'workoutSegments' in data and isinstance(data.get('sportType'), dict):
        steps_ok = True
        for seg in data['workoutSegments']:
            for step in seg.get('workoutSteps', []):
                if isinstance(step.get('stepType'), str):
                    steps_ok = False
                    break
        if steps_ok:
            return data

    result = {'workoutName': data.get('workoutName', 'Workout')}

    if 'description' in data:
        result['description'] = data['description']

    # Sport type
    sport = data.get('sportType') or data.get('sport', 'running')
    result['sportType'] = _preprocess_sport_type(sport)

    # Steps -> workoutSegments
    steps = data.get('steps') or data.get('workoutSteps')
    if steps:
        result['workoutSegments'] = [{
            'segmentOrder': 1,
            'sportType': result['sportType'].copy(),
            'workoutSteps': [_preprocess_step(s) for s in steps],
        }]
    elif 'workoutSegments' in data:
        # Has segments but steps inside may need preprocessing
        segments = []
        for seg in data['workoutSegments']:
            new_seg = {
                'segmentOrder': seg.get('segmentOrder', 1),
                'sportType': _preprocess_sport_type(seg.get('sportType', result['sportType'])),
            }
            raw_steps = seg.get('workoutSteps', [])
            new_seg['workoutSteps'] = [_preprocess_step(s) for s in raw_steps]
            segments.append(new_seg)
        result['workoutSegments'] = segments
    else:
        result['workoutSegments'] = [{
            'segmentOrder': 1,
            'sportType': result['sportType'].copy(),
            'workoutSteps': [],
        }]

    return result


# =============================================================================
# NORMALIZATION FUNCTIONS
# =============================================================================

def _normalize_workout_structure(workout_data: dict) -> dict:
    """Normalize workout structure to match Garmin API requirements."""
    normalized = copy.deepcopy(workout_data)

    normalized.setdefault('avgTrainingSpeed', 2.5)
    normalized.setdefault('estimatedDurationInSecs', 0)
    normalized.setdefault('estimatedDistanceInMeters', 0.0)
    normalized.setdefault('estimateType', None)

    sport_type = normalized.get('sportType', {})
    if sport_type.get('sportTypeKey') == 'running':
        normalized.setdefault('isWheelchair', False)

    if 'sportType' in normalized:
        normalized['sportType'].setdefault('displayOrder', 1)

    if 'workoutSegments' in normalized:
        for segment in normalized['workoutSegments']:
            if 'sportType' in segment:
                segment['sportType'].setdefault('displayOrder', 1)
            if 'workoutSteps' in segment:
                segment['workoutSteps'] = _normalize_steps(segment['workoutSteps'])

    return normalized


def _restructure_flat_repeats(steps: list) -> list:
    """Restructure flat repeat groups into nested structure."""
    step_map = {}
    for step in steps:
        if 'stepId' in step:
            step_map[step['stepId']] = step

    moved_step_ids = set()
    restructured = []

    for step in steps:
        if step.get('stepId') in moved_step_ids:
            continue

        is_repeat = (step.get('stepType', {}).get('stepTypeKey') == 'repeat' or
                     step.get('numberOfIterations'))
        has_child_id = 'childStepId' in step
        has_workout_steps = 'workoutSteps' in step and step['workoutSteps']

        if is_repeat and has_child_id and not has_workout_steps:
            child_steps = []
            current_child_id = step.get('childStepId')

            while current_child_id and current_child_id in step_map:
                child_step = step_map[current_child_id]
                child_steps.append(child_step)
                moved_step_ids.add(current_child_id)
                next_child_id = child_step.get('childStepId')
                if not next_child_id or next_child_id in moved_step_ids:
                    break
                current_child_id = next_child_id

            step['workoutSteps'] = child_steps

        restructured.append(step)

    return restructured


def _normalize_steps(steps: list, step_id_counter: list = None) -> list:
    """Recursively normalize workout steps."""
    if step_id_counter is None:
        step_id_counter = [1]

    steps = _restructure_flat_repeats(steps)
    normalized_steps = []

    for step in steps:
        step_type_key = step.get('stepType', {}).get('stepTypeKey', '')
        if step_type_key == 'repeat' or step.get('numberOfIterations'):
            normalized_step = _normalize_repeat_group(step, step_id_counter)
        else:
            normalized_step = _normalize_executable_step(step, step_id_counter)
        normalized_steps.append(normalized_step)

    return normalized_steps


def _normalize_repeat_group(step: dict, step_id_counter: list = None) -> dict:
    """Normalize a repeat group step."""
    if step_id_counter is None:
        step_id_counter = [1]

    normalized = step.copy()

    if normalized.get('stepId') is None or not isinstance(normalized.get('stepId'), int):
        normalized['stepId'] = step_id_counter[0]
        step_id_counter[0] += 1

    if normalized.get('type') != 'RepeatGroupDTO':
        normalized['type'] = 'RepeatGroupDTO'

    if 'stepType' in normalized and 'displayOrder' not in normalized['stepType']:
        normalized['stepType']['displayOrder'] = 6

    if 'endCondition' not in normalized:
        normalized['endCondition'] = {
            'conditionTypeId': 7,
            'conditionTypeKey': 'iterations',
            'displayOrder': 7,
            'displayable': False
        }

    if 'numberOfIterations' in normalized and 'endConditionValue' not in normalized:
        normalized['endConditionValue'] = float(normalized['numberOfIterations'])

    normalized.setdefault('skipLastRestStep', True)
    normalized.setdefault('smartRepeat', False)

    if 'workoutSteps' in normalized:
        normalized['workoutSteps'] = _normalize_steps(normalized['workoutSteps'], step_id_counter)

    return normalized


def _normalize_executable_step(step: dict, step_id_counter: list = None) -> dict:
    """Normalize an executable workout step."""
    if step_id_counter is None:
        step_id_counter = [1]

    normalized = step.copy()

    if normalized.get('stepId') is None or not isinstance(normalized.get('stepId'), int):
        normalized['stepId'] = step_id_counter[0]
        step_id_counter[0] += 1

    normalized['type'] = 'ExecutableStepDTO'

    step_type_id_map = {
        'warmup': 1, 'cooldown': 2, 'interval': 3, 'recovery': 4,
        'rest': 5, 'repeat': 6, 'other': 7
    }

    if 'stepType' in normalized:
        step_type_key = normalized['stepType'].get('stepTypeKey', '')
        if step_type_key in step_type_id_map:
            correct_id = step_type_id_map[step_type_key]
            if normalized['stepType'].get('stepTypeId') != correct_id:
                normalized['stepType']['stepTypeId'] = correct_id
        if 'displayOrder' not in normalized['stepType']:
            if step_type_key in step_type_id_map:
                normalized['stepType']['displayOrder'] = step_type_id_map[step_type_key]

    if 'endCondition' in normalized:
        if 'displayOrder' not in normalized['endCondition']:
            condition_key = normalized['endCondition'].get('conditionTypeKey', '')
            condition_display_map = {'lap.button': 1, 'time': 2, 'distance': 3, 'calories': 4, 'heart.rate': 6}
            if condition_key in condition_display_map:
                normalized['endCondition']['displayOrder'] = condition_display_map[condition_key]
        if 'displayable' not in normalized['endCondition']:
            normalized['endCondition']['displayable'] = True

    if 'targetType' in normalized and 'displayOrder' not in normalized['targetType']:
        target_key = normalized['targetType'].get('workoutTargetTypeKey', '')
        target_display_map = {'no.target': 1, 'speed.zone': 2, 'cadence': 3, 'heart.rate.zone': 4, 'power.zone': 5, 'pace.zone': 6}
        normalized['targetType']['displayOrder'] = target_display_map.get(target_key, 1)

    if 'targetType' in normalized:
        target_key = normalized['targetType'].get('workoutTargetTypeKey', '')
        if target_key == 'heart.rate.zone':
            target_one = normalized.get('targetValueOne')
            target_two = normalized.get('targetValueTwo')
            if (target_one is not None and target_two is not None and
                target_one == target_two and 1 <= target_one <= 5):
                normalized['zoneNumber'] = int(target_one)
                normalized['targetValueOne'] = None
                normalized['targetValueTwo'] = None
        elif target_key == 'power.zone':
            target_one = normalized.get('targetValueOne')
            target_two = normalized.get('targetValueTwo')
            if (target_one is not None and target_two is not None and
                target_one == target_two and 1 <= target_one <= 7):
                normalized['zoneNumber'] = int(target_one)
                normalized['targetValueOne'] = None
                normalized['targetValueTwo'] = None

    if 'strokeType' not in normalized:
        normalized['strokeType'] = {}
    if 'equipmentType' not in normalized:
        normalized['equipmentType'] = {'equipmentTypeId': None, 'equipmentTypeKey': None, 'displayOrder': None}

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
        """Create a new workout in the Garmin Connect library.

        Accepts both simplified format (sport, steps) and full Garmin format (sportType, workoutSegments).

        Args:
            workout_data: Workout structure. Simplified example: {workoutName, sport: "running", steps: [{stepOrder, stepType: "warmup", endCondition: "time", endConditionValue: 600}, ...]}. Full format also accepted with sportType, workoutSegments, etc.
        """
        try:
            preprocessed = _preprocess_workout_input(workout_data)
            validated = WorkoutData(**preprocessed)
            data_dict = validated.model_dump(exclude_none=True)
            normalized = _normalize_workout_structure(data_dict)
            workout_json = json.dumps(normalized)
            result = garmin_client.upload_workout(workout_json)

            if isinstance(result, dict):
                curated = {
                    "workout_id": result.get('workoutId'),
                    "name": result.get('workoutName'),
                    "created_date": result.get('createdDate'),
                    "status": "created",
                    "message": "Workout created. Use schedule_workout to add it to your calendar."
                }
                curated = {k: v for k, v in curated.items() if v is not None}
                return json.dumps(curated, indent=2)

            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error creating workout: {str(e)}"

    @app.tool()
    async def plan_workout(workout_data: dict, date: str) -> str:
        """Create and schedule a workout in one step.

        Accepts both simplified format (sport, steps) and full Garmin format (sportType, workoutSegments).

        Args:
            workout_data: Workout structure. Simplified example: {workoutName, sport: "running", steps: [{stepOrder, stepType: "interval", endCondition: "time", endConditionValue: 1200}, ...]}
            date: Schedule date in YYYY-MM-DD format.
        """
        try:
            preprocessed = _preprocess_workout_input(workout_data)
            validated = WorkoutData(**preprocessed)
            data_dict = validated.model_dump(exclude_none=True)
            normalized = _normalize_workout_structure(data_dict)
            workout_json = json.dumps(normalized)
            upload_result = garmin_client.upload_workout(workout_json)

            workout_id = upload_result.get('workoutId') if isinstance(upload_result, dict) else None
            if not workout_id:
                return json.dumps({
                    "status": "error",
                    "message": "Failed to create workout - no workout ID returned"
                }, indent=2)

            url = f"workout-service/schedule/{workout_id}"
            schedule_response = garmin_client.garth.post("connectapi", url, json={"date": date})

            curated = {
                "status": "planned",
                "workout_id": workout_id,
                "workout_name": upload_result.get('workoutName'),
                "scheduled_date": date,
                "message": f"Workout '{upload_result.get('workoutName')}' created and scheduled for {date}"
            }
            curated = {k: v for k, v in curated.items() if v is not None}
            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error planning workout: {str(e)}"

    @app.tool()
    async def update_workout(workout_id: int, workout_data: dict) -> str:
        """Update an existing workout in the library.

        Args:
            workout_id: ID of the workout to update (from get_workouts).
            workout_data: Workout structure (simplified or full Garmin format).
        """
        try:
            existing = garmin_client.get_workout_by_id(workout_id)
            if not existing:
                return json.dumps({
                    "status": "error",
                    "message": f"Workout {workout_id} not found"
                }, indent=2)

            preprocessed = _preprocess_workout_input(workout_data)
            validated = WorkoutData(**preprocessed)
            data_dict = validated.model_dump(exclude_none=True)
            normalized = _normalize_workout_structure(data_dict)

            # Preserve workout ID and merge into existing
            normalized['workoutId'] = workout_id

            url = f"/workout-service/workout/{workout_id}"
            response = garmin_client.garth.put("connectapi", url, json=normalized, api=True)

            try:
                result = response.json() if response.text else normalized
            except Exception:
                result = normalized

            curated = {
                "status": "updated",
                "workout_id": result.get('workoutId', workout_id),
                "workout_name": result.get('workoutName', normalized.get('workoutName')),
                "updated_date": result.get('updatedDate'),
                "message": f"Workout '{normalized.get('workoutName')}' updated"
            }
            curated = {k: v for k, v in curated.items() if v is not None}
            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error updating workout: {str(e)}"

    @app.tool()
    async def delete_workout(workout_id: int) -> str:
        """Delete a workout from the library.

        Args:
            workout_id: ID of the workout to delete (from get_workouts).
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

    return app
