"""
Activities API — curated activity data.

Pure functions: (Garmin client, params) → dict.
Output contract (empty answers, failures): see `api/contract.py`.
Fields of `list`, `get` and `splits` (names, units, raw keys): see `api/activity_fields.py`.
"""

import bisect
import io
import logging
import os
import statistics
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from garminconnect import Garmin
from garmin_mcp.api.activity_fields import (
    DETAIL_FIELDS,
    LAP_FIELDS,
    LIST_EFFORT_FIELDS,
    LIST_FIELDS,
    INTERVAL_FIELDS,
    RUN_WALK_FIELDS,
    split_type,
)
from garmin_mcp.api.contract import (
    NO_DATA,
    AuthError,
    InvalidInput,
    NotFound,
    Unavailable,
    as_garmin_error,
    error_reason,
)
from garmin_mcp.api.fields import parse_time, shift_time
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
    with_effort: bool = False,
) -> dict:
    """Unified activity list: date range OR pagination.

    If start_date and end_date are given, uses date-based query.
    Otherwise, uses pagination (start/limit).

    `with_effort`: the RPE and feel of each activity (`perceived_effort`,
    `workout_feel`). The list endpoint has neither: one detail call per
    activity, in parallel. `effort_missing` gives the activities without RPE,
    and why (see `_add_effort`).
    """
    limit = min(max(1, limit), 100)

    if start_date and end_date:
        raw = client.get_activities_by_date(start_date, end_date, activity_type) or []
        answer = {"count": len(raw), "date_range": {"start": start_date, "end": end_date}}
    else:
        raw = client.get_activities(start, limit, activity_type or None) or []
        answer = {
            "start": start,
            "limit": limit,
            "count": len(raw),
            "has_more": len(raw) == limit,
            "next_start": start + limit if len(raw) == limit else None,
        }

    if with_effort:
        raw, missing = _add_effort(client, raw)
        activities = [LIST_EFFORT_FIELDS.curate(a) for a in raw]
    else:
        missing = {}
        activities = [LIST_FIELDS.curate(a) for a in raw]
    if include_hr_zones:
        _enrich_hr_zones(client, activities, raw)
    answer["activities"] = activities
    if missing:
        answer["effort_missing"] = missing
    return answer


def get_activity(client: Garmin, activity_id: int) -> dict:
    """One activity: the fields of `DETAIL_FIELDS`, with the weather at the start,
    and its stops and walks (Garmin's run / walk / stand detection)."""
    raw = client.get_activity(activity_id)
    if not raw:
        raise NotFound(f"No activity {activity_id}")
    return DETAIL_FIELDS.curate({
        **raw,
        "weather": _activity_weather(client, activity_id),
        "typedSplits": _typed_splits(client, activity_id),
    })


def _typed_splits(client: Garmin, activity_id: int) -> list[dict] | None:
    """Garmin's typed splits (workout intervals, run / walk / stand), or None when the
    call fails: the activity's other fields do not depend on it."""
    try:
        return (client.get_activity_typed_splits(activity_id) or {}).get("splits") or []
    except Exception as e:  # noqa: BLE001 — logged, the answer says nothing about stops
        error = as_garmin_error(e)
        if isinstance(error, AuthError):
            raise error from e
        logger.warning("Typed splits of activity %s not read: %s", activity_id, error)
        return None


SPLIT_MODES = ("lap", "interval", "run-walk", "km")
# Garmin's typed splits: `INTERVAL_*` = the workout's steps, `RWD_*` = run / walk / stand detection.
_TYPED_PREFIX = {"interval": "INTERVAL_", "run-walk": "RWD_"}


def get_activity_splits(client: Garmin, activity_id: int, by: str = "lap") -> dict:
    """The activity cut in parts.

    - `lap`: the watch's laps (`LAP_FIELDS`), `{activity_id, lap_count, laps}`;
    - `interval`: the workout's steps as run (warmup, active, recovery, cooldown);
    - `run-walk`: Garmin's run / walk / stand detection, with the totals per type;
    - `km`: one split per kilometre, computed from the FIT recording.
    The last three: `{activity_id, by, count, splits}`.
    """
    if by not in SPLIT_MODES:
        raise InvalidInput(f"Unknown split mode '{by}'. Valid: {', '.join(SPLIT_MODES)}")
    if by == "lap":
        return _laps(client, activity_id)
    if by == "km":
        splits = _km_splits(_fit_records(download_fit(client, activity_id)))
        return {"activity_id": activity_id, "by": by, "count": len(splits), "splits": splits}
    raw = (client.get_activity_typed_splits(activity_id) or {}).get("splits") or []
    typed = [t for t in raw if (t.get("type") or "").startswith(_TYPED_PREFIX[by])]
    typed.sort(key=lambda t: t.get("startTimeGMT") or "")
    fields = RUN_WALK_FIELDS if by == "run-walk" else INTERVAL_FIELDS
    answer = {"activity_id": activity_id, "by": by, "count": len(typed),
              "splits": [fields.curate(t) for t in typed]}
    if by == "run-walk":
        answer["totals"] = segment_totals(typed)
    return answer


