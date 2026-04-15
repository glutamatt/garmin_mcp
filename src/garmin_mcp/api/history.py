"""
Long-Term History API — historical time-series for trend analysis.

Pure functions: (Garmin client, start_date, end_date) → list[dict].
Each dict is one row (flat scalars) suitable for CSV/pandas.

Design principle: max fields, max precision. Aggregated reports pass
`standardizedUnits=false` so values come back in Garmin internal units
(distance in cm, duration in ms, speed in m/s) — lossless, convert in pandas.

Backs the `garmin history` CLI group. Uses ranged endpoints discovered via
HAR capture of the Garmin Connect web UI. Daily endpoints with 28-day server
caps are chunked + parallelized.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

from garminconnect import Garmin


logger = logging.getLogger(__name__)


# Concurrency for daily-sampled endpoints. 8 parallel is well below Garmin's
# per-user rate limits while keeping 365 calls under ~1 minute.
_DAILY_WORKERS = 8


# ── Sport-level aggregated reports (Garmin "Reports" UI endpoint) ───────────

# /fitnessstats-service/activity aggregation values seen in the Garmin web UI.
VALID_AGGREGATIONS = ("daily", "weekly", "monthly", "yearly", "lifetime")

# The exact metric list Garmin's own web UI sends — verbatim from HAR capture
# (both running and cycling Reports pages). Garmin doesn't tailor per sport;
# it sends everything, server returns only metrics that have data for the
# filtered sport (empty columns come back with count=0).
_GARMIN_UI_METRICS: tuple[str, ...] = (
    "duration", "distance", "movingDuration",
    "splitSummaries.noOfSplits.CLIMB_ACTIVE",
    "splitSummaries.duration.CLIMB_ACTIVE",
    "splitSummaries.totalAscent.CLIMB_ACTIVE",
    "splitSummaries.maxElevationGain.CLIMB_ACTIVE",
    "splitSummaries.numClimbsAttempted.CLIMB_ACTIVE",
    "splitSummaries.numClimbsCompleted.CLIMB_ACTIVE",
    "splitSummaries.numClimbSends.CLIMB_ACTIVE",
    "splitSummaries.numFalls.CLIMB_ACTIVE",
    "calories", "elevationGain", "elevationLoss",
    "avgSpeed", "maxSpeed", "avgGradeAdjustedSpeed",
    "avgHr", "maxHr",
    "avgRunCadence", "maxRunCadence",
    "avgBikeCadence", "maxBikeCadence",
    "avgWheelchairCadence", "maxWheelchairCadence",
    "avgPower", "maxPower",
    "avgVerticalOscillation", "avgGroundContactTime", "avgStrideLength",
    "avgStress", "maxStress",
    "splitSummaries.duration.CLIMB_REST",
    "beginPackWeight", "steps",
)

# Sports we expose as CLI subcommands. Value = `activityType` query param +
# response `stats` dict key (both always lowercase sport name).
VALID_SPORTS: tuple[str, ...] = ("running", "cycling")


# ── Utilities ────────────────────────────────────────────────────────────────


def _daterange(start: str, end: str) -> list[str]:
    """Inclusive list of YYYY-MM-DD strings from start to end."""
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    if e < s:
        return []
    out = []
    cur = s
    while cur <= e:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def default_window(days: int = 365) -> tuple[str, str]:
    """Default (start, end) window: `days` back from today, inclusive."""
    today = date.today()
    start = today - timedelta(days=days)
    return start.isoformat(), today.isoformat()


def _flatten(d: dict, prefix: str = "") -> dict:
    """Flatten one level of nested dicts; drop nested lists.

    Garmin summaries expose ~100 scalar fields + nested {activityType, eventType}
    dicts with a few more scalars. We keep it flat for CSV consumption.
    """
    out: dict = {}
    if not isinstance(d, dict):
        return out
    for k, v in d.items():
        key = f"{prefix}{k}" if prefix else k
        if isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, (dict, list)):
                    continue
                out[f"{key}_{kk}"] = vv
        elif isinstance(v, list):
            continue  # lists (laps, split summaries) pollute CSV; use dedicated endpoints
        else:
            out[key] = v
    return out


def _sample_daily(
    client: Garmin,
    start_date: str,
    end_date: str,
    fetch_one,
    *,
    workers: int = _DAILY_WORKERS,
) -> list[dict]:
    """Fetch `fetch_one(client, date_str)` for every day in the range.

    Days that 404 / return None / raise are skipped (logged at debug).
    Rows are returned sorted by `date` (or calendarDate) ascending.
    """
    days = _daterange(start_date, end_date)
    rows: list[dict] = []

    def _one(d: str):
        try:
            r = fetch_one(client, d)
            return d, r
        except Exception as e:  # noqa: BLE001 — per-day failures are non-fatal
            logger.debug("history: sample %s failed: %s", d, e)
            return d, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, d) for d in days]
        for fut in as_completed(futures):
            d, r = fut.result()
            if not r:
                continue
            if isinstance(r, list):
                for item in r:
                    row = _flatten(item)
                    row.setdefault("date", d)
                    rows.append(row)
            elif isinstance(r, dict):
                row = _flatten(r)
                row.setdefault("date", d)
                rows.append(row)

    rows.sort(key=lambda x: str(x.get("date") or x.get("calendarDate") or ""))
    return rows


# ── Public API ───────────────────────────────────────────────────────────────


def get_sport_stats(
    client: Garmin,
    sport: str,
    start_date: str,
    end_date: str,
    aggregation: str = "weekly",
) -> list[dict]:
    """Garmin "Reports" endpoint — aggregated stats per period for one sport.

    Hits `/fitnessstats-service/activity` (same endpoint the Garmin web UI
    uses when you open Reports → Running/Cycling → Group by Week/Month).

    Returns one row per period, with metric 5-tuples flattened to columns:
    {date, countOfActivities, distance_count, distance_min, distance_max,
     distance_avg, distance_sum, avgHr_avg, avgHr_max, ...}.

    Units are Garmin-internal (lossless, `standardizedUnits=false`):
      - distance / elevation: cm  (÷100 → m)
      - duration: ms               (÷1000 → s)
      - speed: m/s
      - cadence: spm (running) / rpm (cycling)
    """
    if sport not in VALID_SPORTS:
        raise ValueError(f"Unknown sport '{sport}'. Valid: {VALID_SPORTS}")
    if aggregation not in VALID_AGGREGATIONS:
        raise ValueError(
            f"Unknown aggregation '{aggregation}'. Valid: {VALID_AGGREGATIONS}"
        )

    params: dict = {
        "aggregation": aggregation,
        "groupByParentActivityType": "true",
        "groupByEventType": "false",
        "activityType": sport,
        "userFirstDay": "monday",
        "startDate": start_date,
        "endDate": end_date,
        "standardizedUnits": "false",
        # list → repeated `metric=...` query params (verbatim Garmin web UI list)
        "metric": list(_GARMIN_UI_METRICS),
    }
    raw = client.connectapi("/fitnessstats-service/activity", params=params)
    if not raw:
        return []

    entries = raw if isinstance(raw, list) else [raw]
    sport_key = sport
    rows: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        row = {
            "date": entry.get("date"),
            "countOfActivities": entry.get("countOfActivities"),
        }
        metrics = (entry.get("stats") or {}).get(sport_key) or {}
        for metric_name, agg in metrics.items():
            if not isinstance(agg, dict):
                continue
            # 5-tuple {count, min, max, avg, sum} → flat columns
            for stat_key in ("count", "min", "max", "avg", "sum"):
                if stat_key in agg:
                    row[f"{metric_name}_{stat_key}"] = agg[stat_key]
        rows.append(row)

    rows.sort(key=lambda r: str(r.get("date") or ""))
    return rows


# Garmin's `/sleep-service/stats/sleep/daily/<start>/<end>` endpoint hard-caps
# at 28-day windows (verified by binary-search — 29+ returns 400). For longer
# ranges we chunk and merge. This matches what the Garmin web UI does when
# paging through the "4 Weeks" / "1 Year" sleep views.
_SLEEP_MAX_WINDOW_DAYS = 28


def _chunk_range(start: str, end: str, chunk_days: int) -> list[tuple[str, str]]:
    """Split [start, end] inclusive into chunks of at most `chunk_days`."""
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    chunks = []
    cur = s
    while cur <= e:
        chunk_end = min(cur + timedelta(days=chunk_days - 1), e)
        chunks.append((cur.isoformat(), chunk_end.isoformat()))
        cur = chunk_end + timedelta(days=1)
    return chunks


def get_sleep(client: Garmin, start_date: str, end_date: str) -> list[dict]:
    """One row per day: sleep score, phases, RHR, HRV, SpO2, respiration, bedtime, skin temp.

    Uses Garmin's `/sleep-service/stats/sleep/daily/<start>/<end>` endpoint
    (same as the web UI's "4 Weeks" sleep view) chunked in 28-day windows.
    Raw Garmin field names passed through verbatim — no renaming.

    Unit quirks (documented in SKILL.md):
      - `sleepNeed`: MINUTES (despite no unit suffix in the name)
      - phase times (`deepTime`, `lightTime`, `remTime`, `awakeTime`): seconds
      - `totalSleepTimeInSeconds`: seconds (per name)
      - `localSleep*InMillis` / `gmtSleep*InMillis`: Unix epoch ms
      - `avgOvernightHrv` / `hrv7dAverage`: ms
    """
    chunks = _chunk_range(start_date, end_date, _SLEEP_MAX_WINDOW_DAYS)

    def _fetch(chunk: tuple[str, str]):
        s, e = chunk
        try:
            return client.connectapi(f"/sleep-service/stats/sleep/daily/{s}/{e}")
        except Exception as exc:  # noqa: BLE001 — per-chunk failures are non-fatal
            logger.debug("history sleep: chunk %s..%s failed: %s", s, e, exc)
            return None

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=_DAILY_WORKERS) as pool:
        for resp in pool.map(_fetch, chunks):
            if not resp:
                continue
            for entry in (resp.get("individualStats") or []):
                values = entry.get("values") or {}
                rows.append({
                    "date": entry.get("calendarDate"),
                    **values,
                })

    rows.sort(key=lambda r: str(r.get("date") or ""))
    # Dedupe on date (chunk boundaries shouldn't overlap, but guard anyway)
    seen: set[str] = set()
    deduped = []
    for r in rows:
        d = r.get("date") or ""
        if d in seen:
            continue
        seen.add(d)
        deduped.append(r)
    return deduped


HEART_RATE_AGGREGATIONS = ("daily", "weekly")

# Same 28-day cap as /sleep-service/stats/sleep/daily (verified by binary search).
_HEART_RATE_DAILY_MAX_WINDOW = 28
# Weekly endpoint accepts up to 52 weeks per call (100 fails).
_HEART_RATE_WEEKLY_MAX_WEEKS = 52


def get_heart_rate(
    client: Garmin,
    start_date: str,
    end_date: str,
    aggregation: str = "daily",
) -> list[dict]:
    """Heart-rate trend via Garmin Connect web UI endpoints.

    Endpoints (both undocumented in python-garminconnect, discovered via HAR):
      - `daily`:  `/usersummary-service/stats/heartRate/daily/{start}/{end}` (28-day cap,
                  chunked + parallelized for longer ranges)
      - `weekly`: `/usersummary-service/stats/heartRate/weekly/{endDate}/{weeks}` (52-week cap)

    Daily rows: `{date, restingHR, wellnessMaxAvgHR, wellnessMinAvgHR}`.
    Weekly rows: `{date, avgRestingHR, wellnessMaxAvgHR, wellnessMinAvgHR}` (week start).

    Raw Garmin field names passed through (camelCase). All in bpm.
    """
    if aggregation not in HEART_RATE_AGGREGATIONS:
        raise ValueError(
            f"Unknown aggregation '{aggregation}'. Valid: {HEART_RATE_AGGREGATIONS}"
        )

    if aggregation == "weekly":
        weeks = min(len(_daterange(start_date, end_date)) // 7 + 1, _HEART_RATE_WEEKLY_MAX_WEEKS)
        path = f"/usersummary-service/stats/heartRate/weekly/{end_date}/{weeks}"
        try:
            resp = client.connectapi(path)
        except Exception as e:  # noqa: BLE001
            logger.debug("history heart-rate weekly fetch failed: %s", e)
            return []
        if not resp:
            return []
        rows = []
        for entry in resp:
            if not isinstance(entry, dict):
                continue
            values = entry.get("values") or {}
            rows.append({"date": entry.get("calendarDate"), **values})
        rows.sort(key=lambda r: str(r.get("date") or ""))
        return rows

    # daily: chunk + parallelize, same pattern as get_sleep
    chunks = _chunk_range(start_date, end_date, _HEART_RATE_DAILY_MAX_WINDOW)

    def _fetch(chunk: tuple[str, str]):
        s, e = chunk
        try:
            return client.connectapi(
                f"/usersummary-service/stats/heartRate/daily/{s}/{e}"
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("history heart-rate: chunk %s..%s failed: %s", s, e, exc)
            return None

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=_DAILY_WORKERS) as pool:
        for resp in pool.map(_fetch, chunks):
            if not resp:
                continue
            for entry in resp:
                if not isinstance(entry, dict):
                    continue
                values = entry.get("values") or {}
                rows.append({"date": entry.get("calendarDate"), **values})

    rows.sort(key=lambda r: str(r.get("date") or ""))
    seen: set[str] = set()
    deduped = []
    for r in rows:
        d = r.get("date") or ""
        if d in seen:
            continue
        seen.add(d)
        deduped.append(r)
    return deduped


VO2MAX_AGGREGATIONS = ("daily", "weekly", "monthly")


def get_vo2max(
    client: Garmin,
    start_date: str,
    end_date: str,
    aggregation: str = "daily",
) -> list[dict]:
    """VO2max history for running + cycling via the Garmin Connect web UI endpoint.

    Endpoint: `/metrics-service/metrics/maxmet/{daily|weekly|monthly}/{start}/{end}?sport=<s>`.
    One call per sport (2 total). Empty sports return no rows.

    Response per entry: `{generic: {calendarDate, vo2MaxValue, vo2MaxPreciseValue,
    fitnessAge, fitnessAgeDescription, maxMetCategory}, cycling, heatAltitudeAcclimation}`.
    We extract the `generic` object and tag with the requested sport.

    Fields passed through verbatim (Garmin camelCase). No unit conversions
    needed — VO2max is ml/kg/min (float), fitnessAge is years (often null).
    """
    if aggregation not in VO2MAX_AGGREGATIONS:
        raise ValueError(
            f"Unknown aggregation '{aggregation}'. Valid: {VO2MAX_AGGREGATIONS}"
        )

    rows: list[dict] = []
    for sport in ("running", "cycling"):
        path = f"/metrics-service/metrics/maxmet/{aggregation}/{start_date}/{end_date}"
        try:
            resp = client.connectapi(path, params={"sport": sport})
        except Exception as e:  # noqa: BLE001 — non-fatal per sport
            logger.debug("history vo2max: %s fetch failed: %s", sport, e)
            continue
        if not resp:
            continue
        for entry in resp:
            if not isinstance(entry, dict):
                continue
            generic = entry.get("generic") or {}
            if not generic.get("calendarDate"):
                continue
            rows.append({
                "date": generic.get("calendarDate"),
                "sport": sport,
                "vo2MaxValue": generic.get("vo2MaxValue"),
                "vo2MaxPreciseValue": generic.get("vo2MaxPreciseValue"),
                "fitnessAge": generic.get("fitnessAge"),
                "fitnessAgeDescription": generic.get("fitnessAgeDescription"),
                "maxMetCategory": generic.get("maxMetCategory"),
            })

    rows.sort(key=lambda r: (r["date"], r["sport"]))
    return rows


def get_race_predictions(
    client: Garmin, start_date: str, end_date: str
) -> list[dict]:
    """One row per day: 5K / 10K / half-marathon / marathon predicted times (seconds)."""
    raw = client.get_race_predictions(
        startdate=start_date, enddate=end_date, _type="daily"
    )
    if not raw:
        return []
    if isinstance(raw, dict):
        raw = [raw]

    rows = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        rows.append({
            "date": r.get("calendarDate") or r.get("fromCalendarDate") or r.get("date"),
            "race_5k_seconds": r.get("time5K"),
            "race_10k_seconds": r.get("time10K"),
            "race_half_marathon_seconds": r.get("timeHalfMarathon"),
            "race_marathon_seconds": r.get("timeMarathon"),
        })
    rows.sort(key=lambda x: str(x.get("date") or ""))
    return rows
