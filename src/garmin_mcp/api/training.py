"""
Training & Performance API — curated fitness metrics.

Pure functions: (Garmin client, params) → dict.
Returns {"error": "..."} for missing data.
"""

from garminconnect import Garmin
from garmin_mcp.utils import clean_nones


def get_max_metrics(client: Garmin, date: str) -> dict:
    """Enriched max metrics: VO2 max + fitness age + lactate threshold."""
    raw = client.get_max_metrics(date)
    if not raw:
        return {"error": f"No max metrics for {date}"}

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

    return results[0] if len(results) == 1 else {"metrics": results}


def get_hrv_data(client: Garmin, date: str) -> dict:
    """HRV overnight summary: last night avg, weekly avg, baseline, status."""
    raw = client.get_hrv_data(date)
    if not raw:
        return {"error": f"No HRV data for {date}"}

    summary = raw.get("hrvSummary") or raw
    baseline = summary.get("baseline") or {}

    return clean_nones({
        "date": summary.get("calendarDate") or date,
        "last_night_avg_hrv_ms": summary.get("lastNightAvg"),
        "last_night_5min_high_hrv_ms": summary.get("lastNight5MinHigh"),
        "weekly_avg_hrv_ms": summary.get("weeklyAvg"),
        "baseline_balanced_low_ms": baseline.get("balancedLow"),
        "baseline_balanced_upper_ms": baseline.get("balancedUpper"),
        "status": summary.get("status"),
        "feedback": summary.get("feedbackPhrase"),
    })


def get_training_status(client: Garmin, date: str) -> dict:
    """Training status: productive/maintaining/detraining, ACWR, VO2, load balance."""
    raw = client.get_training_status(date)
    if not raw:
        return {"error": f"No training status for {date}"}

    recent_status = raw.get("mostRecentTrainingStatus") or {}
    latest_data = recent_status.get("latestTrainingStatusData") or {}

    # Get first device data
    device_data = {}
    for _device_id, data in latest_data.items():
        device_data = data
        break

    acwr = device_data.get("acuteTrainingLoadDTO") or {}
    vo2 = (raw.get("mostRecentVO2Max") or {}).get("generic") or {}

    # Load balance
    load_balance = raw.get("mostRecentTrainingLoadBalance") or {}
    load_map = load_balance.get("metricsTrainingLoadBalanceDTOMap") or {}
    load_data = {}
    for _device_id, data in load_map.items():
        load_data = data
        break

    return clean_nones({
        "date": device_data.get("calendarDate", date),
        # Training status
        "training_status": device_data.get("trainingStatus"),
        "training_status_feedback": device_data.get("trainingStatusFeedbackPhrase"),
        "sport": device_data.get("sport"),
        "fitness_trend": device_data.get("fitnessTrend"),
        # ACWR
        "acute_load": acwr.get("dailyTrainingLoadAcute"),
        "chronic_load": acwr.get("dailyTrainingLoadChronic"),
        "load_ratio": acwr.get("dailyAcuteChronicWorkloadRatio"),
        "acwr_status": acwr.get("acwrStatus"),
        "acwr_percent": acwr.get("acwrPercent"),
        "optimal_chronic_load_min": acwr.get("minTrainingLoadChronic"),
        "optimal_chronic_load_max": acwr.get("maxTrainingLoadChronic"),
        # VO2 Max
        "vo2_max": vo2.get("vo2MaxValue"),
        "vo2_max_precise": vo2.get("vo2MaxPreciseValue"),
        # Monthly load balance
        "monthly_load_aerobic_low": load_data.get("monthlyLoadAerobicLow"),
        "monthly_load_aerobic_high": load_data.get("monthlyLoadAerobicHigh"),
        "monthly_load_anaerobic": load_data.get("monthlyLoadAnaerobic"),
        "training_balance_feedback": load_data.get("trainingBalanceFeedbackPhrase"),
    })


def get_progress_summary(
    client: Garmin, start_date: str, end_date: str, metric: str
) -> dict:
    """Progress summary for a metric between dates."""
    raw = client.get_progress_summary_between_dates(start_date, end_date, metric)
    if not raw:
        return {"error": f"No progress data for {metric} between {start_date} and {end_date}"}

    result = {
        "metric": metric,
        "start_date": start_date,
        "end_date": end_date,
    }

    # Metric-specific fields
    if metric == "distance":
        result["total_distance_meters"] = raw.get("totalDistance")
        result["avg_distance_meters"] = raw.get("avgDistance")
    elif metric == "duration":
        result["total_duration_seconds"] = raw.get("totalDuration")
        result["avg_duration_seconds"] = raw.get("avgDuration")
    elif metric == "elevationGain":
        result["total_elevation_meters"] = raw.get("totalElevationGain")
        result["avg_elevation_meters"] = raw.get("avgElevationGain")
    elif metric == "movingDuration":
        result["total_moving_seconds"] = raw.get("totalMovingDuration")
        result["avg_moving_seconds"] = raw.get("avgMovingDuration")

    # Common training metrics
    result["aerobic_effect"] = raw.get("aerobicEffect")
    result["anaerobic_effect"] = raw.get("anaerobicEffect")
    result["training_load"] = raw.get("trainingLoad")
    result["activity_count"] = raw.get("numberOfActivities")

    return clean_nones(result)


def get_race_predictions(client: Garmin) -> dict:
    """Race time predictions (5K, 10K, half, marathon)."""
    raw = client.get_race_predictions()
    if not raw:
        return {"error": "No race predictions available"}
    return raw


def get_goals(client: Garmin, goal_type: str = "active") -> dict:
    """Garmin Connect goals (active, future, or past)."""
    raw = client.get_goals(goal_type)
    if not raw:
        return {"error": f"No {goal_type} goals found"}
    return raw


def get_personal_record(client: Garmin) -> dict:
    """Personal records across all activities."""
    raw = client.get_personal_record()
    if not raw:
        return {"error": "No personal records found"}
    return raw