def segment_totals(typed: list[dict]) -> dict:
    """Per type (run, walk, stand): number of segments, total and longest time, distance."""
    totals: dict[str, dict] = {}
    for t in typed:
        kind = split_type(t)
        duration = t.get("duration") or 0
        total = totals.setdefault(kind, {"count": 0, "duration_s": 0, "longest_s": 0, "distance_m": 0})
        total["count"] += 1
        total["duration_s"] += duration
        total["longest_s"] = max(total["longest_s"], duration)
        total["distance_m"] += t.get("distance") or 0
    return {kind: {k: round(v) for k, v in total.items()} for kind, total in totals.items()}


def _laps(client: Garmin, activity_id: int) -> dict:
    """Per-lap splits: the fields of `LAP_FIELDS`.

    Garmin's laps only have a GMT start. The activity detail gives the offset to
    local time, so a lap's `start_time` is local, as in `list` and `get`.
    """
    raw = client.get_activity_splits(activity_id) or {}
    laps = raw.get("lapDTOs") or []
    if laps:
        offset = _local_time_offset(client.get_activity(activity_id))
        if offset is not None:
            laps = [_with_local_start(lap, offset) for lap in laps]
    return {
        "activity_id": raw.get("activityId", activity_id),
        "lap_count": len(laps),
        "laps": [LAP_FIELDS.curate(lap) for lap in laps],
    }


def get_activity_hr_in_timezones(client: Garmin, activity_id: int) -> dict:
    """HR zone distribution for an activity: Garmin's list, one entry per zone."""
    return client.get_activity_hr_in_timezones(activity_id) or []


def get_activity_types(client: Garmin) -> dict:
    """All available activity type codes."""
    raw = client.get_activity_types() or []
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


def download_activity(client: Garmin, activity_id: int, path: str, fmt: str = "fit") -> dict:
    """Download activity and preprocess to pandas-ready CSV, written at `path`.

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
        raise InvalidInput(f"Unsupported format '{fmt}'. Use: fit, gpx, tcx")

    if fmt == "fit":
        return _fit_to_csv(download_fit(client, activity_id), activity_id, path)

    content = client.download_activity(str(activity_id), dl_fmt=format_map[fmt])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    size_kb = round(os.path.getsize(path) / 1024, 1)
    return {"activity_id": activity_id, "format": fmt, "path": path, "size_kb": size_kb}


def download_fit(client: Garmin, activity_id: int) -> bytes:
    """The activity's original FIT file, taken out of Garmin's zip. In memory only."""
    zip_bytes = client.download_activity(
        str(activity_id), dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL,
    )
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            fit_names = [n for n in zf.namelist() if n.endswith(".fit")]
            if not fit_names:
                raise Unavailable(f"Garmin's download of activity {activity_id} has no .fit file")
            return zf.read(fit_names[0])
    except zipfile.BadZipFile as e:
        raise Unavailable(f"Garmin's download of activity {activity_id} is not a valid zip: {e}")


_SEMICIRCLES_TO_DEG = 180.0 / (2 ** 31)


def _fit_records(fit_bytes: bytes) -> list[dict]:
    """The FIT's second-by-second records, cleaned: one row per record (see `download --help`)."""
    from fitparse import FitFile

    fit = FitFile(io.BytesIO(fit_bytes))

    # Detect sport — running cadence is RPM (×2 for SPM), cycling cadence stays as RPM
    sport = None
    for msg in fit.get_messages("sport"):
        sport = {f.name: f.value for f in msg.fields}.get("sport")
        break

    is_running = sport in ("running", "trail_running", "treadmill_running", None)
    cadence_label = "cadence_spm" if is_running else "cadence_rpm"
    cadence_multiplier = 2 if is_running else 1

    # The watch's laps: a record belongs to the last lap started at or before it.
    lap_starts = sorted(
        start for start in ({f.name: f.value for f in m.fields}.get("start_time") for m in fit.get_messages("lap"))
        if start is not None
    )

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
        row["lap"] = max(bisect.bisect_right(lap_starts, ts), 1) if lap_starts else None
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

    # Fix half-cadence glitch — running only (cycling 80rpm is valid)
    if is_running and rows:
        _fix_half_cadence_glitch(rows, cadence_label)
    return rows


