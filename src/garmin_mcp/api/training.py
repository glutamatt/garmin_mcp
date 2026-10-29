"""
Training & Performance API — curated fitness metrics.

Pure functions: (Garmin client, params) → dict.
A day without data is `{"date", "available": False, "reason": "no_data"}`
(`not_supported_by_device` for a device feature, see `api/capabilities.py`);
failures are exceptions (see `api/contract.py`).
"""

import logging
import re
import statistics
from collections.abc import Sequence
from datetime import date as _date, timedelta as _timedelta
from typing import NamedTuple

from garminconnect import Garmin
from garmin_mcp.api import capabilities
from garmin_mcp.api.activities import add_effort
from garmin_mcp.api.activity_fields import LIST_EFFORT_FIELDS, LIST_FIELDS
from garmin_mcp.api.contract import (
    NO_DATA,
    NOT_SUPPORTED_BY_DEVICE,
    AuthError,
    InvalidInput,
    as_garmin_error,
    day_answer,
    unavailable,
)
from garmin_mcp.api.health_fields import HRV_FIELDS
from garmin_mcp.api.training_fields import (
    ENDURANCE_FIELDS,
    HILL_FIELDS,
    LACTATE_THRESHOLD_FIELDS,
    LOAD_SOURCES,
    MAX_METRICS_FIELDS,
    RACE_PREDICTION_FIELDS,
    acwr_zone,
    personal_record,
)
from garmin_mcp.utils import clean_nones

logger = logging.getLogger(__name__)


def get_max_metrics(client: Garmin, date: str) -> dict:
    """VO2max (running, cycling), fitness age, heat and altitude acclimation.

    Two calls: `maxmet` (VO2max, acclimation) and `fitnessage` (Garmin's
    `maxmet` has a `fitnessAge` key, always null).
    """
    raw = client.get_max_metrics(date)
    entry = (raw[0] if isinstance(raw, list) and raw else raw) or {}
    curated = MAX_METRICS_FIELDS.curate({**entry, "fitness_age": _fitness_age(client, date)})
    return day_answer(date, {"date": date, **curated} if curated else None)


def _fitness_age(client: Garmin, date: str) -> dict:
    """Garmin's fitness age of the day, or {} when its call fails: VO2max does not depend on it."""
    try:
        return client.get_fitnessage_data(date) or {}
    except Exception as e:  # noqa: BLE001 — logged, the answer has no fitness age
        error = as_garmin_error(e)
        if isinstance(error, AuthError):
            raise error from e
        logger.warning("Fitness age of %s not read: %s", date, error)
        return {}


def get_hrv_data(client: Garmin, date: str) -> dict:
    """HRV overnight: last night, 7-night mean, the athlete's balanced band, status and why."""
    raw = client.get_hrv_data(date)
    curated = HRV_FIELDS.curate(raw) if raw else None
    return day_answer(date, {"date": date, **curated} if curated else None)


def get_lactate_threshold(client: Garmin) -> dict:
    """The latest running lactate threshold (heart rate) and running FTP.

    A part the device does not compute is named in `empty_fields` with the reason.
    """
    curated = LACTATE_THRESHOLD_FIELDS.curate(client.get_lactate_threshold(latest=True) or {})
    if "lactate_threshold_hr_bpm" in curated:
        return curated
    reason = capabilities.missing_reason(client, capabilities.LACTATE_THRESHOLD)
    if not curated:
        return unavailable(reason)
    return {**curated, "empty_fields": {"lactate_threshold_hr_bpm": reason}}


def get_endurance_score(client: Garmin, date: str, weeks: int) -> dict:
    """The endurance score on `date`, its class, and the weekly mean over `weeks` weeks."""
    start = (_date.fromisoformat(date) - _timedelta(weeks=weeks)).isoformat()
    raw = client.get_endurance_score(start, date) or {}
    dto = raw.get("enduranceScoreDTO") or {}
    curated = ENDURANCE_FIELDS.curate(dto)
    weekly = [
        {"week": week, "avg": group.get("groupAverage"), "max": group.get("groupMax")}
        for week, group in sorted((raw.get("groupMap") or {}).items())
        if group.get("groupAverage") is not None
    ]
    if not curated and not weekly:
        return capabilities.day_answer(client, capabilities.ENDURANCE_SCORE, date, None)
    return {"date": dto.get("calendarDate") or date, **curated, "weekly": weekly}


def get_hill_score(client: Garmin, start_date: str, end_date: str) -> dict:
    """Hill score per day (overall, strength, endurance)."""
    raw = client.get_hill_score(start_date, end_date) or {}
    days = [HILL_FIELDS.curate(d) for d in raw.get("hillScoreDTOList") or []]
    days = [d for d in days if d.get("hill_score") is not None]
    if not days:
        reason = capabilities.missing_reason(client, capabilities.HILL_SCORE)
        if reason == NOT_SUPPORTED_BY_DEVICE:
            return unavailable(reason, **{"from": start_date, "to": end_date})
    return {"from": start_date, "to": end_date, "count": len(days), "days": days}


