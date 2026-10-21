"""
High-Level API — Domain Model for Garmin athlete coaching.

Every function returns a clean dict the LLM can reason about.
Composes with the garminconnect SDK (Layer 1) internally.

Modules:
    contract       — Output contract     (empty answers, unavailable, typed failures)
    fields         — Field registry      (names, units, raw keys; one rule for every command)
    clock          — The athlete's today (time zone)
    capabilities   — What the watch computes (not_supported_by_device)
    activities     — What have you done?  (list, detail, splits, FIT) — activity_fields
    health         — How are you?        (day summary, sleep, stress, HR, body battery…) — health_fields
    history        — Series              (daily wellness, reports, sleep, HR, VO2max) → CSV
    training       — How fit are you?     (VO2max, HRV, status, thresholds, records) — training_fields
    workouts       — Build a session      (readable format: workout_format; create, schedule…)
    calendar       — What's coming up?    (month, upcoming, races) — calendar_fields
    profile        — Who are you?         (profile, zones, devices)
    body           — Body measurements    (weigh-ins)
    gear           — Shoes and bikes
    geographic, geo_history, geo_runner — Places of a run, route history (geo-runner service)
"""
