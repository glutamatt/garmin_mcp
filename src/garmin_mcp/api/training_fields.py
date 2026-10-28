"""
Training fields — the registry behind `training max-metrics`, `race-predictions`,
`lactate-threshold`, `endurance-score`, `hill-score` and `personal-records`,
and the load sources of `training load`.

Raw keys checked on real answers (neural-runner `tests/garmin-fixtures/`, Forerunner 165)
where the device computes the metric. The Forerunner 165 computes no lactate threshold
(speed, heart rate), no endurance score and no hill score: those shapes come from
python-garminconnect `docs/graphql_queries.txt` and are tested on it only.

Naming and unit rule: `api/fields.py`.
"""

from __future__ import annotations

from garmin_mcp.api.fields import Field, FieldSet, Source, dig, iso_time

MAX_METRICS = Source("max_metrics", "training max-metrics")
RACE_PREDICTIONS = Source("race_predictions", "training race-predictions")
LACTATE_THRESHOLD = Source("lactate_threshold", "training lactate-threshold")
ENDURANCE = Source("endurance", "training endurance-score")
HILL = Source("hill", "training hill-score")

_SOURCES = {s.name: s for s in (MAX_METRICS, RACE_PREDICTIONS, LACTATE_THRESHOLD, ENDURANCE, HILL)}

# `training load`: where the load of one activity comes from → its unit.
LOAD_SOURCES = {
    "srpe": "RPE × min",  # Foster's session RPE: perceived_effort (0-10) × duration in minutes
    "epoc": "EPOC",       # Garmin's training_load, when the watch computes it
}

# Endurance score classes: Garmin's `classification` (1-7) and the lower limit of each.
ENDURANCE_CLASSES = ("recreational", "intermediate", "trained", "well_trained", "expert", "superior", "elite")
_ENDURANCE_LIMITS = ("Intermediate", "Trained", "WellTrained", "Expert", "Superior", "Elite")


def _endurance_class(raw: dict) -> str | None:
    number = raw.get("classification")
    return ENDURANCE_CLASSES[number - 1] if isinstance(number, int) and 1 <= number <= 7 else None


def _endurance_limits(raw: dict) -> dict | None:
    """Score where each class starts: `{"intermediate": 5100, …, "elite": 8800}`."""
    limits = {cls: raw.get(f"classificationLowerLimit{key}")
              for cls, key in zip(ENDURANCE_CLASSES[1:], _ENDURANCE_LIMITS)}
    limits = {cls: v for cls, v in limits.items() if v is not None}
    return limits or None


def _time(path: str):
    def read(raw: dict):
        value = dig(raw, path)
        return iso_time(value) if value else None
    return read


def _field(name: str, unit: str, doc: str, *, convert=None, digits=None, **keys) -> Field:
    return Field(name, unit, doc, {_SOURCES[s]: key for s, key in keys.items()}, convert, digits)


