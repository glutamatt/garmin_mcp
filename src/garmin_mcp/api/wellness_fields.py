"""
Wellness fields — the registry behind `history daily` (one row per day).

A row of `history daily` is built from six ranged endpoints of Garmin Connect
(28 days at most per call), merged by date. `api/history.py` keeps each
endpoint's item under its own key in the raw row:

- `steps`:        `/usersummary-service/stats/steps/daily/<start>/<end>`
- `floors`:       `/usersummary-service/stats/floors/daily/<start>/<end>` (values)
- `intensity`:    `/usersummary-service/stats/im/daily/<start>/<end>`
- `stress`:       `/usersummary-service/stats/stress/daily/<start>/<end>` (values)
- `body_battery`: `/wellness-service/wellness/bodyBattery/reports/daily`
- `heart_rate`:   `/usersummary-service/stats/heartRate/daily/<start>/<end>` (values)
- `summary`:      the daily summary (`get_user_summary`) of the last day only,
  for `synced_until`.

Raw keys checked on real answers (neural-runner `tests/garmin-fixtures/`).
Naming and unit rule: `api/fields.py`.
"""

from __future__ import annotations

from datetime import date, timedelta

from garmin_mcp.api.fields import Field, Source, iso_time, parse_time

DAILY = Source("daily", "history daily")


def synced_until(summary: dict | None) -> str | None:
    """Local time where the day's data ends, when the watch has not synced the whole day yet.

    Garmin's daily summary ends its wellness period (`wellnessEndTimeLocal`) at
    the next midnight for a complete day, and at the last sync for a partial one
    (today, or a day whose end the watch has not sent yet). None for a complete
    day, and for a day without wellness data.
    """
    end = (summary or {}).get("wellnessEndTimeLocal")
    day = (summary or {}).get("calendarDate")
    if not end or not day:
        return None
    day_end = date.fromisoformat(day) + timedelta(days=1)
    return iso_time(end) if parse_time(end).date() < day_end else None


def _battery_levels(body_battery: dict | None) -> list[int]:
    """The day's body battery readings. Garmin's array keeps the day's extremes:
    its min and max are the low and high of `stats/bodybattery/daily`."""
    readings = (body_battery or {}).get("bodyBatteryValuesArray") or []
    return [level for _, level in readings if level is not None]


def _battery_low(raw: dict) -> int | None:
    levels = _battery_levels(raw.get("body_battery"))
    return min(levels) if levels else None


def _battery_high(raw: dict) -> int | None:
    levels = _battery_levels(raw.get("body_battery"))
    return max(levels) if levels else None


def _avg_stress(raw: dict) -> int | None:
    """Garmin's daily stress level, 0-100. Negative values mean "not enough data"."""
    level = (raw.get("stress") or {}).get("overallStressLevel")
    return level if level is not None and level >= 0 else None


def _daily(name, unit, doc, key, *, digits=None) -> Field:
    return Field(name, unit, doc, {DAILY: key}, digits=digits)


DAILY_REGISTRY: tuple[Field, ...] = (
    _daily("steps", "", "steps of the day", "steps.totalSteps"),
    _daily("step_goal", "", "the day's step goal (Garmin adapts it)", "steps.stepGoal"),
    _daily("distance_m", "m", "distance walked and run, from the steps", "steps.totalDistance"),
    _daily("floors_ascended", "", "floors climbed (Garmin: 1 floor = 3 m of climb)", "floors.wellnessFloorsAscended", digits=0),
    _daily("floors_descended", "", "floors descended", "floors.wellnessFloorsDescended", digits=0),
    _daily("moderate_intensity_minutes", "", "intensity minutes, moderate",
           "intensity.moderateValue"),
    _daily("vigorous_intensity_minutes", "", "intensity minutes, vigorous (count double for the weekly goal)",
           "intensity.vigorousValue"),
    _daily("avg_stress", "", "Garmin's stress level of the day, 0-100", _avg_stress),
    _daily("rest_stress_s", "s", "time at rest (stress 0-25)", "stress.restStressDuration"),
    _daily("low_stress_s", "s", "time in low stress (26-50)", "stress.lowStressDuration"),
    _daily("medium_stress_s", "s", "time in medium stress (51-75)", "stress.mediumStressDuration"),
    _daily("high_stress_s", "s", "time in high stress (76-100)", "stress.highStressDuration"),
    _daily("body_battery_low", "", "lowest body battery of the day, 0-100", _battery_low),
    _daily("body_battery_high", "", "highest body battery of the day, 0-100 (most days: the level at wake)",
           _battery_high),
    _daily("body_battery_charged", "", "body battery points gained", "body_battery.charged"),
    _daily("body_battery_drained", "", "body battery points spent", "body_battery.drained"),
    _daily("resting_hr_bpm", "bpm", "resting heart rate", "heart_rate.restingHR"),
    _daily("synced_until", "", "the day is partial: its data ends at this local time (last watch sync). "
           "Empty: the whole day is synced", lambda raw: synced_until(raw.get("summary"))),
)

# The fields that say something about the day: a row with none of them is a day
# without data (watch not worn, before the watch), left out of the CSV.
MEASURES = tuple(f.name for f in DAILY_REGISTRY if f.name not in ("step_goal", "synced_until"))


def daily_row(day: str, raw: dict) -> dict:
    """One CSV row: `date`, then every field of the registry (None when Garmin has no value)."""
    return {"date": day, **{f.name: f.read(DAILY, raw) for f in DAILY_REGISTRY}}
