"""
Workouts API layer — the readable workout format in and out, Garmin calls, curation.

Pure functions: (Garmin client, params) → dict.
The readable format (parse, render, estimates) is in `api/workout_format.py`.
Output contract (empty answers, failures): see `api/contract.py`. A change
that Garmin does not apply raises `GarminWriteError`, never `{"status": "error"}`.
"""

import datetime
import logging
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from garmin_mcp.api import workout_format
from garmin_mcp.api.contract import GarminWriteError, NotFound, as_garmin_error
from garmin_mcp.utils import clean_nones

logger = logging.getLogger(__name__)


# =============================================================================
# PYDANTIC MODELS — the native JSON we send to Garmin, exactly
# =============================================================================
# `workout_format.to_garmin` builds it; these models check every payload, in a
# dry-run too. `extra="forbid"`: a key not listed here is a bug of the builder.


class _Native(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SportType(_Native):
    sportTypeId: int = Field(description="1=running, 2=cycling")
    sportTypeKey: str
    displayOrder: int


class StepType(_Native):
    stepTypeId: int = Field(description="1=warmup, 2=cooldown, 3=interval, 4=recovery, 5=rest, 6=repeat, 7=other")
    stepTypeKey: str
    displayOrder: int


class EndCondition(_Native):
    conditionTypeId: int = Field(description="1=lap.button, 2=time, 3=distance, 7=iterations")
    conditionTypeKey: str
    displayOrder: int
    displayable: bool


class TargetType(_Native):
    workoutTargetTypeId: int = Field(description="1=no.target, 3=cadence, 4=heart.rate.zone, 6=pace.zone")
    workoutTargetTypeKey: str
    displayOrder: int


class StrokeType(_Native):
    strokeTypeId: int
    displayOrder: int


class EquipmentType(_Native):
    equipmentTypeId: int
    displayOrder: int


class WorkoutStep(_Native):
    """An executable step (warmup, interval, recovery, rest, cooldown, other)."""
    type: Literal["ExecutableStepDTO"]
    stepId: int
    stepOrder: int
    stepType: StepType
    endCondition: EndCondition
    endConditionValue: Optional[float] = Field(default=None, description="Seconds (time) or meters (distance)")
    targetType: TargetType
    zoneNumber: Optional[int] = Field(default=None, description="Heart rate zone 1-5")
    targetValueOne: Optional[float] = Field(default=None, description="pace.zone: FASTER bound, m/s; hr/cadence: lower")
    targetValueTwo: Optional[float] = Field(default=None, description="pace.zone: SLOWER bound, m/s; hr/cadence: higher")
    description: Optional[str] = Field(default=None, description="Step note, shown on the watch")
    strokeType: StrokeType
    equipmentType: EquipmentType


class RepeatGroup(_Native):
    """Steps done `numberOfIterations` times."""
    type: Literal["RepeatGroupDTO"]
    stepId: int
    stepOrder: int
    stepType: StepType
    numberOfIterations: int
    endCondition: EndCondition
    endConditionValue: float
    skipLastRestStep: bool
    smartRepeat: bool
    workoutSteps: List[WorkoutStep]


class WorkoutSegment(_Native):
    segmentOrder: int
    sportType: SportType
    workoutSteps: List[Annotated[Union[WorkoutStep, RepeatGroup], Field(discriminator="type")]]


class WorkoutData(_Native):
    """Complete workout payload for Garmin Connect."""
    workoutName: str
    description: Optional[str] = None
    sportType: SportType
    workoutSegments: List[WorkoutSegment]
    isWheelchair: Optional[bool] = None
    estimatedDurationInSecs: Optional[int] = None
    estimatedDistanceInMeters: Optional[float] = None


# =============================================================================
# READABLE FORMAT → PAYLOAD
# =============================================================================


def prepare_workout(workout: dict) -> dict:
    """The native payload for a readable workout: parsed, checked, with its estimates.

    Invalid input raises `InvalidInput` (exit 2) with every error. The same
    function runs for a create, an update and their dry-run.
    """
    native = workout_format.to_garmin(workout)
    WorkoutData.model_validate(native)
    return native


def preview_workout(workout: dict) -> dict:
    """What a create or update would send, read back in the readable format.

    The steps are rendered from the payload itself (paces read back from m/s),
    with the estimated duration and distance. An estimate that a step does not
    give is absent, and `not_estimated` names the steps and why (lap, no pace).
    """
    native = prepare_workout(workout)
    totals = workout_format.estimate(native["workoutSegments"][0]["workoutSteps"])
    not_estimated = {}
    if totals.duration_s is None:
        not_estimated["duration_s"] = totals.no_duration
    if totals.distance_m is None:
        not_estimated["distance_m"] = totals.no_distance
    return clean_nones({
        "workout": workout_format.from_garmin(native),
        "estimated_duration_s": totals.duration_s,
        "estimated_distance_m": totals.distance_m,
        "not_estimated": not_estimated or None,
    })


# =============================================================================
# CURATION — extract coaching-relevant fields from raw Garmin responses
# =============================================================================


def _whole(value) -> Optional[int]:
    """An estimate as an integer; Garmin's 0 means no estimate."""
    return round(value) if value else None


def _estimates(raw: dict) -> dict:
    return {
        "estimated_duration_s": _whole(raw.get('estimatedDurationInSecs')),
        "estimated_distance_m": _whole(raw.get('estimatedDistanceInMeters')),
    }


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
        # The list says `updateDate`, the detail `updatedDate`.
        "updated_date": workout.get('updatedDate') or workout.get('updateDate'),
        **_estimates(workout),
    })