def _fit_to_csv(fit_bytes: bytes, activity_id: int, csv_path: str) -> dict:
    """Parse the FIT records, write a clean CSV at `csv_path`."""
    import csv

    rows = _fit_records(fit_bytes)
    # A FIT without samples (a manual activity) gives an empty CSV: an empty answer, not an error.

    # Drop columns that are entirely None
    all_keys = list(rows[0].keys()) if rows else []
    drop_keys = {k for k in all_keys if all(r.get(k) is None for r in rows)}
    if drop_keys:
        for r in rows:
            for k in drop_keys:
                del r[k]

    # Write CSV
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    columns = [k for k in all_keys if k not in drop_keys]
    with open(csv_path, "w", newline="") as f:
        if columns:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    size_kb = round(os.path.getsize(csv_path) / 1024, 1)
    last = rows[-1] if rows else {}
    return clean_nones({
        "activity_id": activity_id,
        "format": "csv",
        "path": csv_path,
        "rows": len(rows),
        "columns": columns,
        "duration_s": last.get("elapsed_s"),
        "distance_m": last.get("distance_m"),
        "size_kb": size_kb,
    })


# Altitude changes below this are noise: the same gain and loss as Garmin's own
# laps (checked on two real runs: 40/48 m vs Garmin's 40/47, 94/101 vs 88/98).
_ELEVATION_STEP_M = 1.0


def _elevation(altitudes: list[float]) -> tuple[float, float]:
    """Gain and loss along altitudes, counting a change once it reaches `_ELEVATION_STEP_M`."""
    gain = loss = 0.0
    anchor = altitudes[0] if altitudes else None
    for altitude in altitudes[1:]:
        if altitude - anchor >= _ELEVATION_STEP_M:
            gain += altitude - anchor
            anchor = altitude
        elif anchor - altitude >= _ELEVATION_STEP_M:
            loss += anchor - altitude
            anchor = altitude
    return gain, loss


def _km_splits(rows: list[dict]) -> list[dict]:
    """One split per kilometre of the FIT's records (the last one shorter).

    The marks are at 1, 2, 3… km of the recorded distance. `duration_s` is the
    time between two marks, stops included; `avg_pace_s_per_km` follows from it.
    """
    points = [r for r in rows if r.get("distance_m") is not None]
    if len(points) < 2:
        return []
    origin = points[0]["distance_m"]
    splits = []
    first = 0
    for i in range(1, len(points)):
        if points[i]["distance_m"] - origin >= 1000 * (len(splits) + 1):
            splits.append(_km_split(len(splits) + 1, points[first:i + 1]))
            first = i
    if first < len(points) - 1 and points[-1]["distance_m"] > points[first]["distance_m"]:
        splits.append(_km_split(len(splits) + 1, points[first:]))
    return splits


def _km_split(number: int, rows: list[dict]) -> dict:
    start, end = rows[0], rows[-1]
    distance = end["distance_m"] - start["distance_m"]
    duration = end["elapsed_s"] - start["elapsed_s"]
    hr = [r["heart_rate"] for r in rows if r.get("heart_rate")]
    cadence = [r["cadence_spm"] for r in rows if r.get("cadence_spm")]
    altitudes = [r["altitude_m"] for r in rows if r.get("altitude_m") is not None]
    gain, loss = _elevation(altitudes)
    return clean_nones({
        "km": number,
        "distance_m": round(distance),
        "duration_s": round(duration),
        "avg_pace_s_per_km": round(duration / distance * 1000) if distance > 0 else None,
        "avg_hr_bpm": round(statistics.mean(hr)) if hr else None,
        "avg_cadence_spm": round(statistics.mean(cadence)) if cadence else None,
        "elevation_gain_m": round(gain) if altitudes else None,
        "elevation_loss_m": round(loss) if altitudes else None,
    })


# ── Private helpers ──────────────────────────────────────────────────────────


# Half-cadence glitch: a value within this share of half the cadence around it.
_CADENCE_HALF_TOLERANCE = 0.1
_CADENCE_WINDOW = 31  # samples (~30 s) around each one
_RUNNING_CADENCE_MIN = 140  # spm: below, the median itself is walking or standing


