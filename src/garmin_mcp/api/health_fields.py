"""
Health fields — the registry behind the `health` commands, `training hrv` and `history daily`.

The same concept has the same name and unit in every command: `resting_hr_bpm`
is the resting heart rate of `health stats`, `health sleep`, `health heart-rate`
and `history daily`.

Sources (raw keys checked on real answers, neural-runner `tests/garmin-fixtures/`):
- SUMMARY:     the daily summary (`usersummary-service/usersummary/daily`): `health stats`.
- SLEEP:       `wellness-service/wellness/dailySleepData`. The resting heart rate is
               at the top level, not in `dailySleepDTO`; the sleep SpO2 is in
               `wellnessSpO2SleepSummaryDTO`. `sleepStart/EndTimestampLocal` are
               epochs in ms of the local time; `sleepNeed` is in minutes.
- HRV:         `hrv-service/hrv/<date>` (`hrvSummary`).
- READINESS:   one entry of `metrics-service/metrics/trainingreadiness/<date>` (shape
               documented in python-garminconnect `docs/graphql_queries.txt`: the
               Forerunner 165 computes none). `recoveryTime` is in minutes.
- STRESS, HEART_RATE, RESPIRATION, SPO2: the day's endpoint of each.
- BODY_BATTERY: a day of `wellness-service/wellness/bodyBattery/reports/daily`.
- DAILY:       a row of `history daily`: six ranged endpoints merged by date, each
               item under its own key (`api/history.py`):
               `steps` (`usersummary-service/stats/steps/daily`), `floors`, `intensity`
               (`stats/im/daily`), `stress`, `heart_rate` (their `values`),
               `body_battery` (the reports above), and `summary`: the daily summary
               of the last day only, for `synced_until`.

Naming and unit rule: `api/fields.py`.
"""

from __future__ import annotations

from datetime import date, timedelta

from garmin_mcp.api.fields import Field, FieldSet, Source, dig, iso_time, local_epoch_time, parse_time

SUMMARY = Source("summary", "health stats")
SLEEP = Source("sleep", "health sleep")
HRV = Source("hrv", "training hrv")
READINESS = Source("readiness", "health training-readiness")
STRESS = Source("stress", "health stress")
HEART_RATE = Source("heart_rate", "health heart-rate")
RESPIRATION = Source("respiration", "health respiration")
SPO2 = Source("spo2", "health spo2")
BODY_BATTERY = Source("body_battery", "health body-battery")
DAILY = Source("daily", "history daily")

_SOURCES = {s.name: s for s in (SUMMARY, SLEEP, HRV, READINESS, STRESS, HEART_RATE, RESPIRATION,
                                SPO2, BODY_BATTERY, DAILY)}


# ── Readers ──────────────────────────────────────────────────────────────────


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


def _level(path: str):
    """A 0-100 level where Garmin writes a negative value for "not enough data" (stress)."""
    def read(raw: dict):
        value = dig(raw, path)
        return value if value is not None and value >= 0 else None
    return read


def _battery_levels(day: dict | None) -> list[int]:
    """A day's body battery readings. Garmin's array keeps the day's extremes:
    its min and max are the low and high of `stats/bodybattery/daily`."""
    readings = (day or {}).get("bodyBatteryValuesArray") or []
    return [level for _, level in readings if level is not None]


def _battery(pick, path: str | None = None):
    def read(raw: dict):
        levels = _battery_levels(dig(raw, path) if path else raw)
        return pick(levels) if levels else None
    return read


def _local_epoch(path: str):
    """The local time of an epoch in ms that holds it (see `local_epoch_time`)."""
    def read(raw: dict):
        ms = dig(raw, path)
        return local_epoch_time(ms) if ms is not None else None
    return read


def _time(path: str):
    def read(raw: dict):
        value = dig(raw, path)
        return iso_time(value) if value else None
    return read