def get_training_status(client: Garmin, date: str) -> dict:
    """Training status of the main device: status, acute and chronic load (ACWR),
    weekly load, monthly load balance and its targets, VO2max.

    Garmin keeps one entry per device that computes it, keyed by device id
    (`latestTrainingStatusData`, `metricsTrainingLoadBalanceDTOMap`). The main
    device is the entry with `primaryTrainingDevice: true`, else the latest one.
    A watch that computes no training status (Forerunner 165) gets an answer of
    nulls: `not_supported_by_device`.
    """
    raw = client.get_training_status(date) or {}
    status_block = raw.get("mostRecentTrainingStatus") or {}
    balance_block = raw.get("mostRecentTrainingLoadBalance") or {}
    status = _main_device_entry(status_block.get("latestTrainingStatusData"))
    balance = _main_device_entry(balance_block.get("metricsTrainingLoadBalanceDTOMap"))
    acute = status.get("acuteTrainingLoadDTO") or {}
    vo2 = (raw.get("mostRecentVO2Max") or {}).get("generic") or {}
    phrase = status.get("trainingStatusFeedbackPhrase")
    device_id = status.get("deviceId") or balance.get("deviceId")

    curated = clean_nones({
        "date": status.get("calendarDate") or balance.get("calendarDate") or date,
        "device": _device_name(device_id, status_block, balance_block),
        "device_id": device_id,
        # Training status
        "training_status": _status_label(phrase) or status.get("trainingStatus"),
        "training_status_feedback": phrase,
        "training_paused": status.get("trainingPaused"),
        "sport": status.get("sport"),
        "fitness_trend": status.get("fitnessTrend"),
        # Weekly load (devices without ACWR) and its optimal range
        "weekly_training_load": _load(status.get("weeklyTrainingLoad")),
        "optimal_weekly_load_min": _load(status.get("loadTunnelMin")),
        "optimal_weekly_load_max": _load(status.get("loadTunnelMax")),
        # ACWR: acute load (7 days) / chronic load (28 days)
        "acute_load": _load(acute.get("dailyTrainingLoadAcute")),
        "chronic_load": _load(acute.get("dailyTrainingLoadChronic")),
        "load_ratio": acute.get("dailyAcuteChronicWorkloadRatio"),
        "acwr_status": acute.get("acwrStatus"),
        "acwr_status_feedback": acute.get("acwrStatusFeedback"),
        "acwr_percent": acute.get("acwrPercent"),
        "optimal_chronic_load_min": _load(acute.get("minTrainingLoadChronic")),
        "optimal_chronic_load_max": _load(acute.get("maxTrainingLoadChronic")),
        # VO2 Max
        "vo2_max": vo2.get("vo2MaxValue"),
        "vo2_max_precise": vo2.get("vo2MaxPreciseValue"),
        # Monthly load balance (4 weeks) and Garmin's target range for each part
        **_monthly_load(balance),
        "training_balance_feedback": balance.get("trainingBalanceFeedbackPhrase"),
    })
    return capabilities.day_answer(client, capabilities.TRAINING_STATUS, date, curated)


# Garmin's feedback phrase is `<STATUS>_<n>` (`PRODUCTIVE_3`, `MAINTAINING_3`); its
# `trainingStatus` is a number (7, 4) with no table published.
_STATUS_PHRASE = re.compile(r"^([A-Z_]+?)_\d+$")

# The three parts of the monthly load balance: output prefix → Garmin's prefix.
_MONTHLY_LOADS = {
    "monthly_load_aerobic_low": "monthlyLoadAerobicLow",
    "monthly_load_aerobic_high": "monthlyLoadAerobicHigh",
    "monthly_load_anaerobic": "monthlyLoadAnaerobic",
}


def _main_device_entry(by_device: dict | None) -> dict:
    """The entry of the main device: `primaryTrainingDevice: true`, else the latest."""
    entries = [e for e in (by_device or {}).values() if isinstance(e, dict)]
    if not entries:
        return {}
    primary = [e for e in entries if e.get("primaryTrainingDevice")]
    return max(primary or entries, key=lambda e: (e.get("calendarDate") or "", e.get("timestamp") or 0))


def _device_name(device_id, *blocks: dict) -> str | None:
    for block in blocks:
        for device in block.get("recordedDevices") or []:
            if device.get("deviceId") == device_id:
                return device.get("deviceName")
    return None


def _status_label(phrase: str | None) -> str | None:
    match = _STATUS_PHRASE.match(phrase or "")
    return match.group(1) if match else None


