"""
Training & Performance API — curated fitness metrics.

Pure functions: (Garmin client, params) → dict.
A day without data is `{"date", "available": False, "reason": "no_data"}`
(`not_supported_by_device` for a device feature, see `api/capabilities.py`);
failures are exceptions (see `api/contract.py`).
"""

import re

from garminconnect import Garmin
from garmin_mcp.api import capabilities
from garmin_mcp.api.contract import NO_DATA, day_answer, unavailable
from garmin_mcp.utils import clean_nones


def get_max_metrics(client: Garmin, date: str) -> dict:
    """Enriched max metrics: VO2 max + fitness age + lactate threshold."""
    raw = client.get_max_metrics(date)
    if not raw:
        return day_answer(date, None)

    metrics_list = raw if isinstance(raw, list) else [raw]
    results = []
    for m in metrics_list:
        results.append(clean_nones({
            "date": date,
            "metric_type": m.get("metricType") or m.get("sport"),
            # VO2 Max
            "vo2_max": m.get("vo2MaxValue") or (m.get("generic") or {}).get("vo2MaxValue"),
            "vo2_max_precision": m.get("vo2MaxPrecisionIndex"),
            # Fitness age
            "fitness_age_years": m.get("fitnessAge"),
            "chronological_age_years": m.get("chronologicalAge"),
            "fitness_age_description": m.get("fitnessAgeDescription"),
            # Lactate threshold
            "lactate_threshold_hr_bpm": m.get("lactateThresholdHeartRate"),
            "lactate_threshold_speed_mps": m.get("lactateThresholdSpeed"),
            "lactate_threshold_pace_sec_per_km": m.get("lactateThresholdPace"),
            # Other
            "max_heart_rate_bpm": m.get("maxHeartRate"),
            "ftp_watts": m.get("functionalThresholdPower"),
        }))

    return day_answer(date, results[0]) if len(results) == 1 else {"metrics": results}


def get_hrv_data(client: Garmin, date: str) -> dict:
    """HRV overnight summary: last night avg, weekly avg, baseline, status."""
    raw = client.get_hrv_data(date)
    if not raw:
        return day_answer(date, None)

    summary = raw.get("hrvSummary") or raw
    baseline = summary.get("baseline") or {}

    return day_answer(date, clean_nones({
        "date": summary.get("calendarDate") or date,
        "last_night_avg_hrv_ms": summary.get("lastNightAvg"),
        "last_night_5min_high_hrv_ms": summary.get("lastNight5MinHigh"),
        "weekly_avg_hrv_ms": summary.get("weeklyAvg"),
        "baseline_balanced_low_ms": baseline.get("balancedLow"),
        "baseline_balanced_upper_ms": baseline.get("balancedUpper"),
        "status": summary.get("status"),
        "feedback": summary.get("feedbackPhrase"),
    }))


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


def get_progress_summary(
    client: Garmin, start_date: str, end_date: str, metric: str
) -> dict:
    """Progress summary for a metric between dates.

    SDK returns: [{date, countOfActivities, stats: {running: {<metric>: {count, min, max, avg, sum}}, ...}}]
    We flatten per-sport stats into a clean list.
    """
    raw = client.get_progress_summary_between_dates(start_date, end_date, metric) or []
    entries = raw if isinstance(raw, list) else [raw]

    # Aggregate across all periods, grouped by sport
    sport_totals = {}
    total_activities = 0
    for entry in entries:
        total_activities += entry.get("countOfActivities", 0)
        stats = entry.get("stats", {})
        for sport, metrics in stats.items():
            metric_data = metrics.get(metric, {})
            if sport not in sport_totals:
                sport_totals[sport] = {"count": 0, "sum": 0.0}
            sport_totals[sport]["count"] += metric_data.get("count", 0)
            sport_totals[sport]["sum"] += metric_data.get("sum", 0.0)
            sport_totals[sport]["avg"] = metric_data.get("avg")
            sport_totals[sport]["min"] = metric_data.get("min")
            sport_totals[sport]["max"] = metric_data.get("max")

    # Build curated per-sport entries
    curated_entries = []
    for sport, data in sport_totals.items():
        entry = clean_nones({
            "activity_type": sport,
            "activity_count": data["count"],
        })
        total = data["sum"]
        avg = data.get("avg")
        if metric == "distance":
            # Garmin returns distance in cm, convert to meters
            entry["total_distance_meters"] = round(total / 100, 1) if total else None
            entry["avg_distance_meters"] = round(avg / 100, 1) if avg else None
        elif metric == "duration":
            entry["total_duration_seconds"] = round(total / 1000) if total else None
            entry["avg_duration_seconds"] = round(avg / 1000) if avg else None
        elif metric == "elevationGain":
            entry["total_elevation_meters"] = round(total / 100, 1) if total else None
            entry["avg_elevation_meters"] = round(avg / 100, 1) if avg else None
        elif metric == "movingDuration":
            entry["total_moving_seconds"] = round(total / 1000) if total else None
            entry["avg_moving_seconds"] = round(avg / 1000) if avg else None
        curated_entries.append(clean_nones(entry))

    return clean_nones({
        "metric": metric,
        "start_date": start_date,
        "end_date": end_date,
        "total_activities": total_activities,
        "entries": curated_entries,
    })


def get_race_predictions(client: Garmin) -> dict:
    """Race time predictions (5K, 10K, half, marathon)."""
    return client.get_race_predictions() or unavailable(NO_DATA)


def get_goals(client: Garmin, goal_type: str = "active") -> dict:
    """Garmin Connect goals (active, future, or past)."""
    return client.get_goals(goal_type) or []


def get_personal_record(client: Garmin) -> dict:
    """Personal records across all activities."""
    return client.get_personal_record() or []
