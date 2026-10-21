"""
Calendar fields — the registry behind `calendar month`, `calendar upcoming` and `calendar events`.

Two sources:
- CALENDAR: an item of the calendar (`calendar-service/year/<y>/month/<m>`):
  an activity, a scheduled workout, an event (race)…, told apart by `itemType`.
  Its `id` is the activity id of an activity and the schedule id of a workout.
- EVENT: an item of `calendar-service/events` (the races the athlete follows),
  with the goal and the link to the race's activity.

Raw keys and units checked on real answers (neural-runner `tests/garmin-fixtures/`):
a calendar activity has its distance in cm and its duration in ms. The calendar
is an overview: the rest of an activity is in `activities get <activity_id>`
(the calendar's own `startTimestampLocal` is on a 12-hour clock without AM/PM,
and its `totalAscent` is not the activity's elevation gain).

Naming and unit rule: `api/fields.py`.
"""

from __future__ import annotations

from typing import Any

from garmin_mcp.api.fields import Field, FieldSet, Source, dig

CALENDAR = Source("calendar", "calendar month|upcoming")
EVENT = Source("event", "calendar events")

# Distance units of an event's `completionTarget` → metres.
_METRES = {"meter": 1, "kilometer": 1000, "mile": 1609.344}
# Time units of an event's goal → seconds.
_SECONDS = {"second": 1, "minute": 60, "hour": 3600}


def _of_type(item_type: str, key: str):
    """The raw `key` of a calendar item of this type only (`id` means another thing for each type)."""
    return lambda raw: raw.get(key) if raw.get("itemType") == item_type else None


def _target_metres(path: str):
    def read(raw: dict) -> float | None:
        target = dig(raw, path) or {}
        factor = _METRES.get(target.get("unit"))
        value = target.get("value")
        return value * factor if target.get("unitType") == "distance" and factor and value else None
    return read


def _calendar_distance(raw: dict) -> float | None:
    """An activity's distance (cm), or a race's target distance."""
    if raw.get("itemType") == "activity":
        cm = raw.get("distance")
        return cm / 100 if cm is not None else None
    return _target_metres("completionTarget")(raw)


def _goal_seconds(raw: dict) -> float | None:
    goal = dig(raw, "eventCustomization.customGoal") or {}
    factor = _SECONDS.get(goal.get("unit"))
    value = goal.get("value")
    return value * factor if goal.get("unitType") == "time" and factor and value else None


def _start_time(raw: dict) -> str | None:
    """The event's local start: its date and `eventTimeLocal.startTimeHhMm`."""
    hh_mm = dig(raw, "eventTimeLocal.startTimeHhMm")
    return f"{raw['date']}T{hh_mm}:00" if hh_mm and raw.get("date") else None


def _field(name: str, unit: str, doc: str, *, calendar: Any = None, event: Any = None,
           convert=None, digits=None) -> Field:
    keys = {source: key for source, key in ((CALENDAR, calendar), (EVENT, event)) if key is not None}
    return Field(name, unit, doc, keys, convert, digits)


CALENDAR_REGISTRY: tuple[Field, ...] = (
    _field("date", "", "day of the item (YYYY-MM-DD)", calendar="date", event="date"),
    _field("type", "", "activity, workout, event…", calendar="itemType"),
    _field("name", "", "title", calendar="title", event="eventName"),
    _field("sport", "", "running, cycling…", calendar="sportTypeKey", event="eventType"),
    _field("activity_id", "", "the activity: `activities get <activity_id>` (an event: the race's activity)",
           calendar=_of_type("activity", "id"), event="eventCustomization.associatedWithActivityId"),
    _field("schedule_id", "", "the workout on this day: `workouts reschedule|unschedule <schedule_id>`",
           calendar=_of_type("workout", "id")),
    _field("workout_id", "", "the workout in the library: `workouts get <workout_id>`",
           calendar="workoutId", event="workoutId"),
    _field("event_id", "", "the event", event="id"),
    _field("distance_m", "m", "activity distance, or race distance",
           calendar=_calendar_distance, event=_target_metres("completionTarget"), digits=0),
    _field("duration_s", "s", "activity duration",
           calendar=_of_type("activity", "duration"), convert=lambda ms: ms / 1000, digits=0),
    _field("start_time", "", "race start, local time of the race", calendar=_start_time, event=_start_time),
    _field("location", "", "race location", calendar="location", event="location"),
    _field("goal_time_s", "s", "the athlete's goal time for the race", event=_goal_seconds, digits=0),
    _field("primary_event", "", "the athlete's main race", event="eventCustomization.isPrimaryEvent"),
    _field("url", "", "race page", event="url"),
)

CALENDAR_ITEMS = FieldSet(CALENDAR, CALENDAR_REGISTRY, items_key="items")
EVENT_ITEMS = FieldSet(EVENT, CALENDAR_REGISTRY, items_key="events")