def _avg_of_samples(path: str):
    """Mean of a day's samples `[[timestamp, value], …]`, zeros and gaps left out."""
    def read(raw: dict):
        values = [v[1] for v in dig(raw, path) or [] if v[1] and v[1] > 0]
        return sum(values) / len(values) if values else None
    return read


# Stress levels: rest 0-25, low 26-50, medium 51-75, high 76-100.
_STRESS_BANDS = {"rest": (0, 26), "low": (26, 51), "medium": (51, 76), "high": (76, 101)}


def _stress_share(band: str):
    """Share of the day's measured stress samples (3 min each) in this band, in %."""
    low, high = _STRESS_BANDS[band]

    def read(raw: dict):
        values = [v[1] for v in raw.get("stressValuesArray") or [] if v[1] and v[1] > 0]
        return 100 * sum(low <= v < high for v in values) / len(values) if values else None
    return read


# `sleepScores` factors and their names here.
_SLEEP_FACTORS = {
    "totalDuration": "duration", "stress": "stress", "awakeCount": "awake_count",
    "restlessness": "restlessness", "remPercentage": "rem", "lightPercentage": "light",
    "deepPercentage": "deep",
}


def _sleep_factors(raw: dict) -> dict | None:
    """Garmin's rating of each part of the sleep score: `{"duration": "FAIR", "deep": "GOOD", …}`."""
    scores = dig(raw, "dailySleepDTO.sleepScores") or {}
    factors = {name: (scores.get(key) or {}).get("qualifierKey") for key, name in _SLEEP_FACTORS.items()}
    factors = {name: q for name, q in factors.items() if q}
    return factors or None


def _minutes_to_s(minutes: float) -> float:
    return minutes * 60


def _field(name: str, unit: str, doc: str, *, convert=None, digits=None, **keys) -> Field:
    """One row; `keys` maps a source name (`summary`, `sleep`…) to its raw key or reader."""
    return Field(name, unit, doc, {_SOURCES[s]: key for s, key in keys.items()}, convert, digits)


