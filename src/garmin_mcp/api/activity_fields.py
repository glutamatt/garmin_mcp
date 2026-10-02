"""
Activity fields — the registry behind `activities list`, `get` and `splits`.

Each row says where Garmin keeps a value in each source:
- LIST:   an item of the activity list (`activitylist-service`);
- DETAIL: the activity detail (`activity-service/activity/<id>`), most values in `summaryDTO`;
- LAP:    an item of `lapDTOs` (`activity-service/activity/<id>/splits`). Same keys as `summaryDTO`.

Raw keys checked on real answers (neural-runner `tests/garmin-fixtures/`). Two keys
are added by `api/activities.py` from another Garmin call, and say so below:
`weather` (detail) and `startTimeLocal` (lap: Garmin's laps only have GMT).

Naming and unit rule: `api/fields.py`.
"""

from __future__ import annotations

from garmin_mcp.api.fields import (
    Field,
    FieldSet,
    Source,
    fahrenheit_to_celsius,
    iso_time,
    mph_to_mps,
    pace_s_per_km,
)

LIST = Source("list", "activities list")
DETAIL = Source("detail", "activities get")
LAP = Source("lap", "activities splits")

WEATHER = Source("weather", "activities get")


# Output names before the registry (audit PR 2, 2026-10). `--fields` with one of them
# is refused with the new name.
_FORMER_NAMES = {
    "sport": ("type",),
    "parent_type_id": ("parent_type",),
    "start_time": ("start_time_local",),
    "duration_s": ("duration_seconds",),
    "moving_duration_s": ("moving_duration_seconds",),
    "elapsed_duration_s": ("elapsed_duration_seconds",),
    "distance_m": ("distance_meters",),
    "hr_zones_s": ("hr_zones_seconds",),
    "calories_kcal": ("calories",),
    "avg_cadence_spm": ("avg_cadence",),
    "max_cadence_spm": ("max_cadence",),
    "vo2_max": ("vo2max",),
}


def _field(name, unit, doc, *, list=None, detail=None, lap=None, convert=None, digits=None) -> Field:
    keys = {source: key for source, key in ((LIST, list), (DETAIL, detail), (LAP, lap)) if key is not None}
    return Field(name, unit, doc, keys, convert, digits, _FORMER_NAMES.get(name, ()))


def _moving_speed(item: dict) -> float | None:
    """The list has no `averageMovingSpeed`: Garmin's value is distance / moving time, the same here."""
    distance, moving = item.get("distance"), item.get("movingDuration")
    return distance / moving if distance is not None and moving else None


def _hr_zones(item: dict) -> dict | None:
    """`hrTimeInZone_1..5` (seconds) → `{"z1": 666, …}`, zones at 0 left out."""
    zones = {f"z{z}": round(item[f"hrTimeInZone_{z}"]) for z in range(1, 6) if item.get(f"hrTimeInZone_{z}")}
    return zones or None


def _cr10(rpe: float) -> float:
    """Garmin's RPE is 0-100; the athlete chose 1-10 on the watch (Foster CR10)."""
    return rpe / 10


def _weather(raw: dict) -> dict | None:
    return WEATHER_FIELDS.curate(raw) or None