def _fix_half_cadence_glitch(rows: list[dict], key: str) -> None:
    """Fix wrist-based cadence sensor half-count glitch in-place.

    Some Garmin watches (e.g. FR165) count 1 step out of 2 when the wrist is
    raised: a value at half the cadence around it while running. Only such a
    value is doubled: a walk (100-120 spm) is a walk, not a glitch.
    Zero → None.
    """
    values = [r.get(key) for r in rows]
    half = _CADENCE_WINDOW // 2
    fixed = 0
    for i, val in enumerate(values):
        if val is None:
            continue
        if val == 0:
            rows[i][key] = None
            continue
        around = [v for v in values[max(0, i - half):i + half + 1] if v]
        median = statistics.median(around)
        if median >= _RUNNING_CADENCE_MIN and abs(2 * val - median) <= _CADENCE_HALF_TOLERANCE * median:
            rows[i][key] = val * 2
            fixed += 1
    if fixed:
        logger.info("Half-cadence fix: corrected %d points", fixed)


# `--with effort`: at most this many detail calls per list, this many at a time.
EFFORT_MAX_ACTIVITIES = 100
_EFFORT_WORKERS = 5


def _add_effort(client: Garmin, raw: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """Each list item with the `summaryDTO` of its detail (read by LIST_EFFORT_FIELDS),
    and the activities without RPE: `{"<id>": "no_data" | "error: …"}`.

    `no_data`: the athlete entered no RPE. `error: …`: the detail call failed; the
    other activities keep theirs. An auth error fails the list at once; so does
    a failure of every call.
    """
    if len(raw) > EFFORT_MAX_ACTIVITIES:
        raise InvalidInput(
            f"--with effort reads one detail per activity: {len(raw)} activities, "
            f"at most {EFFORT_MAX_ACTIVITIES}. Ask for a shorter range."
        )

    def detail(item: dict):
        try:
            return client.get_activity(item["activityId"]), None
        except Exception as e:  # noqa: BLE001 — one failed detail does not fail the list
            return None, as_garmin_error(e)

    with ThreadPoolExecutor(max_workers=_EFFORT_WORKERS) as pool:
        details = list(pool.map(detail, raw))

    errors = [error for _, error in details if error is not None]
    for error in errors:
        if isinstance(error, AuthError):
            raise error
    if raw and len(errors) == len(raw):
        raise errors[0]

    items, missing = [], {}
    for item, (found, error) in zip(raw, details):
        item = {**item, "summaryDTO": (found or {}).get("summaryDTO") or {}}
        items.append(item)
        if error is not None:
            missing[str(item["activityId"])] = error_reason(error)
        elif LIST_EFFORT_FIELDS.value("perceived_effort", item) is None:
            missing[str(item["activityId"])] = NO_DATA
    return items, missing


def _enrich_hr_zones(client: Garmin, activities: list[dict], raw: list[dict]) -> None:
    """Fetch HR zones per activity and embed as compact dict. Mutates activities in-place."""
    for activity, raw_a in zip(activities, raw):
        if activity.get("hr_zones_s"):
            continue  # Already has inline zones from list response
        activity_id = raw_a.get("activityId")
        if not activity_id:
            continue
        try:
            zones = client.get_activity_hr_in_timezones(activity_id)
            if zones:
                activity["hr_zones_s"] = {
                    f"z{z['zoneNumber']}": round(z.get("secsInZone", 0))
                    for z in sorted(zones, key=lambda z: z.get("zoneNumber", 0))
                    if z.get("zoneNumber")
                }
        except Exception:
            pass  # Skip zones for this activity, don't fail the batch


def _activity_weather(client: Garmin, activity_id: int) -> dict | None:
    """Garmin's raw weather at the start of the activity. Optional: never fails the detail."""
    try:
        return client.get_activity_weather(activity_id)
    except Exception:
        return None


def _local_time_offset(detail: dict | None) -> timedelta | None:
    """Local time − GMT at the start of the activity, from its detail."""
    summary = (detail or {}).get("summaryDTO") or {}
    local, gmt = summary.get("startTimeLocal"), summary.get("startTimeGMT")
    if not (local and gmt):
        return None
    return parse_time(local) - parse_time(gmt)


def _with_local_start(lap: dict, offset: timedelta) -> dict:
    """The lap with the `startTimeLocal` key that list and detail answers have (read by LAP_FIELDS)."""
    if not lap.get("startTimeGMT"):
        return lap
    return {**lap, "startTimeLocal": shift_time(lap["startTimeGMT"], offset)}