def _curate_scheduled_workout(scheduled: dict) -> dict:
    """Extract essential scheduled workout information.

    SDK returns flat structure: {scheduledWorkoutId, workoutId, workoutName,
    workoutType, scheduleDate, estimatedDurationInSecs, ...}
    """
    return clean_nones({
        "date": scheduled.get('scheduleDate'),
        "schedule_id": scheduled.get('scheduledWorkoutId'),
        "workout_id": scheduled.get('workoutId'),
        "name": scheduled.get('workoutName'),
        "sport": scheduled.get('workoutType'),
        "completed": scheduled.get('associatedActivityId') is not None,
        **_estimates(scheduled),
    })


# =============================================================================
# PUBLIC API FUNCTIONS
# =============================================================================


def get_workouts(client) -> dict:
    """Get all workouts from the library, curated."""
    workouts = client.get_workouts() or []
    return {
        "count": len(workouts),
        "workouts": [_curate_workout_summary(w) for w in workouts],
    }


def get_workout_by_id(client, workout_id: int, raw: bool = False) -> dict:
    """A workout in the readable format, ready to edit and give to create or update.

    `raw`: Garmin's own JSON, unchanged. `warnings` names what the readable
    format cannot say and the targets stored in the reverse of Garmin Connect's order.
    """
    workout = client.get_workout_by_id(workout_id)
    if not workout:
        raise NotFound(f"No workout {workout_id}")
    if raw:
        return workout
    readable = workout_format.from_garmin(workout)
    warnings = readable.pop("warnings", None)
    return clean_nones({
        "id": workout.get('workoutId'),
        **readable,
        **_estimates(workout),
        "created_date": workout.get('createdDate'),
        "updated_date": workout.get('updatedDate'),
        "provider": workout.get('workoutProvider'),
        "warnings": warnings,
    })


def get_scheduled_workouts(client, start_date: str, end_date: str) -> dict:
    """Get workouts scheduled on the calendar between two dates."""
    scheduled = client.get_scheduled_workouts_for_range(start_date, end_date) or []
    return {
        "count": len(scheduled),
        "date_range": {"start": start_date, "end": end_date},
        "scheduled_workouts": [_curate_scheduled_workout(s) for s in scheduled],
    }


def create_workout(client, workout_data: dict, date: str = None) -> dict:
    """Create a workout (readable format) and optionally schedule it: upload, then schedule.

    If the upload works but the scheduling fails, the workout is in the library:
    the error gives its id, so that it gets scheduled, not created twice.
    """
    upload_result = client.upload_workout(prepare_workout(workout_data))

    workout_id = upload_result.get('workoutId') if isinstance(upload_result, dict) else None
    if not workout_id:
        raise GarminWriteError("Garmin did not create the workout: no workout ID returned")

    result = clean_nones({
        "status": "created",
        "workout_id": workout_id,
        "name": upload_result.get('workoutName'),
        "created_date": upload_result.get('createdDate'),
    })

    if date:
        try:
            schedule_result = client.schedule_workout(workout_id, date)
        except Exception as e:
            raise GarminWriteError(
                f"Workout {workout_id} was created, but scheduling it on {date} failed "
                f"({as_garmin_error(e)}). Do not create it again: "
                f"`workouts schedule {workout_id} --date {date}`."
            ) from e
        result["status"] = "planned"
        result["scheduled_date"] = date
        if isinstance(schedule_result, dict):
            result["schedule_id"] = schedule_result.get('workoutScheduleId')

    return result