def _load(value: float | None) -> int | None:
    """A training load: Garmin gives floats (1926.3918), the unit is a whole point."""
    return round(value) if value is not None else None


def _monthly_load(balance: dict) -> dict:
    loads = {}
    for name, key in _MONTHLY_LOADS.items():
        loads[name] = _load(balance.get(key))
        loads[f"{name}_target_min"] = _load(balance.get(f"{key}TargetMin"))
        loads[f"{name}_target_max"] = _load(balance.get(f"{key}TargetMax"))
    return loads


_LOAD_WEEKS = 4
_PLAN_FORMAT = "YYYY-MM-DD:MINUTES:RPE, comma-separated (2026-11-01:60:7,2026-11-02:40:3)"
_PLAN_RPE = (1, 10)
_DAY_MINUTES = 24 * 60


class PlannedSession(NamedTuple):
    """A session to come, counted as session RPE: minutes × RPE."""

    day: _date
    minutes: float
    rpe: float

    @property
    def load(self) -> float:
        return self.minutes * self.rpe


def parse_plan(text: str) -> list[PlannedSession]:
    """`2026-11-01:60:7,2026-11-02:40:3` → the planned sessions. InvalidInput names the bad entry."""
    sessions = []
    for entry in text.split(","):
        parts = entry.strip().split(":")
        try:
            day, minutes, rpe = parts
            session = PlannedSession(_date.fromisoformat(day), float(minutes), float(rpe))
        except ValueError as e:
            raise InvalidInput(f"Invalid plan entry '{entry.strip()}': {_PLAN_FORMAT}") from e
        if not (0 < session.minutes <= _DAY_MINUTES and _PLAN_RPE[0] <= session.rpe <= _PLAN_RPE[1]):
            raise InvalidInput(f"Invalid plan entry '{entry.strip()}': 0 < minutes ≤ {_DAY_MINUTES}, "
                               f"RPE {_PLAN_RPE[0]}-{_PLAN_RPE[1]}. {_PLAN_FORMAT}")
        sessions.append(session)
    return sessions


def get_training_load(client: Garmin, date: str, source: str = "srpe",
                      plan: Sequence[PlannedSession] = ()) -> dict:
    """Load of the 4 weeks that end on `date` (local days, every sport), from the activities.

    - `week_load`: the last 7 days; `chronic_week_load`: the mean of the 3 weeks before.
    - `acwr` = week_load / chronic_week_load, uncoupled: the last week is not in
      the chronic load, so it does not weigh on both sides of the ratio. None when
      the 3 weeks before have no load. `acwr_zone`: see `acwr_zone`.
    - Foster: `monotony` = mean / standard deviation of the last 7 daily loads
      (None when every day has the same load), `strain` = week_load × monotony.

    An activity without load (no RPE, a watch without EPOC) counts as 0 and is
    listed in `load_missing`. When no activity has a load: `available: false`.

    `plan`: sessions to come, added to their day as session RPE, so `date` can be a
    future day and the projection reads like today's numbers. Each day and week
    with a plan says how much of its load is `planned`. srpe only: the EPOC of a
    session to come is not known.
    """
    if source not in LOAD_SOURCES:
        raise InvalidInput(f"Unknown load '{source}'. Valid: {', '.join(LOAD_SOURCES)}")
    try:
        end = _date.fromisoformat(date)
    except ValueError as e:
        raise InvalidInput(f"Invalid date '{date}' (YYYY-MM-DD)") from e
    start = end - _timedelta(weeks=_LOAD_WEEKS) + _timedelta(days=1)
    days = [start + _timedelta(days=i) for i in range(_LOAD_WEEKS * 7)]
    window = {"from": start.isoformat(), "to": end.isoformat()}
    if plan and source != "srpe":
        raise InvalidInput("A plan counts minutes × RPE (srpe load): the EPOC of a session to come is not known")
    planned = dict.fromkeys(days, 0.0)
    for session in plan:
        if session.day not in planned:
            raise InvalidInput(f"Planned session on {session.day} is outside the 4 weeks "
                               f"{window['from']} → {window['to']}")
        planned[session.day] += session.load

    raw = client.get_activities_by_date(window["from"], window["to"], "") or []
    if source == "srpe":
        raw, missing = add_effort(client, raw)
    else:
        missing = {}

    daily = dict.fromkeys(days, 0.0)
    for activity in raw:
        load = _activity_load(activity, source)
        if load is None:
            missing.setdefault(str(activity.get("activityId")), NO_DATA)
            continue
        day = _date.fromisoformat(LIST_FIELDS.value("start_time", activity)[:10])
        if day in daily:
            daily[day] += load

    if raw and len(missing) == len(raw):
        reason = (capabilities.missing_reason(client, capabilities.TRAINING_LOAD)
                  if source == "epoc" else NO_DATA)
        return unavailable(reason, **window, load=source, activities=len(raw))

    planned_loads = [planned[day] for day in days]
    loads = [daily[day] + planned[day] for day in days]
    last_7 = loads[-7:]
    week_load = sum(last_7)
    chronic_week_load = sum(loads[:-7]) / (_LOAD_WEEKS - 1)
    acwr = round(week_load / chronic_week_load, 2) if chronic_week_load else None
    deviation = statistics.pstdev(last_7)
    monotony = round(statistics.mean(last_7) / deviation, 2) if deviation else None
    answer = {
        **window,
        "load": source,
        "unit": LOAD_SOURCES[source],
        "week_load": round(week_load),
        "chronic_week_load": round(chronic_week_load),
        "acwr": acwr,
        "acwr_zone": acwr_zone(acwr),
        "monotony": monotony,
        "strain": round(week_load * monotony) if monotony is not None else None,
        "weeks": [
            _with_planned({"from": days[w * 7].isoformat(), "to": days[w * 7 + 6].isoformat(),
                           "load": round(sum(loads[w * 7:(w + 1) * 7]))},
                          sum(planned_loads[w * 7:(w + 1) * 7]))
            for w in range(_LOAD_WEEKS)
        ],
        "last_7_days": [_with_planned({"date": day.isoformat(), "load": round(load)}, planned[day])
                        for day, load in zip(days[-7:], last_7)],
        "activities": len(raw),
    }
    if plan:
        answer["planned_load"] = round(sum(planned_loads))
    if missing:
        answer["load_missing"] = missing
    return answer


