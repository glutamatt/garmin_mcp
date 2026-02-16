"""
Workouts API layer — preprocessing, validation, normalization, curation.

Pure functions: (Garmin client, params) → dict.
Pydantic models and normalization logic moved here from the old tool layer.
"""

import copy
import json
import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, Field

from garmin_mcp.utils import clean_nones


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
# LOOKUP MAPS
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


# =============================================================================
# PREPROCESSING — simplified AI format → full Garmin format
# =============================================================================

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

    st = step.get('stepType', 'interval')
    if isinstance(st, str):
        result['stepType'] = STEP_TYPE_MAP.get(st, STEP_TYPE_MAP['other']).copy()
    else:
        result['stepType'] = st

    ec = step.get('endCondition', step.get('endConditionType'))
    if isinstance(ec, str):
        result['endCondition'] = CONDITION_TYPE_MAP.get(ec, CONDITION_TYPE_MAP['lap.button']).copy()
    elif isinstance(ec, dict):
        result['endCondition'] = ec
    else:
        result['endCondition'] = CONDITION_TYPE_MAP['lap.button'].copy()

    if 'endConditionValue' in step and step['endConditionValue'] is not None:
        result['endConditionValue'] = step['endConditionValue']

    tt = step.get('targetType')
    if isinstance(tt, str):
        result['targetType'] = TARGET_TYPE_MAP.get(tt, TARGET_TYPE_MAP['no.target']).copy()
    elif isinstance(tt, dict) and 'workoutTargetTypeId' in tt:
        result['targetType'] = tt

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

    if 'numberOfIterations' in step:
        result['numberOfIterations'] = step['numberOfIterations']
    if 'workoutSteps' in step:
        result['workoutSteps'] = [_preprocess_step(s) for s in step['workoutSteps']]

    return result


def preprocess_workout_input(data: dict) -> dict:
    """Convert simplified AI-generated workout to full Garmin-compatible format."""
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

    sport = data.get('sportType') or data.get('sport', 'running')
    result['sportType'] = _preprocess_sport_type(sport)

    steps = data.get('steps') or data.get('workoutSteps')
    if steps:
        result['workoutSegments'] = [{
            'segmentOrder': 1,
            'sportType': result['sportType'].copy(),
            'workoutSteps': [_preprocess_step(s) for s in steps],
        }]
    elif 'workoutSegments' in data:
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
# NORMALIZATION — add Garmin-required fields, fix IDs
# =============================================================================

def normalize_workout_structure(workout_data: dict) -> dict:
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


# =============================================================================
# CURATION — extract coaching-relevant fields from raw Garmin responses
# =============================================================================

def _curate_workout_summary(workout: dict) -> dict:
    """Extract essential workout metadata for list views."""
    sport_type = workout.get('sportType', {})
    return clean_nones({
        "id": workout.get('workoutId'),
        "name": workout.get('workoutName'),
        "sport": sport_type.get('sportTypeKey'),
        "description": workout.get('description'),
        "provider": workout.get('workoutProvider'),
        "created_date": workout.get('createdDate'),
        "updated_date": workout.get('updatedDate'),
        "estimated_duration_seconds": workout.get('estimatedDuration'),
        "estimated_distance_meters": workout.get('estimatedDistance'),
    })


def _curate_scheduled_workout(scheduled: dict) -> dict:
    """Extract essential scheduled workout information."""
    workout = scheduled.get('workout', {})
    sport_type = workout.get('sportType', {})
    return clean_nones({
        "date": scheduled.get('date'),
        "schedule_id": scheduled.get('workoutScheduleId'),
        "workout_id": workout.get('workoutId'),
        "name": workout.get('workoutName'),
        "sport": sport_type.get('sportTypeKey'),
        "provider": workout.get('workoutProvider'),
        "completed": scheduled.get('completed', False),
        "estimated_duration_seconds": workout.get('estimatedDuration'),
        "estimated_distance_meters": workout.get('estimatedDistance'),
    })


# =============================================================================
# PUBLIC API FUNCTIONS
# =============================================================================

def prepare_workout_json(workout_data: dict) -> str:
    """Preprocess, validate, and normalize workout data → JSON string for SDK."""
    preprocessed = preprocess_workout_input(workout_data)
    validated = WorkoutData(**preprocessed)
    data_dict = validated.model_dump(exclude_none=True)
    normalized = normalize_workout_structure(data_dict)
    return json.dumps(normalized)


def get_workouts(client) -> dict:
    """Get all workouts from the library, curated."""
    workouts = client.get_workouts()
    if not workouts:
        return {"error": "No workouts found"}
    return {
        "count": len(workouts),
        "workouts": [_curate_workout_summary(w) for w in workouts],
    }


def get_workout_by_id(client, workout_id: int) -> dict:
    """Get detailed workout info. Returns full structure for editing."""
    workout = client.get_workout_by_id(workout_id)
    if not workout:
        return {"error": f"No workout found with ID {workout_id}"}
    sport_type = workout.get('sportType', {})
    return clean_nones({
        "id": workout.get('workoutId'),
        "name": workout.get('workoutName'),
        "sport": sport_type.get('sportTypeKey'),
        "description": workout.get('description'),
        "provider": workout.get('workoutProvider'),
        "created_date": workout.get('createdDate'),
        "updated_date": workout.get('updatedDate'),
        "estimated_duration_seconds": workout.get('estimatedDuration'),
        "estimated_distance_meters": workout.get('estimatedDistance'),
        "avg_training_speed_mps": workout.get('avgTrainingSpeed'),
        "segments": workout.get('workoutSegments'),
    })