def update_workout(client, workout_id: int, workout_data: dict) -> dict:
    """Replace an existing workout's definition with a readable workout."""
    normalized = {**prepare_workout(workout_data), 'workoutId': workout_id}
    existing = client.get_workout_by_id(workout_id)
    if not existing:
        raise NotFound(f"No workout {workout_id}")

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
        scheduled = client.get_scheduled_workouts_for_range(start_date, end_date) or []

        for entry in scheduled:
            if entry.get('workoutId') == workout_id:
                schedule_id = entry.get('scheduledWorkoutId')
                if schedule_id:
                    try:
                        client.unschedule_workout(schedule_id)
                        unscheduled.append({"schedule_id": schedule_id, "date": entry.get('scheduleDate')})
                    except Exception as ue:
                        unschedule_errors.append({"schedule_id": schedule_id, "error": str(ue)})
    except Exception as e:
        unschedule_errors.append({"error": f"Failed to query schedules: {e}"})

    success = client.delete_workout(workout_id)
    if not success:
        raise GarminWriteError(f"Garmin did not delete workout {workout_id}")

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


def schedule_workout(client, workout_id: int, date: str) -> dict:
    """Schedule an existing workout from the library onto a calendar date."""
    schedule_result = client.schedule_workout(workout_id, date)
    result = {"status": "scheduled", "workout_id": workout_id, "date": date}
    if isinstance(schedule_result, dict):
        result["schedule_id"] = schedule_result.get('workoutScheduleId')
    return result


def unschedule_workout(client, schedule_id: int) -> dict:
    """Remove a scheduled workout from the calendar (keeps library entry)."""
    success = client.unschedule_workout(schedule_id)
    if not success:
        raise GarminWriteError(f"Garmin did not unschedule {schedule_id}")
    return {"status": "unscheduled", "schedule_id": schedule_id}


def reschedule_workout(client, schedule_id: int, new_date: str) -> dict:
    """Move a scheduled workout to a different date.

    Implemented as unschedule + re-schedule (Garmin's PUT endpoint returns 500).
    If the second step fails, the workout is on no date: the error says how to
    put it back.
    """
    # Find the workout_id for this schedule entry
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=30)).isoformat()
    end = (today + datetime.timedelta(days=365)).isoformat()
    scheduled = client.get_scheduled_workouts_for_range(start, end) or []

    workout_id = None
    workout_name = None
    for entry in scheduled:
        if entry.get('scheduledWorkoutId') == schedule_id:
            workout_id = entry.get('workoutId')
            workout_name = entry.get('workoutName')
            break

    if not workout_id:
        raise NotFound(f"No scheduled workout {schedule_id} between {start} and {end}")

    # Unschedule the old entry
    if not client.unschedule_workout(schedule_id):
        raise GarminWriteError(f"Garmin did not unschedule {schedule_id}: nothing was moved")

    # Re-schedule on the new date
    try:
        schedule_result = client.schedule_workout(workout_id, new_date)
    except Exception as e:
        raise GarminWriteError(
            f"Schedule {schedule_id} was removed, but scheduling workout {workout_id} on "
            f"{new_date} failed ({as_garmin_error(e)}): the workout is on no date now. "
            f"`workouts schedule {workout_id} --date {new_date}`."
        ) from e
    new_schedule_id = schedule_result.get('workoutScheduleId') if isinstance(schedule_result, dict) else None

    return clean_nones({
        "status": "rescheduled",
        "old_schedule_id": schedule_id,
        "new_schedule_id": new_schedule_id,
        "workout_id": workout_id,
        "workout_name": workout_name,
        "new_date": new_date,
    })
