"""
Gear API layer — shoes, bikes, accessories: usage curation.

Pure functions: (Garmin client, params) → dict.

Garmin splits gear data across two endpoints:
    - filterGear    → metadata   (name, type, retirement threshold, dates)
    - stats/{uuid}  → real usage  (accumulated distance, activity count)
This module merges both so the caller sees ONE gear object with real mileage.

Why this exists: filterGear alone exposes neither the accumulated distance nor
a usable name (Garmin leaves `displayName` null when the user typed a custom
make/model). Merging the stats endpoint + picking the right name field is the
whole point of this layer.
"""

from garmin_mcp.utils import clean_nones


def _resolve_profile_id(client) -> str | None:
    """The authenticated athlete's numeric profile id.

    Read from garth's cached profile — no extra API call once the client has
    resolved it (same source `profile info` reports as user_profile_id).
    """
    try:
        profile = getattr(client.garth, "profile", None)
        if isinstance(profile, dict) and profile.get("profileId"):
            return str(profile["profileId"])
    except Exception:
        pass
    return None


def _gear_name(g: dict) -> str | None:
    """Best human name for a gear.

    Priority: the user's explicit display name, then the custom make/model they
    typed in (Garmin stores that in `customMakeModel`), then the generic
    brand+model — but only if it isn't Garmin's "Other"/"Unknown …" placeholder.
    """
    make = g.get("gearMakeName")
    model = g.get("gearModelName")
    generic = " ".join(
        p for p in (make, model)
        if p and p != "Other" and not str(p).lower().startswith("unknown")
    )
    return g.get("displayName") or g.get("customMakeModel") or (generic or None)


def get_gear(client, user_profile_id: str | None = None) -> dict:
    """All gear (shoes, bikes) with REAL usage stats merged in.

    Args:
        client: Authenticated Garmin client.
        user_profile_id: Defaults to the authenticated athlete.

    Returns:
        {"count": int, "gear": [ {uuid, name, type, status, distance_km,
        activity_count, max_distance_km, wear_pct, date_retired} ]}
        wear_pct = distance_km / max_distance_km × 100 (100 ⇒ due for replacement).
    """
    if not user_profile_id:
        user_profile_id = _resolve_profile_id(client)
        if not user_profile_id:
            return {"error": "Could not resolve user profile id from auth context."}

    gear_list = client.get_gear(str(user_profile_id))
    if not gear_list:
        return {"count": 0, "gear": []}

    items = []
    for g in gear_list:
        uuid = g.get("uuid")
        try:
            stats = client.get_gear_stats(uuid) or {}
        except Exception:
            stats = {}

        distance_m = stats.get("totalDistance")
        max_m = g.get("maximumMeters")
        has_dist = isinstance(distance_m, (int, float))
        has_max = isinstance(max_m, (int, float))
        items.append(clean_nones({
            "uuid": uuid,
            "name": _gear_name(g),
            "type": g.get("gearTypeName"),
            "status": g.get("gearStatusName"),
            "distance_km": round(distance_m / 1000, 1) if has_dist else None,
            "activity_count": stats.get("totalActivities"),
            "max_distance_km": round(max_m / 1000, 1) if has_max else None,
            "wear_pct": round(distance_m / max_m * 100) if has_dist and has_max and max_m else None,
            "date_retired": (g.get("dateEnd") or "")[:10] or None,
        }))

    return {"count": len(items), "gear": items}