TRAINING_REGISTRY: tuple[Field, ...] = (
    _field("date", "", "the day (YYYY-MM-DD)", max_metrics="generic.calendarDate", race_predictions="calendarDate",
           endurance="calendarDate", hill="calendarDate"),
    # VO2max and fitness age
    _field("vo2_max", "", "running VO2max (mL/kg/min) as Garmin shows it", max_metrics="generic.vo2MaxValue"),
    _field("vo2_max_precise", "", "running VO2max, one decimal", max_metrics="generic.vo2MaxPreciseValue"),
    _field("cycling_vo2_max", "", "cycling VO2max (mL/kg/min)", max_metrics="cycling.vo2MaxValue"),
    _field("fitness_age", "", "Garmin's fitness age, years", digits=1, max_metrics="fitness_age.fitnessAge"),
    _field("achievable_fitness_age", "", "fitness age within reach", digits=1,
           max_metrics="fitness_age.achievableFitnessAge"),
    _field("chronological_age", "", "years", max_metrics="fitness_age.chronologicalAge"),
    _field("heat_acclimation_percent", "%", "", max_metrics="heatAltitudeAcclimation.heatAcclimationPercentage"),
    _field("altitude_acclimation_m", "m", "", max_metrics="heatAltitudeAcclimation.altitudeAcclimation"),
    # Race predictions
    _field("race_5k_s", "s", "predicted 5K time", race_predictions="time5K"),
    _field("race_10k_s", "s", "predicted 10K time", race_predictions="time10K"),
    _field("race_half_marathon_s", "s", "predicted half marathon time", race_predictions="timeHalfMarathon"),
    _field("race_marathon_s", "s", "predicted marathon time", race_predictions="timeMarathon"),
    # Lactate threshold (running). Garmin's threshold speed is left out: its unit is
    # not checked on a device that computes it.
    _field("lactate_threshold_hr_bpm", "bpm", "heart rate at the lactate threshold",
           lactate_threshold="speed_and_heart_rate.heartRate"),
    _field("lactate_threshold_date", "", "day of the threshold measure",
           lactate_threshold="speed_and_heart_rate.calendarDate"),
    _field("ftp_watts", "W", "running functional threshold power", digits=0,
           lactate_threshold="power.functionalThresholdPower"),
    _field("power_to_weight", "W/kg", "running FTP per kg", digits=2, lactate_threshold="power.powerToWeight"),
    _field("ftp_date", "", "day of the FTP", lactate_threshold=_time("power.ftpCreateTime")),
    # Endurance score
    _field("endurance_score", "", "Garmin's endurance score", endurance="overallScore"),
    _field("endurance_class", "", "recreational … elite", endurance=_endurance_class),
    _field("endurance_class_limits", "", "score where each class starts", endurance=_endurance_limits),
    # Hill score
    _field("hill_score", "", "Garmin's hill score", hill="overallScore"),
    _field("hill_strength_score", "", "strength part of the hill score", hill="strengthScore"),
    _field("hill_endurance_score", "", "endurance part of the hill score", hill="enduranceScore"),
)

MAX_METRICS_FIELDS = FieldSet(MAX_METRICS, TRAINING_REGISTRY)
RACE_PREDICTION_FIELDS = FieldSet(RACE_PREDICTIONS, TRAINING_REGISTRY)
LACTATE_THRESHOLD_FIELDS = FieldSet(LACTATE_THRESHOLD, TRAINING_REGISTRY)
ENDURANCE_FIELDS = FieldSet(ENDURANCE, TRAINING_REGISTRY)
HILL_FIELDS = FieldSet(HILL, TRAINING_REGISTRY)


# ── Personal records ─────────────────────────────────────────────────────────
# Garmin's `typeId` → (record, unit of `value`). Checked on real records: 1 km,
# 1 mile, 5K, 10K and half marathon are times (s), the longest run and ride are
# distances (m), 9 is a ride's total ascent (m), 11 the 40 km ride time (s), 12-14
# the most steps of a day, week, month (no activity). The other ids follow Garmin
# Connect's list of records; 15 and up are not named (not checked).
PERSONAL_RECORDS = {
    1: ("run_1km", "s"), 2: ("run_1mile", "s"), 3: ("run_5k", "s"), 4: ("run_10k", "s"),
    5: ("run_half_marathon", "s"), 6: ("run_marathon", "s"), 7: ("run_longest", "m"),
    8: ("ride_longest", "m"), 9: ("ride_total_ascent", "m"), 10: ("ride_max_avg_power_20min", "watts"),
    11: ("ride_40k", "s"), 12: ("steps_day", ""), 13: ("steps_week", ""), 14: ("steps_month", ""),
}


def personal_record(raw: dict) -> dict:
    """One record: its name, its value with the unit in the key, the day and the activity.

    An unknown `typeId` keeps the raw value, without a unit: `{"record": "type_17", "value": …}`.
    """
    record, unit = PERSONAL_RECORDS.get(raw.get("typeId"), (f"type_{raw.get('typeId')}", ""))
    value = raw.get("value")
    local = raw.get("activityStartDateTimeLocalFormatted")
    gmt = raw.get("prStartTimeGmtFormatted")
    curated = {
        "record": record,
        f"value_{unit}" if unit else "value": round(value) if value is not None and (unit or record.startswith("steps")) else value,
        # A steps record has no activity, so no local time: its GMT start (local midnight) is given.
        "date": local[:10] if local else None,
        "start_time_gmt": iso_time(gmt) if gmt and not local else None,
        "activity_id": raw.get("activityId"),
        "activity_name": raw.get("activityName"),
        "sport": raw.get("activityType"),
    }
    return {k: v for k, v in curated.items() if v is not None}
