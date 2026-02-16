"""
Activities API — curated activity data.

Pure functions: (Garmin client, params) → dict.
Returns {"error": "..."} for missing data.
"""

from garminconnect import Garmin
from garmin_mcp.utils import clean_nones


def get_activities(
    client: Garmin,
    start_date: str = None,
    end_date: str = None,
    activity_type: str = "",
    start: int = 0,
    limit: int = 20,
) -> dict:
    """Unified activity list: date range OR pagination.

    If start_date and end_date are given, uses date-based query.
    Otherwise, uses pagination (start/limit).
    """
    limit = min(max(1, limit), 100)

    if start_date and end_date:
        raw = client.get_activities_by_date(start_date, end_date, activity_type)
        if not raw:
            msg = f"No activities between {start_date} and {end_date}"
            if activity_type:
                msg += f" for type '{activity_type}'"
            return {"error": msg}

        return {
            "count": len(raw),
            "date_range": {"start": start_date, "end": end_date},
            "activities": [_curate_activity_summary(a) for a in raw],
        }
    else:
        raw = client.get_activities(start, limit)
        if not raw:
            return {"error": f"No activities found at index {start}"}

        return {
            "start": start,
            "limit": limit,
            "count": len(raw),
            "has_more": len(raw) == limit,
            "next_start": start + limit if len(raw) == limit else None,
            "activities": [_curate_activity_summary(a) for a in raw],
        }


def get_activity(client: Garmin, activity_id: int) -> dict:
    """Curated single activity detail: timing, distance, HR, cadence, power, training effect."""
    raw = client.get_activity(activity_id)
    if not raw:
        return {"error": f"No activity found with ID {activity_id}"}

    summary = raw.get("summaryDTO", {})
    activity_type = raw.get("activityTypeDTO", {})
    metadata = raw.get("metadataDTO", {})

    result = clean_nones({
        "id": raw.get("activityId"),
        "name": raw.get("activityName"),
        "type": activity_type.get("typeKey"),
        "parent_type": activity_type.get("parentTypeId"),
        # Timing
        "start_time_local": summary.get("startTimeLocal"),
        "start_time_gmt": summary.get("startTimeGMT"),
        "duration_seconds": summary.get("duration"),
        "moving_duration_seconds": summary.get("movingDuration"),
        "elapsed_duration_seconds": summary.get("elapsedDuration"),
        # Distance & speed
        "distance_meters": summary.get("distance"),
        "avg_speed_mps": summary.get("averageSpeed"),
        "max_speed_mps": summary.get("maxSpeed"),
        # Heart rate
        "avg_hr_bpm": summary.get("averageHR"),
        "max_hr_bpm": summary.get("maxHR"),
        "min_hr_bpm": summary.get("minHR"),
        # Calories
        "calories": summary.get("calories"),
        # Running metrics
        "avg_cadence": summary.get("averageRunCadence"),
        "max_cadence": summary.get("maxRunCadence"),
        "avg_stride_length_cm": summary.get("strideLength"),
        "steps": summary.get("steps"),
        # Power
        "avg_power_watts": summary.get("averagePower"),
        "max_power_watts": summary.get("maxPower"),
        "normalized_power_watts": summary.get("normalizedPower"),
        # Training effect
        "training_effect": summary.get("trainingEffect"),
        "anaerobic_training_effect": summary.get("anaerobicTrainingEffect"),
        "training_effect_label": summary.get("trainingEffectLabel"),
        "training_load": summary.get("activityTrainingLoad"),
        # Recovery
        "recovery_hr_bpm": summary.get("recoveryHeartRate"),
        "body_battery_impact": summary.get("differenceBodyBattery"),
        # Weather (folded into detail)
        "temperature_celsius": summary.get("startingTemperatureInFahrenheit"),
        # Metadata
        "lap_count": metadata.get("lapCount"),
        "has_splits": metadata.get("hasSplits"),
    })

    # Try to get weather inline
    try:
        weather = client.get_activity_weather(activity_id)
        if weather:
            result["weather"] = clean_nones({
                "temperature_celsius": weather.get("temp"),
                "apparent_temperature_celsius": weather.get("apparentTemp"),
                "humidity_percent": weather.get("relativeHumidity"),
                "wind_speed_mps": weather.get("windSpeed"),
                "weather_type": (weather.get("weatherTypeDTO") or {}).get("weatherTypeName"),
            })
    except Exception:
        pass  # Weather is optional, don't fail the whole response

    return result


def get_activity_splits(client: Garmin, activity_id: int) -> dict:
    """Per-lap splits: distance, duration, pace, HR, cadence, power."""
    raw = client.get_activity_splits(activity_id)
    if not raw:
        return {"error": f"No splits for activity {activity_id}"}

    laps = raw.get("lapDTOs", [])
    return {
        "activity_id": raw.get("activityId"),
        "lap_count": len(laps),
        "laps": [
            clean_nones({
                "lap_number": lap.get("lapIndex"),
                "start_time": lap.get("startTimeGMT"),
                "distance_meters": lap.get("distance"),
                "duration_seconds": lap.get("duration"),
                "avg_speed_mps": lap.get("averageSpeed"),
                "max_speed_mps": lap.get("maxSpeed"),
                "avg_hr_bpm": lap.get("averageHR"),
                "max_hr_bpm": lap.get("maxHR"),
                "calories": lap.get("calories"),
                "avg_cadence": lap.get("averageRunCadence"),
                "avg_power_watts": lap.get("averagePower"),
                "intensity_type": lap.get("intensityType"),
            })
            for lap in laps
        ],
    }


def get_activity_hr_in_timezones(client: Garmin, activity_id: int) -> dict:
    """HR zone distribution for an activity."""
    raw = client.get_activity_hr_in_timezones(activity_id)
    if not raw:
        return {"error": f"No HR zone data for activity {activity_id}"}
    return raw


def get_activity_types(client: Garmin) -> dict:
    """All available activity type codes."""
    raw = client.get_activity_types()
    if not raw:
        return {"error": "No activity types found"}
    return {
        "count": len(raw),
        "activity_types": [
            clean_nones({
                "type_id": at.get("typeId"),
                "type_key": at.get("typeKey"),
                "display_name": at.get("displayName"),
                "parent_type_id": at.get("parentTypeId"),
                "is_hidden": at.get("isHidden"),
            })
            for at in raw
        ],
    }


# ── Private helpers ──────────────────────────────────────────────────────────


def _curate_activity_summary(a: dict) -> dict:
    """Curate an activity list item to essential fields."""
    return clean_nones({
        "id": a.get("activityId"),
        "name": a.get("activityName"),
        "type": (a.get("activityType") or {}).get("typeKey"),
        "start_time": a.get("startTimeLocal"),
        "distance_meters": a.get("distance"),
        "duration_seconds": a.get("duration"),
        "moving_duration_seconds": a.get("movingDuration"),
        "calories": a.get("calories"),
        "avg_hr_bpm": a.get("averageHR"),
        "max_hr_bpm": a.get("maxHR"),
        "steps": a.get("steps"),
    })