HEALTH_REGISTRY: tuple[Field, ...] = (
    _field("date", "", "the day (YYYY-MM-DD)", summary="calendarDate", sleep="dailySleepDTO.calendarDate",
           hrv="hrvSummary.calendarDate", readiness="calendarDate", stress="calendarDate",
           heart_rate="calendarDate", respiration="calendarDate", spo2="calendarDate", body_battery="date"),
    _field("synced_until", "", "the day is partial: its data ends at this local time (last watch sync). "
           "Absent (empty in a CSV): the whole day is synced",
           summary=synced_until, daily=lambda raw: synced_until(raw.get("summary"))),
    # Activity of the day
    _field("steps", "", "steps of the day", summary="totalSteps", daily="steps.totalSteps"),
    _field("step_goal", "", "the day's step goal (Garmin adapts it)", summary="dailyStepGoal",
           daily="steps.stepGoal"),
    _field("distance_m", "m", "distance walked and run, from the steps", summary="totalDistanceMeters",
           daily="steps.totalDistance"),
    _field("floors_ascended", "", "floors climbed (Garmin: 1 floor = 3 m of climb)", digits=0,
           summary="floorsAscended", daily="floors.wellnessFloorsAscended"),
    _field("floors_descended", "", "floors descended", digits=0,
           summary="floorsDescended", daily="floors.wellnessFloorsDescended"),
    _field("moderate_intensity_minutes", "", "intensity minutes, moderate",
           summary="moderateIntensityMinutes", daily="intensity.moderateValue"),
    _field("vigorous_intensity_minutes", "", "intensity minutes, vigorous (count double for the weekly goal)",
           summary="vigorousIntensityMinutes", daily="intensity.vigorousValue"),
    _field("intensity_minutes_weekly_goal", "", "weekly goal of intensity minutes", summary="intensityMinutesGoal"),
    _field("total_calories_kcal", "kcal", "calories of the day, resting included", digits=0,
           summary="totalKilocalories"),
    _field("active_calories_kcal", "kcal", "calories of activity", digits=0, summary="activeKilocalories"),
    _field("highly_active_s", "s", "time highly active", summary="highlyActiveSeconds"),
    _field("active_s", "s", "time active", summary="activeSeconds"),
    _field("sedentary_s", "s", "time sedentary", summary="sedentarySeconds"),
    _field("sleeping_s", "s", "time asleep", summary="sleepingSeconds"),
    # Heart rate
    _field("resting_hr_bpm", "bpm", "resting heart rate", summary="restingHeartRate", sleep="restingHeartRate",
           heart_rate="restingHeartRate", daily="heart_rate.restingHR"),
    _field("resting_hr_7d_avg_bpm", "bpm", "resting heart rate, mean of the last 7 days",
           summary="lastSevenDaysAvgRestingHeartRate", heart_rate="lastSevenDaysAvgRestingHeartRate"),
    _field("min_hr_bpm", "bpm", "lowest heart rate of the day", summary="minHeartRate", heart_rate="minHeartRate"),
    _field("max_hr_bpm", "bpm", "highest heart rate of the day", summary="maxHeartRate", heart_rate="maxHeartRate"),
    _field("avg_hr_bpm", "bpm", "mean heart rate of the day's samples", digits=0,
           heart_rate=_avg_of_samples("heartRateValues")),
    # Stress
    _field("avg_stress", "", "Garmin's stress level of the day, 0-100", summary=_level("averageStressLevel"),
           stress=_level("avgStressLevel"), daily=_level("stress.overallStressLevel")),
    _field("max_stress", "", "highest stress level of the day", summary=_level("maxStressLevel"),
           stress=_level("maxStressLevel")),
    _field("rest_stress_s", "s", "time at rest (stress 0-25)", summary="restStressDuration",
           daily="stress.restStressDuration"),
    _field("low_stress_s", "s", "time in low stress (26-50)", summary="lowStressDuration",
           daily="stress.lowStressDuration"),
    _field("medium_stress_s", "s", "time in medium stress (51-75)", summary="mediumStressDuration",
           daily="stress.mediumStressDuration"),
    _field("high_stress_s", "s", "time in high stress (76-100)", summary="highStressDuration",
           daily="stress.highStressDuration"),
    _field("rest_stress_percent", "%", "share of the measured time at rest", digits=1, stress=_stress_share("rest")),
    _field("low_stress_percent", "%", "share of the measured time in low stress", digits=1,
           stress=_stress_share("low")),
    _field("medium_stress_percent", "%", "share of the measured time in medium stress", digits=1,
           stress=_stress_share("medium")),
    _field("high_stress_percent", "%", "share of the measured time in high stress", digits=1,
           stress=_stress_share("high")),
    # Body battery
    _field("body_battery_wake", "", "body battery at wake, 0-100", summary="bodyBatteryAtWakeTime"),
    _field("body_battery_low", "", "lowest body battery of the day, 0-100", summary="bodyBatteryLowestValue",
           body_battery=_battery(min), daily=_battery(min, "body_battery")),
    _field("body_battery_high", "", "highest body battery of the day, 0-100 (most days: the level at wake)",
           summary="bodyBatteryHighestValue", body_battery=_battery(max), daily=_battery(max, "body_battery")),
    _field("body_battery_charged", "", "body battery points gained", summary="bodyBatteryChargedValue",
           body_battery="charged", daily="body_battery.charged"),
    _field("body_battery_drained", "", "body battery points spent", summary="bodyBatteryDrainedValue",
           body_battery="drained", daily="body_battery.drained"),
    _field("body_battery_current", "", "body battery at the last sync", summary="bodyBatteryMostRecentValue"),
    _field("body_battery_level", "", "Garmin's level: VERY_LOW, LOW, MODERATE, HIGH (a category)",
           summary="bodyBatteryDynamicFeedbackEvent.bodyBatteryLevel",
           body_battery="bodyBatteryDynamicFeedbackEvent.bodyBatteryLevel"),
    _field("body_battery_feedback", "", "Garmin's feedback code of the day",
           summary="bodyBatteryDynamicFeedbackEvent.feedbackShortType",
           body_battery="bodyBatteryDynamicFeedbackEvent.feedbackShortType"),
    # SpO2 and respiration
    _field("avg_spo2_percent", "%", "mean SpO2 of the day", summary="averageSpo2", spo2="averageSpO2"),
    _field("lowest_spo2_percent", "%", "lowest SpO2 of the day", summary="lowestSpo2", spo2="lowestSpO2"),
    _field("latest_spo2_percent", "%", "last SpO2 reading", spo2="latestSpO2"),
    _field("latest_spo2_time", "", "time of the last SpO2 reading (local)", spo2=_time("latestSpO2TimestampLocal")),
    _field("spo2_7d_avg_percent", "%", "mean SpO2 of the last 7 days", digits=1, spo2="lastSevenDaysAvgSpO2"),
    _field("avg_sleep_spo2_percent", "%", "mean SpO2 during the sleep", spo2="avgSleepSpO2",
           sleep="wellnessSpO2SleepSummaryDTO.averageSPO2"),
    _field("lowest_sleep_spo2_percent", "%", "lowest SpO2 during the sleep",
           sleep="wellnessSpO2SleepSummaryDTO.lowestSPO2"),
    _field("avg_waking_respiration_brpm", "breaths/min", "mean respiration awake",
           summary="avgWakingRespirationValue", respiration="avgWakingRespirationValue"),
    _field("avg_sleep_respiration_brpm", "breaths/min", "mean respiration asleep",
           respiration="avgSleepRespirationValue", sleep="dailySleepDTO.averageRespirationValue"),
    _field("min_respiration_brpm", "breaths/min", "lowest respiration of the day",
           summary="lowestRespirationValue", respiration="lowestRespirationValue"),
    _field("max_respiration_brpm", "breaths/min", "highest respiration of the day",
           summary="highestRespirationValue", respiration="highestRespirationValue"),
    # Sleep (the night that ends on the day)
    _field("sleep_score", "", "sleep score 0-100", sleep="dailySleepDTO.sleepScores.overall.value",
           readiness="sleepScore"),
    _field("sleep_score_qualifier", "", "EXCELLENT, GOOD, FAIR, POOR",
           sleep="dailySleepDTO.sleepScores.overall.qualifierKey"),
    _field("sleep_score_feedback", "", "Garmin's feedback code", sleep="dailySleepDTO.sleepScoreFeedback"),
    _field("sleep_score_factors", "", "Garmin's rating of each part of the score", sleep=_sleep_factors),
    _field("bedtime", "", "sleep start (local time)", sleep=_local_epoch("dailySleepDTO.sleepStartTimestampLocal")),
    _field("wake_time", "", "sleep end (local time)", sleep=_local_epoch("dailySleepDTO.sleepEndTimestampLocal")),
    _field("sleep_s", "s", "time asleep", sleep="dailySleepDTO.sleepTimeSeconds"),
    _field("deep_sleep_s", "s", "deep sleep", sleep="dailySleepDTO.deepSleepSeconds"),
    _field("light_sleep_s", "s", "light sleep", sleep="dailySleepDTO.lightSleepSeconds"),
    _field("rem_sleep_s", "s", "REM sleep", sleep="dailySleepDTO.remSleepSeconds"),
    _field("awake_s", "s", "time awake during the night", sleep="dailySleepDTO.awakeSleepSeconds"),
    _field("nap_s", "s", "naps of the day", sleep="dailySleepDTO.napTimeSeconds"),
    _field("sleep_need_s", "s", "Garmin's sleep need for the night", convert=_minutes_to_s,
           sleep="dailySleepDTO.sleepNeed.actual"),
    _field("sleep_need_feedback", "", "why the need moved: INCREASED, NO_CHANGE…",
           sleep="dailySleepDTO.sleepNeed.feedback"),
    _field("avg_sleep_hr_bpm", "bpm", "mean heart rate asleep", digits=0, sleep="dailySleepDTO.avgHeartRate"),
    _field("avg_sleep_stress", "", "mean stress asleep, 0-100", digits=0, sleep="dailySleepDTO.avgSleepStress"),
    _field("awake_count", "", "times awake", sleep="dailySleepDTO.awakeCount"),
    _field("restless_moments", "", "restless moments", sleep="restlessMomentsCount"),
    _field("skin_temp_deviation_celsius", "°C", "skin temperature against the athlete's baseline",
           digits=1, sleep="avgSkinTempDeviationC"),
    _field("body_battery_change", "", "body battery gained during the sleep", sleep="bodyBatteryChange"),
    # HRV
    _field("avg_overnight_hrv_ms", "ms", "mean HRV of the night", digits=0, sleep="avgOvernightHrv"),
    _field("last_night_avg_hrv_ms", "ms", "mean HRV of last night", hrv="hrvSummary.lastNightAvg"),
    _field("last_night_5min_high_hrv_ms", "ms", "highest 5-min HRV of last night", hrv="hrvSummary.lastNight5MinHigh"),
    _field("weekly_avg_hrv_ms", "ms", "mean HRV of the last 7 nights", hrv="hrvSummary.weeklyAvg",
           readiness="hrvWeeklyAverage"),
    _field("baseline_balanced_low_ms", "ms", "the athlete's balanced HRV band, low end",
           hrv="hrvSummary.baseline.balancedLow"),
    _field("baseline_balanced_upper_ms", "ms", "the athlete's balanced HRV band, high end",
           hrv="hrvSummary.baseline.balancedUpper"),
    _field("hrv_status", "", "BALANCED, UNBALANCED, LOW, POOR", hrv="hrvSummary.status", sleep="hrvStatus"),
    _field("hrv_feedback", "", "Garmin's feedback code (why the status)", hrv="hrvSummary.feedbackPhrase"),
    # Training readiness
    _field("score", "", "training readiness 0-100", readiness="score"),
    _field("level", "", "LOW, MODERATE, HIGH, PRIME…", readiness="level"),
    _field("feedback", "", "Garmin's short feedback code", readiness="feedbackShort"),
    _field("feedback_long", "", "Garmin's long feedback code", readiness="feedbackLong"),
    _field("measured_at", "", "time of the reading (local)", readiness=_time("timestampLocal")),
    _field("recovery_time_s", "s", "recovery time left", convert=_minutes_to_s, readiness="recoveryTime"),
    _field("acute_load", "", "7-day training load", readiness="acuteLoad"),
    _field("sleep_factor_percent", "%", "readiness factor: last sleep", readiness="sleepScoreFactorPercent"),
    _field("sleep_factor_feedback", "", "", readiness="sleepScoreFactorFeedback"),
    _field("recovery_factor_percent", "%", "readiness factor: recovery time", readiness="recoveryTimeFactorPercent"),
    _field("recovery_factor_feedback", "", "", readiness="recoveryTimeFactorFeedback"),
    _field("load_factor_percent", "%", "readiness factor: training load (ACWR)", readiness="acwrFactorPercent"),
    _field("load_factor_feedback", "", "", readiness="acwrFactorFeedback"),
    _field("stress_history_factor_percent", "%", "readiness factor: stress of the last days",
           readiness="stressHistoryFactorPercent"),
    _field("stress_history_factor_feedback", "", "", readiness="stressHistoryFactorFeedback"),
    _field("hrv_factor_percent", "%", "readiness factor: HRV", readiness="hrvFactorPercent"),
    _field("hrv_factor_feedback", "", "", readiness="hrvFactorFeedback"),
    _field("sleep_history_factor_percent", "%", "readiness factor: sleep of the last days",
           readiness="sleepHistoryFactorPercent"),
    _field("sleep_history_factor_feedback", "", "", readiness="sleepHistoryFactorFeedback"),
)