# Output order = row order.
FIELDS: tuple[Field, ...] = (
    # ── What, when ──
    _field("id", "", "Activity id (for `activities get <id>`)",
           list="activityId", detail="activityId"),
    _field("name", "", "Activity name",
           list="activityName", detail="activityName"),
    _field("sport", "", "Garmin activity type: running, trail_running, cycling… (the values of `--type`)",
           list="activityType.typeKey", detail="activityTypeDTO.typeKey"),
    _field("parent_type_id", "", "Id of the parent activity type (see `activities types`)",
           list="activityType.parentTypeId", detail="activityTypeDTO.parentTypeId"),
    _field("lap_number", "", "Lap number, from 1",
           lap="lapIndex"),
    _field("intensity_type", "", "Lap intensity: WARMUP, ACTIVE, REST, COOLDOWN…",
           lap="intensityType"),
    _field("workout_step_index", "", "Workout step of the lap, from 0 (step 1 of `workouts get` = 0). "
           "Absent outside the workout",
           lap="wktStepIndex"),
    _field("start_time", "", "Start, local time",
           list="startTimeLocal", detail="summaryDTO.startTimeLocal",
           lap="startTimeLocal",  # added by get_activity_splits
           convert=iso_time),
    _field("start_time_gmt", "", "Start, GMT",
           list="startTimeGMT", detail="summaryDTO.startTimeGMT", lap="startTimeGMT", convert=iso_time),
    # ── Duration, distance, pace ──
    _field("duration_s", "s", "Timer time (pauses left out)",
           list="duration", detail="summaryDTO.duration", lap="duration", digits=0),
    _field("moving_duration_s", "s", "Time in motion (stops left out)",
           list="movingDuration", detail="summaryDTO.movingDuration", lap="movingDuration", digits=0),
    _field("elapsed_duration_s", "s", "Time from start to end, pauses included",
           list="elapsedDuration", detail="summaryDTO.elapsedDuration", lap="elapsedDuration", digits=0),
    _field("distance_m", "m", "Distance",
           list="distance", detail="summaryDTO.distance", lap="distance", digits=0),
    _field("avg_pace_s_per_km", "s/km", "Average pace over the timer time",
           list="averageSpeed", detail="summaryDTO.averageSpeed", lap="averageSpeed",
           convert=pace_s_per_km, digits=0),
    _field("moving_pace_s_per_km", "s/km", "Average pace in motion (stops left out)",
           list=_moving_speed, detail="summaryDTO.averageMovingSpeed", lap="averageMovingSpeed",
           convert=pace_s_per_km, digits=0),
    _field("gap_s_per_km", "s/km", "Grade-adjusted pace: the flat-ground pace of the same effort. "
           "Use it to compare runs with different elevation",
           list="avgGradeAdjustedSpeed", detail="summaryDTO.avgGradeAdjustedSpeed", lap="avgGradeAdjustedSpeed",
           convert=pace_s_per_km, digits=0),
    _field("avg_speed_mps", "m/s", "Average speed",
           list="averageSpeed", detail="summaryDTO.averageSpeed", lap="averageSpeed", digits=2),
    _field("max_speed_mps", "m/s", "Maximum speed",
           list="maxSpeed", detail="summaryDTO.maxSpeed", lap="maxSpeed", digits=2),
    # ── Elevation ──
    _field("elevation_gain_m", "m", "Elevation gain",
           list="elevationGain", detail="summaryDTO.elevationGain", lap="elevationGain", digits=0),
    _field("elevation_loss_m", "m", "Elevation loss",
           list="elevationLoss", detail="summaryDTO.elevationLoss", lap="elevationLoss", digits=0),
    _field("min_elevation_m", "m", "Lowest altitude",
           list="minElevation", detail="summaryDTO.minElevation", lap="minElevation", digits=0),
    _field("max_elevation_m", "m", "Highest altitude",
           list="maxElevation", detail="summaryDTO.maxElevation", lap="maxElevation", digits=0),
    # ── Heart rate ──
    _field("avg_hr_bpm", "bpm", "Average heart rate",
           list="averageHR", detail="summaryDTO.averageHR", lap="averageHR", digits=0),
    _field("max_hr_bpm", "bpm", "Maximum heart rate",
           list="maxHR", detail="summaryDTO.maxHR", lap="maxHR", digits=0),
    _field("min_hr_bpm", "bpm", "Minimum heart rate",
           detail="summaryDTO.minHR", digits=0),
    _field("hr_zones_s", "s", "Time in each heart rate zone: {z1: …, z5: …}, zones at 0 left out",
           list=_hr_zones),
    _field("recovery_hr_bpm", "bpm", "Recovery heart rate",
           detail="summaryDTO.recoveryHeartRate", digits=0),
    # ── Energy ──
    _field("calories_kcal", "kcal", "Energy spent",
           list="calories", detail="summaryDTO.calories", lap="calories", digits=0),
    # ── Running dynamics ──
    _field("avg_cadence_spm", "steps/min", "Average running cadence",
           list="averageRunningCadenceInStepsPerMinute", detail="summaryDTO.averageRunCadence",
           lap="averageRunCadence", digits=0),
    _field("max_cadence_spm", "steps/min", "Maximum running cadence",
           list="maxRunningCadenceInStepsPerMinute", detail="summaryDTO.maxRunCadence",
           lap="maxRunCadence", digits=0),
    _field("steps", "", "Step count",
           list="steps", detail="summaryDTO.steps"),
    _field("avg_stride_length_cm", "cm", "Average stride length (one step)",
           list="avgStrideLength", detail="summaryDTO.strideLength", lap="strideLength", digits=0),
    _field("avg_ground_contact_time_ms", "ms", "Average ground contact time",
           list="avgGroundContactTime", detail="summaryDTO.groundContactTime", lap="groundContactTime",
           digits=0),
    _field("avg_vertical_oscillation_cm", "cm", "Average vertical oscillation",
           list="avgVerticalOscillation", detail="summaryDTO.verticalOscillation", lap="verticalOscillation",
           digits=1),
    _field("avg_vertical_ratio_percent", "%", "Average vertical ratio (oscillation / stride)",
           list="avgVerticalRatio", detail="summaryDTO.verticalRatio", lap="verticalRatio", digits=1),
    # ── Power ──
    _field("avg_power_watts", "W", "Average power",
           list="avgPower", detail="summaryDTO.averagePower", lap="averagePower", digits=0),
    _field("max_power_watts", "W", "Maximum power",
           list="maxPower", detail="summaryDTO.maxPower", lap="maxPower", digits=0),
    _field("normalized_power_watts", "W", "Normalized power",
           list="normPower", detail="summaryDTO.normalizedPower", lap="normalizedPower", digits=0),
    # ── Training effect, load, effort ──
    _field("training_effect", "", "Aerobic training effect, 0-5 (Firstbeat)",
           list="aerobicTrainingEffect", detail="summaryDTO.trainingEffect", digits=1),
    _field("anaerobic_training_effect", "", "Anaerobic training effect, 0-5 (Firstbeat)",
           list="anaerobicTrainingEffect", detail="summaryDTO.anaerobicTrainingEffect", digits=1),
    _field("training_effect_label", "", "Main benefit: AEROBIC_BASE, TEMPO, THRESHOLD…",
           list="trainingEffectLabel", detail="summaryDTO.trainingEffectLabel"),
    _field("training_load", "", "Training load (EPOC), when the device computes it",
           list="activityTrainingLoad", detail="summaryDTO.activityTrainingLoad", digits=1),
    _field("perceived_effort", "", "Effort entered by the athlete after the run, 0-10 (Foster CR10)",
           detail="summaryDTO.directWorkoutRpe", convert=_cr10, digits=1),
    _field("workout_feel", "", "Feel entered by the athlete after the run, 0-100",
           detail="summaryDTO.directWorkoutFeel"),
    _field("vo2_max", "mL/kg/min", "VO2max estimate after the activity",
           list="vO2MaxValue", digits=1),
    _field("body_battery_impact", "", "Body Battery change during the activity (negative = drain)",
           list="differenceBodyBattery", detail="summaryDTO.differenceBodyBattery"),
    # ── Context ──
    _field("temperature_celsius", "°C", "Starting temperature",
           detail="summaryDTO.startingTemperatureInFahrenheit", convert=fahrenheit_to_celsius, digits=1),
    _field("lap_count", "", "Number of laps",
           list="lapCount", detail="metadataDTO.lapCount"),
    _field("has_splits", "", "True when the activity has laps",
           list="hasSplits", detail="metadataDTO.hasSplits"),
    _field("weather", "", "Weather at the start, from the nearest weather station (see WEATHER_FIELDS)",
           detail="weather",  # added by get_activity, from get_activity_weather
           convert=_weather),
)


# Garmin's activity weather is imperial: temperatures in °F, wind in mph.
WEATHER_FIELDS = FieldSet(WEATHER, (
    Field("temperature_celsius", "°C", "Air temperature", {WEATHER: "temp"}, fahrenheit_to_celsius, 1),
    Field("apparent_temperature_celsius", "°C", "Felt temperature", {WEATHER: "apparentTemp"},
          fahrenheit_to_celsius, 1),
    Field("humidity_percent", "%", "Relative humidity", {WEATHER: "relativeHumidity"}, digits=0),
    Field("wind_speed_mps", "m/s", "Wind speed", {WEATHER: "windSpeed"}, mph_to_mps, 1),
    Field("weather_type", "", "Sky: Fair, Light Rain…", {WEATHER: "weatherTypeDTO.desc"}),
))

LIST_FIELDS = FieldSet(LIST, FIELDS, items_key="activities", always=("sport",))
DETAIL_FIELDS = FieldSet(DETAIL, FIELDS, always=("sport",))
LAP_FIELDS = FieldSet(LAP, FIELDS, items_key="laps")
