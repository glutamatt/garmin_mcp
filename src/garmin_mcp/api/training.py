"""
Training & Performance API — curated fitness metrics.

Pure functions: (Garmin client, params) → dict.
A day without data is `{"date", "available": False, "reason": "no_data"}`
(`not_supported_by_device` for a device feature, see `api/capabilities.py`);
failures are exceptions (see `api/contract.py`).
"""

import re
from datetime import date as _date, timedelta as _timedelta

from garminconnect import Garmin
from garmin_mcp.api import capabilities
from garmin_mcp.api.contract import NO_DATA, NOT_SUPPORTED_BY_DEVICE, day_answer, unavailable
from garmin_mcp.api.health_fields import HRV_FIELDS
from garmin_mcp.api.training_fields import (
    ENDURANCE_FIELDS,
    HILL_FIELDS,
    LACTATE_THRESHOLD_FIELDS,
    MAX_METRICS_FIELDS,
    RACE_PREDICTION_FIELDS,
    personal_record,
)
from garmin_mcp.utils import clean_nones


def get_max_metrics(client: Garmin, date: str) -> dict:
    """VO2max (running, cycling), fitness age, heat and altitude acclimation.

    Two calls: `maxmet` (VO2max, acclimation) and `fitnessage` (Garmin's
    `maxmet` has a `fitnessAge` key, always null).
    """
    raw = client.get_max_metrics(date)
    entry = (raw[0] if isinstance(raw, list) and raw else raw) or {}
    fitness_age = client.get_fitnessage_data(date)
    curated = MAX_METRICS_FIELDS.curate({**entry, "fitness_age": fitness_age or {}})
    return day_answer(date, {"date": date, **curated} if curated else None)


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
