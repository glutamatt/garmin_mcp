"""
Body API — weight measurements: read, add, delete.

Pure functions: (Garmin client, params) → dict. Empty is `{"count": 0, …}`;
failures are exceptions (see `api/contract.py`).

Raw keys checked on real answers (neural-runner `tests/garmin-fixtures/`): a
weigh-in's `date` is an epoch in ms, its day is `calendarDate`; weights and
masses are in grams.
"""

from __future__ import annotations

from garmin_mcp.utils import clean_nones


def _kg(grams: float | None) -> float | None:
    return round(grams / 1000, 1) if grams is not None else None


def _weigh_in(raw: dict) -> dict:
    return clean_nones({
        "date": raw.get("calendarDate"),
        "weight_kg": _kg(raw.get("weight")),
        "bmi": round(raw["bmi"], 1) if raw.get("bmi") is not None else None,
        "body_fat_percent": raw.get("bodyFat"),
        "body_water_percent": raw.get("bodyWater"),
        "bone_mass_kg": _kg(raw.get("boneMass")),
        "muscle_mass_kg": _kg(raw.get("muscleMass")),
        "source": raw.get("sourceType"),
    })


def get_weigh_ins(client, start_date: str, end_date: str) -> dict:
    """Weight measurements between two days, latest first."""
    raw = client.get_weigh_ins(start_date, end_date) or {}
    entries = [w for day in raw.get("dailyWeightSummaries") or [] for w in day.get("allWeightMetrics") or []]
    measurements = [_weigh_in(w) for w in entries]
    return {"from": start_date, "to": end_date, "count": len(measurements), "measurements": measurements}


def add_weight(client, weight: float, unit: str, local_time: str | None, gmt_time: str | None) -> dict:
    """Add a weight measurement, now or at the given time (local and GMT, both)."""
    if local_time and gmt_time:
        client.add_weigh_in_with_timestamps(
            weight=weight, unitKey=unit, dateTimestamp=local_time, gmtTimestamp=gmt_time,
        )
    else:
        client.add_weigh_in(weight=weight, unitKey=unit)
    return clean_nones({"status": "added", "weight": weight, "unit": unit, "time": local_time})


def delete_weight(client, date: str, delete_all: bool) -> dict:
    """Delete the weight measurements of a day (all, or the latest one)."""
    client.delete_weigh_ins(date, delete_all=delete_all)
    return {"status": "deleted", "date": date}