STATS_FIELDS = FieldSet(SUMMARY, HEALTH_REGISTRY)
SLEEP_FIELDS = FieldSet(SLEEP, HEALTH_REGISTRY)
HRV_FIELDS = FieldSet(HRV, HEALTH_REGISTRY)
READINESS_FIELDS = FieldSet(READINESS, HEALTH_REGISTRY)
STRESS_FIELDS = FieldSet(STRESS, HEALTH_REGISTRY)
HEART_RATE_FIELDS = FieldSet(HEART_RATE, HEALTH_REGISTRY)
RESPIRATION_FIELDS = FieldSet(RESPIRATION, HEALTH_REGISTRY)
SPO2_FIELDS = FieldSet(SPO2, HEALTH_REGISTRY)
BODY_BATTERY_FIELDS = FieldSet(BODY_BATTERY, HEALTH_REGISTRY, items_key="days")
DAILY_FIELDS = FieldSet(DAILY, HEALTH_REGISTRY)

# `health snapshot`: the overview of each section. The rest is in the section's own command.
SNAPSHOT_STATS = FieldSet(SUMMARY, HEALTH_REGISTRY, only=(
    "date", "synced_until", "steps", "distance_m", "moderate_intensity_minutes", "vigorous_intensity_minutes",
    "resting_hr_bpm", "resting_hr_7d_avg_bpm", "avg_stress", "max_stress",
    "body_battery_wake", "body_battery_low", "body_battery_high", "body_battery_charged",
    "body_battery_drained", "body_battery_current", "avg_spo2_percent", "lowest_spo2_percent",
))
SNAPSHOT_SLEEP = FieldSet(SLEEP, HEALTH_REGISTRY, only=(
    "sleep_score", "bedtime", "wake_time", "sleep_s", "deep_sleep_s", "light_sleep_s", "rem_sleep_s",
    "awake_s", "sleep_need_s", "avg_sleep_stress",
))
SNAPSHOT_READINESS = FieldSet(READINESS, HEALTH_REGISTRY, only=(
    "score", "level", "feedback", "recovery_time_s", "sleep_factor_percent", "recovery_factor_percent",
    "load_factor_percent", "stress_history_factor_percent", "hrv_factor_percent", "sleep_history_factor_percent",
))

