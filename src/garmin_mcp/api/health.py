"""
Health & Wellness API — curated daily health data.

Pure functions: (Garmin client, params) → dict. Fields, names and units:
`api/health_fields.py`.
A day without data is `{"date", "available": False, "reason": "no_data"}`
(`not_supported_by_device` for a device feature, see `api/capabilities.py`);
failures are exceptions (see `api/contract.py`).
"""

from garminconnect import Garmin
from garmin_mcp.api import capabilities
from garmin_mcp.api.contract import (
    NO_DATA,
    AuthError,
    as_garmin_error,
    day_answer,
    error_reason,
    has_data,
    unavailable,
)
from garmin_mcp.api.fields import FieldSet
from garmin_mcp.api.health_fields import (
    BODY_BATTERY_FIELDS,
    HEART_RATE_FIELDS,
    HRV_FIELDS,
    READINESS_FIELDS,
    RESPIRATION_FIELDS,
    SLEEP_FIELDS,
    SNAPSHOT_READINESS,
    SNAPSHOT_SLEEP,
    SNAPSHOT_STATS,
    SPO2_FIELDS,
    STATS_FIELDS,
    STRESS_FIELDS,
    body_battery_events,
)


def _day(fields: FieldSet, date: str, raw) -> dict:
    """A one-day answer curated by `fields`, or `no_data`."""
    curated = fields.curate(raw) if raw else None
    if curated and "date" not in curated:
        curated = {"date": date, **curated}
    return day_answer(date, curated)


def get_stats(client: Garmin, date: str) -> dict:
    """The day's summary: steps, calories, heart rate, stress, body battery, SpO2, respiration.

    `synced_until`: only on a partial day (the watch has not sent its end yet).
    """
    return _day(STATS_FIELDS, date, client.get_user_summary(date))


def get_sleep(client: Garmin, date: str) -> dict:
    """The night that ends on `date`: score and its factors, phases, bedtime, need, HR, SpO2, HRV."""
    raw = client.get_sleep_data(date)
    return _day(SLEEP_FIELDS, date, raw if (raw or {}).get("dailySleepDTO") else None)


def get_stress(client: Garmin, date: str) -> dict:
    """The day's stress: mean, max, and the share of the measured time in each band."""
    return _day(STRESS_FIELDS, date, client.get_stress_data(date))


def get_heart_rate(client: Garmin, date: str) -> dict:
    """The day's heart rate: resting (and its 7-day mean), min, max, mean."""
    return _day(HEART_RATE_FIELDS, date, client.get_heart_rates(date))


def get_respiration(client: Garmin, date: str) -> dict:
    """The day's respiration, breaths per minute: awake, asleep, min, max."""
    return _day(RESPIRATION_FIELDS, date, client.get_respiration_data(date))


def get_spo2(client: Garmin, date: str) -> dict:
    """The day's SpO2: mean, lowest, last reading, during the sleep, 7-day mean."""
    return _day(SPO2_FIELDS, date, client.get_spo2_data(date))


def get_body_battery(client: Garmin, start_date: str, end_date: str) -> dict:
    """Body battery per day: low, high, charged, drained, Garmin's level, and the day's events."""
    days = []
    for raw in client.get_body_battery(start_date, end_date) or []:
        day = BODY_BATTERY_FIELDS.curate(raw)
        events = body_battery_events(raw)
        if events:
            day["events"] = events
        if has_data(day):
            days.append(day)
    return {"count": len(days), "days": days}


def get_training_readiness(client: Garmin, date: str) -> dict:
    """The morning's training readiness, its factors, and the last update of the day."""
    raw = _readiness(client.get_training_readiness(date))
    curated = READINESS_FIELDS.curate(raw) if raw else None
    if curated and raw.get("latest"):
        curated.update(raw["latest"])
    return capabilities.day_answer(client, capabilities.TRAINING_READINESS, date, curated)


def _readiness(raw) -> dict | None:
    """The reading of the morning (`inputContext` AFTER_WAKEUP_RESET, else the first of the day),
    with `latest` = the score of the day's last update when there is a later one.

    Garmin updates the readiness during the day (activity, rest): the morning's is
    the day's reference, the last one says where the athlete is now.
    """
    entries = [e for e in (raw if isinstance(raw, list) else [raw]) if isinstance(e, dict)]
    if not entries:
        return None
    entries.sort(key=lambda e: e.get("timestamp") or "")
    morning = next((e for e in entries if e.get("inputContext") == "AFTER_WAKEUP_RESET"), entries[0])
    last = entries[-1]
    if last is morning:
        return morning
    latest = READINESS_FIELDS.curate(last)
    return {**morning, "latest": {"latest_score": latest.get("score"), "latest_at": latest.get("measured_at")}}


def get_coaching_snapshot(client: Garmin, date: str) -> dict:
    """One-call daily overview: stats + sleep + readiness + HRV, each in short.

    The full section is its own command (`health stats`, `health sleep`,
    `health training-readiness`, `training hrv`).

    Each section is its curated data, or `{"available": False, "reason": …}`:
    `no_data` when Garmin has nothing for that day, `not_supported_by_device`
    when no device of the athlete computes it (readiness), `error: …` when its
    call failed. An auth error fails the snapshot at once; so does a failure of
    every section.

    The sections are fetched here, one call each, and not with the SDK's
    `get_coaching_snapshot`: it turns every error into `None`.
    """
    snapshot = {"date": date}
    errors = []
    for name, method, curate, feature in _SNAPSHOT_SECTIONS:
        try:
            raw = getattr(client, method)(date)
            curated = curate(raw) if raw else None
            if has_data(curated):
                snapshot[name] = curated
            else:
                reason = capabilities.missing_reason(client, feature) if feature else NO_DATA
                snapshot[name] = unavailable(reason)
        except Exception as e:
            error = as_garmin_error(e)
            if isinstance(error, AuthError):
                raise error from e
            errors.append(error)
            snapshot[name] = unavailable(error_reason(error))
    if len(errors) == len(_SNAPSHOT_SECTIONS):
        raise errors[0]
    return snapshot


def _snapshot_stats(raw: dict) -> dict:
    return {k: v for k, v in SNAPSHOT_STATS.curate(raw).items() if k != "date"}


def _snapshot_sleep(raw: dict) -> dict | None:
    return SNAPSHOT_SLEEP.curate(raw) if raw.get("dailySleepDTO") else None


def _snapshot_readiness(raw) -> dict | None:
    entry = _readiness(raw)
    return SNAPSHOT_READINESS.curate(entry) if entry else None


def _snapshot_hrv(raw: dict) -> dict:
    return {k: v for k, v in HRV_FIELDS.curate(raw).items() if k != "date"}


# (section, client method called with the date, curation, device feature or None) — in output order.
_SNAPSHOT_SECTIONS = (
    ("stats", "get_user_summary", _snapshot_stats, None),
    ("sleep", "get_sleep_data", _snapshot_sleep, None),
    ("training_readiness", "get_training_readiness", _snapshot_readiness, capabilities.TRAINING_READINESS),
    ("hrv", "get_hrv_data", _snapshot_hrv, None),
)
