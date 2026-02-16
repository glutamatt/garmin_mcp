"""
Health & Wellness API — curated daily health data.

Pure functions: (Garmin client, params) → dict.
Returns {"error": "..."} for missing data.
Lets SDK exceptions bubble for real errors (auth, network).
"""

from garminconnect import Garmin
from garmin_mcp.utils import clean_nones


def get_coaching_snapshot(client: Garmin, date: str) -> dict:
    """One-call daily overview: stats + sleep + readiness + body battery + HRV."""
    raw = client.get_coaching_snapshot(date)
    return clean_nones({
        "date": date,
        "stats": _curate_stats(raw.get("stats")) if raw.get("stats") else None,
        "sleep": _curate_sleep(raw.get("sleep")) if raw.get("sleep") else None,
        "training_readiness": _curate_readiness(raw.get("training_readiness")) if raw.get("training_readiness") else None,
        "body_battery": _curate_body_battery_summary(raw.get("body_battery")) if raw.get("body_battery") else None,
        "hrv": _curate_hrv(raw.get("hrv")) if raw.get("hrv") else None,
    })


def get_stats(client: Garmin, date: str) -> dict:
    """Curated daily stats: steps, calories, HR, stress, body battery, SpO2."""
    raw = client.get_user_summary(date)
    if not raw:
        return {"error": f"No stats for {date}"}
    return _curate_stats(raw)


def get_sleep(client: Garmin, date: str) -> dict:
    """Curated sleep summary: score, phases, SpO2, respiration."""
    raw = client.get_sleep_data(date)
    if not raw:
        return {"error": f"No sleep data for {date}"}
    return _curate_sleep(raw)


def get_stress(client: Garmin, date: str) -> dict:
    """Curated stress summary: avg/max levels, distribution percentages."""
    raw = client.get_stress_data(date)
    if not raw:
        return {"error": f"No stress data for {date}"}

    summary = clean_nones({
        "date": raw.get("calendarDate"),
        "max_stress_level": raw.get("maxStressLevel"),
        "avg_stress_level": raw.get("avgStressLevel"),
    })

    # Calculate distribution from time-series
    values = raw.get("stressValuesArray", [])
    if values:
        valid = [v[1] for v in values if v[1] and v[1] > 0]
        if valid:
            total = len(valid)
            summary["rest_percent"] = round(sum(1 for v in valid if v < 26) / total * 100, 1)
            summary["low_stress_percent"] = round(sum(1 for v in valid if 26 <= v < 51) / total * 100, 1)
            summary["medium_stress_percent"] = round(sum(1 for v in valid if 51 <= v < 76) / total * 100, 1)
            summary["high_stress_percent"] = round(sum(1 for v in valid if v >= 76) / total * 100, 1)

    return summary


def get_heart_rate(client: Garmin, date: str) -> dict:
    """Curated HR summary: resting, min, max, avg, 7-day trend."""
    raw = client.get_heart_rates(date)
    if not raw:
        return {"error": f"No heart rate data for {date}"}

    summary = clean_nones({
        "date": raw.get("calendarDate"),
        "max_heart_rate_bpm": raw.get("maxHeartRate"),
        "min_heart_rate_bpm": raw.get("minHeartRate"),
        "resting_heart_rate_bpm": raw.get("restingHeartRate"),
        "last_7_days_avg_resting_hr": raw.get("lastSevenDaysAvgRestingHeartRate"),
    })

    # Calculate average from time-series
    hr_values = raw.get("heartRateValues", [])
    if hr_values:
        valid = [v[1] for v in hr_values if v[1] and v[1] > 0]
        if valid:
            summary["avg_heart_rate_bpm"] = round(sum(valid) / len(valid), 1)

    return summary


def get_respiration(client: Garmin, date: str) -> dict:
    """Curated respiration summary: avg/min/max breaths per minute."""
    raw = client.get_respiration_data(date)
    if not raw:
        return {"error": f"No respiration data for {date}"}
    return clean_nones({
        "date": raw.get("calendarDate"),
        "lowest_breaths_per_min": raw.get("lowestRespirationValue"),
        "highest_breaths_per_min": raw.get("highestRespirationValue"),
        "avg_waking_breaths_per_min": raw.get("avgWakingRespirationValue"),
        "avg_sleep_breaths_per_min": raw.get("avgSleepRespirationValue"),
    })


