"""
Activities API — curated activity data.

Pure functions: (Garmin client, params) → dict.
Returns {"error": "..."} for missing data.
"""

import logging
import os
import zipfile

from garminconnect import Garmin
from garmin_mcp.utils import clean_nones

logger = logging.getLogger(__name__)


def get_activities(
    client: Garmin,
    start_date: str = None,
    end_date: str = None,
    activity_type: str = "",
    start: int = 0,
    limit: int = 20,
    include_hr_zones: bool = False,
    fields: list[str] | None = None,
) -> dict:
    """Unified activity list: date range OR pagination.

    If start_date and end_date are given, uses date-based query.
    Otherwise, uses pagination (start/limit).
    Enriches with GraphQL data (training_load) when needed.
    """
    limit = min(max(1, limit), 100)

    if start_date and end_date:
        raw = client.get_activities_by_date(start_date, end_date, activity_type)
        if not raw:
            msg = f"No activities between {start_date} and {end_date}"
            if activity_type:
                msg += f" for type '{activity_type}'"
            return {"error": msg}

        activities = [_curate_activity_summary(a) for a in raw]
        if include_hr_zones:
            _enrich_hr_zones(client, activities, raw)
        _maybe_enrich_graphql(client, activities, start_date, end_date, fields)
        return {
            "count": len(activities),
            "date_range": {"start": start_date, "end": end_date},
            "activities": activities,
        }
    else:
        raw = client.get_activities(start, limit)
        if not raw:
            return {"error": f"No activities found at index {start}"}

        activities = [_curate_activity_summary(a) for a in raw]
        if include_hr_zones:
            _enrich_hr_zones(client, activities, raw)
        # For pagination: derive date range from results for GraphQL enrichment
        if activities:
            _maybe_enrich_graphql_from_activities(client, activities, fields)
        return {
            "start": start,
            "limit": limit,
            "count": len(activities),
            "has_more": len(raw) == limit,
            "next_start": start + limit if len(raw) == limit else None,
            "activities": activities,
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
        # Self-evaluation (athlete post-workout input) — Garmin 0-100 → Foster CR10 0-10
        "perceived_effort": round(summary["directWorkoutRpe"] / 10, 1) if summary.get("directWorkoutRpe") is not None else None,
        "workout_feel": summary.get("directWorkoutFeel"),
        # Recovery
        "recovery_hr_bpm": summary.get("recoveryHeartRate"),
        "body_battery_impact": summary.get("differenceBodyBattery"),
        # Weather (folded into detail) — Garmin returns Fahrenheit, convert to Celsius
        "temperature_celsius": round((summary.get("startingTemperatureInFahrenheit", 32) - 32) * 5 / 9, 1) if summary.get("startingTemperatureInFahrenheit") is not None else None,
        # Metadata
        "lap_count": metadata.get("lapCount"),
        "has_splits": metadata.get("hasSplits"),
    })

    # Try to get weather inline
    try:
        weather = client.get_activity_weather(activity_id)
        if weather:
            result["weather"] = clean_nones({
                "temperature_celsius": round((weather["temp"] - 32) * 5 / 9, 1) if weather.get("temp") is not None else None,
                "apparent_temperature_celsius": round((weather["apparentTemp"] - 32) * 5 / 9, 1) if weather.get("apparentTemp") is not None else None,
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


def download_activity(client: Garmin, activity_id: int, fmt: str = "fit", sandbox: str = "/tmp/garmin") -> dict:
    """Download activity and preprocess to pandas-ready CSV.

    Downloads ORIGINAL FIT (zip), extracts, parses second-by-second records,
    fixes all gotchas (cadence doubling, enhanced fields, semicircles→degrees,
    computed pace), and writes a clean CSV.

    GPX/TCX: written as-is (XML).

    Returns metadata dict with path, columns, row count — never file contents.
    """
    fmt = fmt.lower().strip()
    format_map = {
        "fit": Garmin.ActivityDownloadFormat.ORIGINAL,
        "gpx": Garmin.ActivityDownloadFormat.GPX,
        "tcx": Garmin.ActivityDownloadFormat.TCX,
    }
    if fmt not in format_map:
        return {"error": f"Unsupported format '{fmt}'. Use: fit, gpx, tcx"}

    content = client.download_activity(str(activity_id), dl_fmt=format_map[fmt])
    os.makedirs(sandbox, exist_ok=True)

    if fmt != "fit":
        file_path = os.path.join(sandbox, f"activity_{activity_id}.{fmt}")
        with open(file_path, "wb") as f:
            f.write(content)
        size_kb = round(os.path.getsize(file_path) / 1024, 1)
        return {"activity_id": activity_id, "format": fmt, "path": file_path, "size_kb": size_kb}

    # ── FIT → CSV preprocessing ──────────────────────────────────────────
    return _fit_to_csv(content, activity_id, sandbox)


_SEMICIRCLES_TO_DEG = 180.0 / (2 ** 31)


def _fit_to_csv(zip_bytes: bytes, activity_id: int, sandbox: str) -> dict:
    """Extract FIT from zip, parse records, write clean CSV."""
    import csv
    import io
    from fitparse import FitFile

    # Extract .fit from zip
    zip_path = os.path.join(sandbox, f"_tmp_{activity_id}.zip")
    with open(zip_path, "wb") as f:
        f.write(zip_bytes)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            fit_names = [n for n in zf.namelist() if n.endswith(".fit")]
            if not fit_names:
                return {"error": "No .fit file found in downloaded zip"}
            fit_bytes = zf.read(fit_names[0])
    finally:
        os.remove(zip_path)

    # Parse FIT
    fit = FitFile(io.BytesIO(fit_bytes))

    # Detect sport — running cadence is RPM (×2 for SPM), cycling cadence stays as RPM
    sport = None
    for msg in fit.get_messages("sport"):
        sport = {f.name: f.value for f in msg.fields}.get("sport")
        break

    is_running = sport in ("running", "trail_running", "treadmill_running", None)
    cadence_label = "cadence_spm" if is_running else "cadence_rpm"
    cadence_multiplier = 2 if is_running else 1

    rows = []
    first_ts = None
    for record in fit.get_messages("record"):
        raw = {f.name: f.value for f in record.fields}

        ts = raw.get("timestamp")
        if ts is None:
            continue
        if first_ts is None:
            first_ts = ts

        speed = raw.get("enhanced_speed") or raw.get("speed")
        altitude = raw.get("enhanced_altitude") or raw.get("altitude")
        cadence_rpm = raw.get("cadence")
        frac_cadence = raw.get("fractional_cadence") or 0.0

        row = {"timestamp": ts.isoformat()}
        row["elapsed_s"] = round((ts - first_ts).total_seconds(), 1)
        row["distance_m"] = round(raw["distance"], 1) if raw.get("distance") is not None else None
        row["heart_rate"] = raw.get("heart_rate")

        # Cadence: running RPM×2 → SPM, cycling stays RPM
        if cadence_rpm is not None:
            row[cadence_label] = round((cadence_rpm + frac_cadence) * cadence_multiplier)
        else:
            row[cadence_label] = None

        if speed is not None:
            row["speed_ms"] = round(speed, 3)
            row["pace_min_km"] = round(1000 / (speed * 60), 2) if speed > 0.3 else None
        else:
            row["speed_ms"] = None
            row["pace_min_km"] = None

        row["altitude_m"] = round(altitude, 1) if altitude is not None else None

        # GPS: semicircles → degrees
        lat = raw.get("position_lat")
        lon = raw.get("position_long")
        row["lat"] = round(lat * _SEMICIRCLES_TO_DEG, 6) if lat is not None else None
        row["lon"] = round(lon * _SEMICIRCLES_TO_DEG, 6) if lon is not None else None

        row["temperature_c"] = raw.get("temperature")

        # Running dynamics (optional)
        row["vertical_oscillation_mm"] = raw.get("vertical_oscillation")
        row["ground_contact_time_ms"] = raw.get("stance_time")
        row["ground_contact_balance_pct"] = raw.get("stance_time_balance")
        step_len = raw.get("step_length")
        row["step_length_cm"] = round(step_len / 10, 1) if step_len is not None else None
        row["vertical_ratio_pct"] = raw.get("vertical_ratio")

        # Power (optional)
        row["power_w"] = raw.get("power")

        rows.append(row)

    if not rows:
        return {"error": "No record data found in FIT file"}

    # Drop columns that are entirely None
    all_keys = list(rows[0].keys())
    drop_keys = {k for k in all_keys if all(r.get(k) is None for r in rows)}
    if drop_keys:
        for r in rows:
            for k in drop_keys:
                del r[k]

    # Write CSV
    csv_path = os.path.join(sandbox, f"activity_{activity_id}.csv")
    columns = [k for k in all_keys if k not in drop_keys]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    size_kb = round(os.path.getsize(csv_path) / 1024, 1)
    last = rows[-1]
    return {
        "activity_id": activity_id,
        "format": "csv",
        "path": csv_path,
        "rows": len(rows),
        "columns": columns,
        "duration_s": last.get("elapsed_s"),
        "distance_m": last.get("distance_m"),
        "size_kb": size_kb,
    }


# ── Private helpers ──────────────────────────────────────────────────────────


def _first_not_none(d: dict, *keys):
    """Return the first non-None value from d for the given keys."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


# Fields only available via GraphQL activitiesScalar (not in REST list)
_GRAPHQL_ONLY_FIELDS = {"training_load"}


def _needs_graphql(fields: list[str] | None) -> bool:
    """Check if requested fields include GraphQL-only data."""
    if fields is None:
        return True  # No filter = include everything
    return bool(set(fields) & _GRAPHQL_ONLY_FIELDS)


def _maybe_enrich_graphql(
    client: Garmin,
    activities: list[dict],
    start_date: str,
    end_date: str,
    fields: list[str] | None,
) -> None:
    """Enrich activities with GraphQL data (training_load) if needed."""
    if not _needs_graphql(fields):
        return
    try:
        display_name = getattr(client, "display_name", None)
        if not display_name:
            logger.warning("GraphQL enrichment skipped: no display_name on client")
            return
        gql_data = client.query_garmin_graphql({
            "query": f'query{{activitiesScalar(displayName:"{display_name}", '
                     f'startTimestampLocal:"{start_date}T00:00:00.00", '
                     f'endTimestampLocal:"{end_date}T23:59:59.999", '
                     f'limit:200)}}'
        })
        gql_activities = (
            gql_data.get("data", {})
            .get("activitiesScalar", {})
            .get("activityList", [])
        )
        if not gql_activities:
            logger.info("GraphQL enrichment: no activities returned for %s..%s", start_date, end_date)
            return
        # Build lookup by activity ID
        gql_by_id = {a["activityId"]: a for a in gql_activities if "activityId" in a}
        enriched = 0
        for activity in activities:
            gql = gql_by_id.get(activity.get("id"))
            if gql and gql.get("activityTrainingLoad") is not None:
                activity["training_load"] = gql["activityTrainingLoad"]
                enriched += 1
        logger.info("GraphQL enrichment: %d/%d activities got training_load", enriched, len(activities))
    except Exception as e:
        logger.warning("GraphQL enrichment failed: %s", e)


def _maybe_enrich_graphql_from_activities(
    client: Garmin,
    activities: list[dict],
    fields: list[str] | None,
) -> None:
    """Derive date range from activities and enrich via GraphQL."""
    if not _needs_graphql(fields):
        return
    # Extract date range from start_time fields
    dates = [a.get("start_time", "")[:10] for a in activities if a.get("start_time")]
    if not dates:
        return
    _maybe_enrich_graphql(client, activities, min(dates), max(dates), fields)


def _enrich_hr_zones(client: Garmin, activities: list[dict], raw: list[dict]) -> None:
    """Fetch HR zones per activity and embed as compact dict. Mutates activities in-place."""
    for activity, raw_a in zip(activities, raw):
        if activity.get("hr_zones_seconds"):
            continue  # Already has inline zones from list response
        activity_id = raw_a.get("activityId")
        if not activity_id:
            continue
        try:
            zones = client.get_activity_hr_in_timezones(activity_id)
            if zones:
                activity["hr_zones_seconds"] = {
                    f"z{z['zoneNumber']}": z.get("secsInZone", 0)
                    for z in sorted(zones, key=lambda z: z.get("zoneNumber", 0))
                    if z.get("zoneNumber")
                }
        except Exception:
            pass  # Skip zones for this activity, don't fail the batch


def _curate_activity_summary(a: dict) -> dict:
    """Curate an activity list item to essential fields."""
    result = clean_nones({
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
        # Training effect (FirstBeat) — list uses aerobicTrainingEffect, detail uses trainingEffect
        "training_effect": _first_not_none(a, "aerobicTrainingEffect", "trainingEffect"),
        "anaerobic_training_effect": a.get("anaerobicTrainingEffect"),
        "training_effect_label": a.get("trainingEffectLabel"),
        # Power — list uses avgPower/normPower, detail uses averagePower/normalizedPower
        "avg_power_watts": _first_not_none(a, "avgPower", "averagePower"),
        "normalized_power_watts": _first_not_none(a, "normPower", "normalizedPower"),
        # Self-evaluation (athlete post-workout input) — Garmin 0-100 → Foster CR10 0-10
        "perceived_effort": round(a["directWorkoutRpe"] / 10, 1) if a.get("directWorkoutRpe") is not None else None,
        "workout_feel": a.get("directWorkoutFeel"),
        # Training load (EPOC) — may be in REST list for some accounts, else GraphQL enriches
        "training_load": a.get("activityTrainingLoad"),
        # VO2max & body battery (available in list)
        "vo2max": a.get("vO2MaxValue"),
        "body_battery_impact": a.get("differenceBodyBattery"),
    })
    # HR zones — available inline in list as hrTimeInZone_1..5 (seconds)
    zones = {}
    for z in range(1, 6):
        val = a.get(f"hrTimeInZone_{z}")
        if val:
            zones[f"z{z}"] = round(val)
    if zones:
        result["hr_zones_seconds"] = zones
    return result
