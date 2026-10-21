"""
Profile & Devices API layer — curation logic.

Pure functions: (Garmin client, params) → dict.
Output contract (empty answers, failures): see `api/contract.py`.
"""

from garminconnect import Garmin
from garmin_mcp.api.contract import NO_DATA, Unavailable, unavailable
from garmin_mcp.utils import clean_nones


def get_full_name(client) -> str:
    """Return user's display name as a plain string."""
    name = client.get_full_name()
    if not name:
        # Stateless mode: full_name not populated during client creation.
        try:
            profile = client.garth.connectapi(
                "/userprofile-service/userprofile/profile"
            )
            if profile and isinstance(profile, dict):
                name = profile.get("fullName") or profile.get("displayName")
        except Exception:
            pass
    return str(name) if name else "Unknown"


def get_hr_zones(client: Garmin) -> dict:
    """The athlete's heart-rate and power zones, per sport, as set in Garmin Connect.

    `zones_bpm` / `zones_watts`: `[low, high]` of zone 1, 2… (a zone ends 1 below
    the next one; the last ends at the max heart rate, or is open). Power zones:
    running and cycling only (Garmin also keeps defaults for skiing, rowing…).
    """
    hr = [_hr_zones(z) for z in client.connectapi("/biometric-service/heartRateZones") or []]
    power = [_power_zones(z) for z in client.connectapi("/biometric-service/powerZones/sports/all") or []
             if (z.get("sport") or "").lower() in _POWER_SPORTS]
    hr, power = [z for z in hr if z], [z for z in power if z]
    if not hr and not power:
        return unavailable(NO_DATA)
    return {"hr_zones": hr, "power_zones": power}


def get_user_profile(client) -> dict:
    """Who the athlete is: name, location, body, birth date, VO2max, usual sleep, training days.

    Heart-rate and power zones: `get_hr_zones()`.
    """
    settings = client.get_user_profile()
    if not settings:
        raise Unavailable("Garmin returned no user settings")
    social = client.connectapi("/userprofile-service/socialProfile") or {}
    user = settings.get("userData") or {}
    sleep = settings.get("userSleep") or {}
    return clean_nones({
        "name": social.get("fullName"),
        "location": social.get("location"),
        "birth_date": user.get("birthDate"),
        "gender": user.get("gender"),
        "weight_kg": _safe_div(user.get("weight"), 1000),
        "height_cm": user.get("height"),
        "vo2_max_running": user.get("vo2MaxRunning"),
        "vo2_max_cycling": user.get("vo2MaxCycling"),
        "lactate_threshold_hr_bpm": user.get("lactateThresholdHeartRate"),
        "usual_bedtime": _clock(sleep.get("sleepTime")),
        "usual_wake_time": _clock(sleep.get("wakeTime")),
        "training_days": _days(user.get("availableTrainingDays")),
        "long_run_days": _days(user.get("preferredLongTrainingDays")),
        "measurement_system": user.get("measurementSystem"),
    })


def get_devices(client) -> dict:
    """Enriched device list with last-used and primary flags."""
    devices = client.get_devices()
    if not devices:
        return {"count": 0, "devices": []}

    # Fetch last-used and primary training device for enrichment
    last_used_id = None
    primary_id = None
    try:
        last_used = client.get_device_last_used()
        if last_used and isinstance(last_used, dict):
            last_used_id = last_used.get("deviceId")
    except Exception:
        pass

    try:
        primary = client.get_primary_training_device()
        if primary and isinstance(primary, dict):
            primary_id = primary.get("deviceId")
    except Exception:
        pass

    curated = []
    for d in devices:
        device_id = d.get("deviceId")
        curated.append(clean_nones({
            "device_id": device_id,
            "name": d.get("displayName") or d.get("productDisplayName"),
            "model": d.get("partNumber"),
            "serial_number": d.get("serialNumber"),
            "software_version": d.get("softwareVersionString"),
            "status": d.get("deviceStatusName"),
            "last_sync_time": d.get("lastSyncTime"),
            "battery_status": d.get("batteryStatus"),
            "device_type": d.get("deviceType"),
            "is_last_used": True if device_id and device_id == last_used_id else None,
            "is_primary_training": True if device_id and device_id == primary_id else None,
        }))

    return {"count": len(curated), "devices": curated}


# ── helpers ───────────────────────────────────────────────────────────────────

_POWER_SPORTS = ("running", "cycling")

_WEEK = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")


def _days(days: list | None) -> list[str] | None:
    """Garmin's unordered day names → in week order, lower case."""
    return [d.lower() for d in _WEEK if d in (days or [])] or None


def _clock(seconds: int | None) -> str | None:
    """Seconds after midnight → `HH:MM`."""
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}" if seconds is not None else None


def _zone_bounds(floors: list, top) -> list[list]:
    """`[low, high]` per zone from the zone floors: a zone ends 1 below the next floor.
    The floors stop at the first one not above the one before (Garmin writes 0 for an unused zone)."""
    used = []
    for floor in floors:
        if floor is None or (used and floor <= used[-1]):
            break
        used.append(floor)
    highs = [nxt - 1 for nxt in used[1:]] + [top]
    return [[low, high] for low, high in zip(used, highs)]


def _hr_zones(raw: dict) -> dict | None:
    floors = [raw.get(f"zone{i}Floor") for i in range(1, 6)]
    if floors[0] is None:
        return None
    return clean_nones({
        "sport": (raw.get("sport") or "").lower() or None,
        "method": (raw.get("trainingMethod") or "").lower() or None,
        "max_hr_bpm": raw.get("maxHeartRateUsed"),
        "resting_hr_bpm": raw.get("restingHeartRateUsed"),
        "lactate_threshold_hr_bpm": raw.get("lactateThresholdHeartRateUsed"),
        "zones_bpm": _zone_bounds(floors, raw.get("maxHeartRateUsed")),
    })


def _power_zones(raw: dict) -> dict | None:
    floors = [round(f) if f is not None else None for f in (raw.get(f"zone{i}Floor") for i in range(1, 8))]
    if floors[0] is None or not raw.get("functionalThresholdPower"):
        return None
    return clean_nones({
        "sport": (raw.get("sport") or "").lower() or None,
        "ftp_watts": round(raw["functionalThresholdPower"]),
        "zones_watts": _zone_bounds(floors, None),
    })


def _safe_div(value, divisor):
    """Safe division returning None if value is None."""
    if value is None:
        return None
    try:
        return round(float(value) / divisor, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