def get_body_battery(client: Garmin, start_date: str, end_date: str) -> dict:
    """Curated body battery: charge/drain per day with activity events."""
    raw = client.get_body_battery(start_date, end_date)
    if not raw:
        return {"error": f"No body battery data between {start_date} and {end_date}"}

    days = []
    for day in raw:
        entry = clean_nones({
            "date": day.get("date"),
            "charged": day.get("charged"),
            "drained": day.get("drained"),
        })

        events = []
        for event in day.get("bodyBatteryActivityEvent", []):
            events.append(clean_nones({
                "type": event.get("eventType"),
                "start_time": event.get("eventStartTimeGmt"),
                "duration_minutes": round(event.get("durationInMilliseconds", 0) / 60000, 1),
                "body_battery_impact": event.get("bodyBatteryImpact"),
                "feedback": event.get("shortFeedback"),
            }))
        if events:
            entry["events"] = events

        feedback = day.get("bodyBatteryDynamicFeedbackEvent", {})
        if feedback:
            entry["current_feedback"] = feedback.get("feedbackShortType")
            entry["body_battery_level"] = feedback.get("bodyBatteryLevel")

        days.append(clean_nones(entry))

    return {"days": days}


def get_spo2(client: Garmin, date: str) -> dict:
    """Curated SpO2: avg, lowest, latest, sleep avg."""
    raw = client.get_spo2_data(date)
    if not raw:
        return {"error": f"No SpO2 data for {date}"}
    return clean_nones({
        "date": raw.get("calendarDate"),
        "avg_spo2_percent": raw.get("averageSpO2"),
        "lowest_spo2_percent": raw.get("lowestSpO2"),
        "latest_spo2_percent": raw.get("latestSpO2"),
        "latest_reading_time": raw.get("latestSpO2TimestampLocal"),
        "last_7_days_avg_spo2": raw.get("lastSevenDaysAvgSpO2"),
        "avg_sleep_spo2_percent": raw.get("avgSleepSpO2"),
    })


def get_training_readiness(client: Garmin, date: str) -> dict:
    """Curated training readiness: score, contributing factors."""
    raw = client.get_training_readiness(date)
    if not raw:
        return {"error": f"No training readiness data for {date}"}

    # API can return a list
    entries = raw if isinstance(raw, list) else [raw]
    curated = []
    for r in entries:
        curated.append(_curate_readiness_entry(r))

    if len(curated) == 1:
        return curated[0]
    return {"entries": curated}


def get_body_composition(client: Garmin, start_date: str, end_date: str = None) -> dict:
    """Body composition data for a date or range."""
    if end_date:
        raw = client.get_body_composition(start_date, end_date)
    else:
        raw = client.get_body_composition(start_date)
    if not raw:
        return {"error": f"No body composition data for {start_date}"}
    return raw


# ── Private curation helpers ─────────────────────────────────────────────────


def _curate_stats(stats: dict) -> dict:
    """Extract essential fields from user summary."""
    return clean_nones({
        "date": stats.get("calendarDate"),
        "total_steps": stats.get("totalSteps"),
        "daily_step_goal": stats.get("dailyStepGoal"),
        "distance_meters": stats.get("totalDistanceMeters"),
        "floors_ascended": stats.get("floorsAscended"),
        "total_calories": stats.get("totalKilocalories"),
        "active_calories": stats.get("activeKilocalories"),
        "highly_active_seconds": stats.get("highlyActiveSeconds"),
        "active_seconds": stats.get("activeSeconds"),
        "sedentary_seconds": stats.get("sedentarySeconds"),
        "moderate_intensity_minutes": stats.get("moderateIntensityMinutes"),
        "vigorous_intensity_minutes": stats.get("vigorousIntensityMinutes"),
        "intensity_minutes_goal": stats.get("intensityMinutesGoal"),
        "min_heart_rate_bpm": stats.get("minHeartRate"),
        "max_heart_rate_bpm": stats.get("maxHeartRate"),
        "resting_heart_rate_bpm": stats.get("restingHeartRate"),
        "last_7_days_avg_resting_hr": stats.get("lastSevenDaysAvgRestingHeartRate"),
        "avg_stress_level": stats.get("averageStressLevel"),
        "max_stress_level": stats.get("maxStressLevel"),
        "body_battery_charged": stats.get("bodyBatteryChargedValue"),
        "body_battery_drained": stats.get("bodyBatteryDrainedValue"),
        "body_battery_highest": stats.get("bodyBatteryHighestValue"),
        "body_battery_lowest": stats.get("bodyBatteryLowestValue"),
        "body_battery_current": stats.get("bodyBatteryMostRecentValue"),
        "avg_spo2_percent": stats.get("averageSpo2"),
        "lowest_spo2_percent": stats.get("lowestSpo2"),
        "avg_waking_respiration": stats.get("avgWakingRespirationValue"),
        "highest_respiration": stats.get("highestRespirationValue"),
        "lowest_respiration": stats.get("lowestRespirationValue"),
    })