def get_scheduled_workouts(client, start_date: str, end_date: str) -> dict:
    """Get workouts scheduled on the calendar between two dates."""
    query = {
        "query": f'query{{workoutScheduleSummariesScalar(startDate:"{start_date}", endDate:"{end_date}")}}'
    }
    result = client.query_garmin_graphql(query)
    if not result or "data" not in result:
        return {"error": f"No scheduled workouts between {start_date} and {end_date}"}

    scheduled = result.get("data", {}).get("workoutScheduleSummariesScalar", [])
    if not scheduled:
        return {"error": f"No workouts scheduled between {start_date} and {end_date}"}

    return {
        "count": len(scheduled),
        "date_range": {"start": start_date, "end": end_date},
        "scheduled_workouts": [_curate_scheduled_workout(s) for s in scheduled],
    }


def create_workout(client, workout_data: dict, date: str = None) -> dict:
    """Create a workout and optionally schedule it. Atomic-ish: upload + schedule."""
    workout_json = prepare_workout_json(workout_data)
    upload_result = client.upload_workout(workout_json)

    workout_id = upload_result.get('workoutId') if isinstance(upload_result, dict) else None
    if not workout_id:
        return {"status": "error", "message": "Failed to create workout — no workout ID returned"}

    result = clean_nones({
        "status": "created",
        "workout_id": workout_id,
        "name": upload_result.get('workoutName'),
        "created_date": upload_result.get('createdDate'),
    })

    if date:
        try:
            schedule_result = client.schedule_workout(workout_id, date)
            result["status"] = "planned"
            result["scheduled_date"] = date
            if isinstance(schedule_result, dict):
                result["schedule_id"] = schedule_result.get('workoutScheduleId')
        except Exception as e:
            result["schedule_error"] = str(e)
            result["message"] = "Workout created but scheduling failed"

    return result


def update_workout(client, workout_id: int, workout_data: dict) -> dict:
    """Replace an existing workout's definition."""
    existing = client.get_workout_by_id(workout_id)
    if not existing:
        return {"status": "error", "message": f"Workout {workout_id} not found"}

    workout_json_str = prepare_workout_json(workout_data)
    normalized = json.loads(workout_json_str)
    normalized['workoutId'] = workout_id

    url = f"/workout-service/workout/{workout_id}"
    response = client.garth.put("connectapi", url, json=normalized, api=True)

    try:
        result = response.json() if response.text else normalized
    except Exception:
        result = normalized

    return clean_nones({
        "status": "updated",
        "workout_id": result.get('workoutId', workout_id),
        "name": result.get('workoutName', normalized.get('workoutName')),
        "updated_date": result.get('updatedDate'),
    })


def delete_workout(client, workout_id: int) -> dict:
    """Delete a workout from the library after cleaning up scheduled instances."""
    unscheduled = []
    unschedule_errors = []

    try:
        today = datetime.date.today()
        start_date = (today - datetime.timedelta(days=30)).isoformat()
        end_date = (today + datetime.timedelta(days=365)).isoformat()
        scheduled = client.get_scheduled_workouts_for_range(start_date, end_date)

        for entry in scheduled:
            entry_workout = entry.get('workout', {})
            if entry_workout.get('workoutId') == workout_id:
                schedule_id = entry.get('workoutScheduleId')
                if schedule_id:
                    try:
                        client.unschedule_workout(schedule_id)
                        unscheduled.append({"schedule_id": schedule_id, "date": entry.get('date')})
                    except Exception as ue:
                        unschedule_errors.append({"schedule_id": schedule_id, "error": str(ue)})
    except Exception as e:
        unschedule_errors.append({"error": f"Failed to query schedules: {e}"})

    success = client.delete_workout(workout_id)
    if not success:
        return {"status": "failed", "workout_id": workout_id, "message": "Failed to delete workout"}

    result = {
        "status": "deleted",
        "workout_id": workout_id,
    }
    if unscheduled:
        result["unscheduled_count"] = len(unscheduled)
        result["unscheduled"] = unscheduled
    if unschedule_errors:
        result["unschedule_errors"] = unschedule_errors
    return result


def unschedule_workout(client, schedule_id: int) -> dict:
    """Remove a scheduled workout from the calendar (keeps library entry)."""
    success = client.unschedule_workout(schedule_id)
    if success:
        return {"status": "unscheduled", "schedule_id": schedule_id}
    return {"status": "failed", "schedule_id": schedule_id, "message": "Failed to unschedule workout"}


def reschedule_workout(client, schedule_id: int, new_date: str) -> dict:
    """Move a scheduled workout to a different date."""
    result = client.reschedule_workout(schedule_id, new_date)
    if isinstance(result, dict):
        return clean_nones({
            "status": "rescheduled",
            "schedule_id": schedule_id,
            "new_date": new_date,
            "workout_name": result.get('workout', {}).get('workoutName'),
        })
    return {"status": "rescheduled", "schedule_id": schedule_id, "new_date": new_date}