def _with_planned(entry: dict, planned: float) -> dict:
    """A day or week of `training load`, with the planned part of its load when there is one."""
    return {**entry, "planned": round(planned)} if planned else entry


def _activity_load(activity: dict, source: str) -> float | None:
    """One activity's load, or None when it has none."""
    if source == "epoc":
        return LIST_FIELDS.value("training_load", activity)
    effort = LIST_EFFORT_FIELDS.value("perceived_effort", activity)
    duration = LIST_EFFORT_FIELDS.value("duration_s", activity)
    if effort is None or duration is None:
        return None
    return effort * duration / 60


# `training progress` metrics: output name and divisor from Garmin's internal unit to SI.
_PROGRESS_UNITS = {
    "distance": ("distance_m", 100),          # cm
    "duration": ("duration_s", 1000),         # ms
    "movingDuration": ("moving_duration_s", 1000),
    "elevationGain": ("elevation_gain_m", 100),
}


def get_progress_summary(
    client: Garmin, start_date: str, end_date: str, metric: str
) -> dict:
    """Total and mean of a metric per sport between two dates.

    SDK returns: [{date, countOfActivities, stats: {running: {<metric>: {count, min, max, avg, sum}}, ...}}]
    in Garmin's internal units (cm, ms): converted here.
    """
    raw = client.get_progress_summary_between_dates(start_date, end_date, metric) or []
    name, divisor = _PROGRESS_UNITS[metric]

    totals: dict[str, dict] = {}
    for entry in raw if isinstance(raw, list) else [raw]:
        for sport, metrics in (entry.get("stats") or {}).items():
            data = metrics.get(metric) or {}
            total = totals.setdefault(sport, {"count": 0, "sum": 0.0})
            total["count"] += data.get("count") or 0
            total["sum"] += data.get("sum") or 0.0

    sports = [
        clean_nones({"sport": sport, "activity_count": t["count"], f"total_{name}": round(t["sum"] / divisor),
                     f"avg_{name}": round(t["sum"] / divisor / t["count"]) if t["count"] else None})
        for sport, t in sorted(totals.items(), key=lambda item: -item[1]["sum"])
    ]
    return {
        "metric": metric, "from": start_date, "to": end_date,
        "activity_count": sum(s["activity_count"] for s in sports),
        "count": len(sports), "sports": sports,
    }


def get_race_predictions(client: Garmin) -> dict:
    """Garmin's latest race time predictions (5K, 10K, half, marathon), in seconds."""
    curated = RACE_PREDICTION_FIELDS.curate(client.get_race_predictions() or {})
    return curated if curated else unavailable(NO_DATA)


def get_goals(client: Garmin, goal_type: str = "active") -> dict:
    """Garmin Connect goals (active, future, or past), as Garmin gives them."""
    goals = client.get_goals(goal_type) or []
    return {"count": len(goals), "goals": goals}


def get_personal_records(client: Garmin) -> dict:
    """Personal records: `{record, value_s | value_m | …, date, activity_id}` each."""
    records = [personal_record(r) for r in client.get_personal_record() or []]
    return {"count": len(records), "records": records}