def _curate_sleep(sleep_data: dict) -> dict:
    """Extract essential fields from sleep data."""
    dto = sleep_data.get("dailySleepDTO", {})
    if not dto:
        return {}
    scores = dto.get("sleepScores", {}).get("overall", {})
    total_sec = dto.get("sleepTimeSeconds", 0)

    result = clean_nones({
        "sleep_score": scores.get("value"),
        "sleep_score_qualifier": scores.get("qualifierKey"),
        "total_sleep_hours": round(total_sec / 3600, 1) if total_sec else None,
        "deep_sleep_hours": round(dto.get("deepSleepSeconds", 0) / 3600, 1) if dto.get("deepSleepSeconds") else None,
        "light_sleep_hours": round(dto.get("lightSleepSeconds", 0) / 3600, 1) if dto.get("lightSleepSeconds") else None,
        "rem_sleep_hours": round(dto.get("remSleepSeconds", 0) / 3600, 1) if dto.get("remSleepSeconds") else None,
        "awake_hours": round(dto.get("awakeSleepSeconds", 0) / 3600, 1) if dto.get("awakeSleepSeconds") else None,
        "resting_heart_rate_bpm": dto.get("restingHeartRate"),
        "avg_sleep_stress": dto.get("avgSleepStress"),
    })

    # SpO2 during sleep
    spo2 = sleep_data.get("wellnessSpO2SleepSummaryDTO", {})
    if spo2:
        result["avg_spo2"] = spo2.get("averageSpo2")
        result["lowest_spo2"] = spo2.get("lowestSpo2")

    # HRV
    if sleep_data.get("avgOvernightHrv"):
        result["avg_overnight_hrv"] = sleep_data["avgOvernightHrv"]

    return clean_nones(result)


def _curate_readiness(readiness_data) -> dict | None:
    """Extract essential fields from training readiness (for snapshot)."""
    if not readiness_data:
        return None
    entries = readiness_data if isinstance(readiness_data, list) else [readiness_data]
    if not entries:
        return None
    # Use the first (usually most relevant) entry
    return _curate_readiness_entry(entries[0])


def _curate_readiness_entry(r: dict) -> dict:
    """Curate a single training readiness entry."""
    return clean_nones({
        "date": r.get("calendarDate"),
        "level": r.get("level"),
        "score": r.get("score"),
        "feedback": r.get("feedbackShort"),
        "sleep_score": r.get("sleepScore"),
        "sleep_factor_percent": r.get("sleepScoreFactorPercent"),
        "recovery_time_hours": round(r.get("recoveryTime", 0) / 60, 1) if r.get("recoveryTime") else None,
        "recovery_factor_percent": r.get("recoveryTimeFactorPercent"),
        "training_load_factor_percent": r.get("acwrFactorPercent"),
        "acute_load": r.get("acuteLoad"),
        "hrv_factor_percent": r.get("hrvFactorPercent"),
        "hrv_weekly_avg": r.get("hrvWeeklyAverage"),
    })


def _curate_body_battery_summary(battery_data) -> dict | None:
    """Extract summary from body battery (for snapshot)."""
    if not battery_data:
        return None
    # battery_data is usually a list of days
    if isinstance(battery_data, list) and battery_data:
        day = battery_data[0]
        return clean_nones({
            "date": day.get("date"),
            "charged": day.get("charged"),
            "drained": day.get("drained"),
        })
    return None


def _curate_hrv(hrv_data: dict) -> dict | None:
    """Extract essential fields from HRV data (for snapshot)."""
    if not hrv_data:
        return None
    summary = hrv_data.get("hrvSummary") or hrv_data
    baseline = summary.get("baseline") or {}
    return clean_nones({
        "last_night_avg_hrv_ms": summary.get("lastNightAvg"),
        "weekly_avg_hrv_ms": summary.get("weeklyAvg"),
        "baseline_low_ms": baseline.get("balancedLow"),
        "baseline_upper_ms": baseline.get("balancedUpper"),
        "status": summary.get("status"),
    })