# `history daily`: its columns, in this order; a row with none of the MEASURES is
# a day without data (watch not worn, before the watch), left out of the CSV.
_DAILY_FIELDS = tuple(f for f in HEALTH_REGISTRY if DAILY in f.keys)
MEASURES = tuple(f.name for f in _DAILY_FIELDS if f.name not in ("step_goal", "synced_until"))


def daily_row(day: str, raw: dict) -> dict:
    """One CSV row: `date`, then every `history daily` field (None when Garmin has no value)."""
    return {"date": day, **{f.name: f.read(DAILY, raw) for f in _DAILY_FIELDS}}


def body_battery_events(day: dict) -> list[dict]:
    """The day's events (sleep, activity, stress, recovery) and what each did to the body battery.

    Garmin gives the start in GMT and the time zone offset: the start here is local.
    """
    events = []
    for event in day.get("bodyBatteryActivityEvent") or []:
        start = event.get("eventStartTimeGmt")
        offset = timedelta(milliseconds=event.get("timezoneOffset") or 0)
        duration = event.get("durationInMilliseconds")
        events.append({k: v for k, v in {
            "type": event.get("eventType"),
            "start_time": (parse_time(start) + offset).strftime("%Y-%m-%dT%H:%M:%S") if start else None,
            "duration_s": round(duration / 1000) if duration is not None else None,
            "body_battery_impact": event.get("bodyBatteryImpact"),
            "feedback": event.get("shortFeedback"),
        }.items() if v is not None})
    return events
