"""
Profile & Devices API layer — curation logic.

Pure functions: (Garmin client, params) → dict.
Merges user_profile + settings + unit_system + devices into 3 calls.
"""

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


def get_user_profile(client) -> dict:
    """Enriched user profile: profile + settings + unit system in one response."""
    profile = client.get_user_profile()
    if not profile:
        return {"error": "No user profile found"}

    result = clean_nones({
        "user_profile_id": profile.get("id"),
        "display_name": profile.get("displayName"),
        "profile_image_url": profile.get("profileImageUrlLarge") or profile.get("profileImageUrlMedium"),
        "location": profile.get("location"),
        "bio": profile.get("aboutMe"),
    })

    # User data is inside the profile response, not settings
    user_data = profile.get("userData", {})
    if user_data:
        result["settings"] = clean_nones({
            "weight_kg": _safe_div(user_data.get("weight"), 1000),
            "height_cm": user_data.get("height"),
            "birth_date": user_data.get("birthDate"),
            "gender": user_data.get("gender"),
            "activity_level": user_data.get("activityLevel"),
            "handedness": user_data.get("handedness"),
            "vo2_max_running": user_data.get("vo2MaxRunning"),
            "vo2_max_cycling": user_data.get("vo2MaxCycling"),
            "lactate_threshold_hr": user_data.get("lactateThresholdHeartRate"),
            "training_status_paused": user_data.get("trainingStatusPaused"),
        })

        # HR zones if present
        hr_zones = user_data.get("heartRateZones")
        if hr_zones and isinstance(hr_zones, list):
            result["hr_zones"] = [
                clean_nones({
                    "zone": z.get("zoneNumber"),
                    "low_bpm": z.get("startBPM"),
                    "high_bpm": z.get("endBPM"),
                })
                for z in hr_zones
            ]

        # Power zones if present
        power_zones = user_data.get("powerZones")
        if power_zones and isinstance(power_zones, list):
            result["power_zones"] = [
                clean_nones({
                    "zone": z.get("zoneNumber"),
                    "low_watts": z.get("zoneLowBoundary"),
                    "high_watts": z.get("zoneHighBoundary"),
                })
                for z in power_zones
            ]

    # Merge unit system
    try:
        unit_system = client.get_unit_system()
        if unit_system:
            result["unit_system"] = unit_system
    except Exception:
        pass

    return result


def get_devices(client) -> dict:
    """Enriched device list with last-used and primary flags."""
    devices = client.get_devices()
    if not devices:
        return {"error": "No devices found"}

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

def _safe_div(value, divisor):
    """Safe division returning None if value is None."""
    if value is None:
        return None
    try:
        return round(float(value) / divisor, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
