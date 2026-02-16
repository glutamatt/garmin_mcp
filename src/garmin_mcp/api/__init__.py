"""
High-Level API — Domain Model for Garmin athlete coaching.

Every function returns a clean dict the LLM can reason about.
Composes with the garminconnect SDK (Layer 1) internally.

Modules:
    health      — How are you?        (stats, sleep, stress, HR, body battery, SpO2, respiration)
    activities  — What have you done?  (past sessions, laps, HR zones)
    training    — How fit are you?     (VO2, HRV, training status, goals, race predictions)
    workouts    — Build a session      (create, update, schedule, delete)
    profile     — Who are you?         (profile, settings, devices)
    calendar    — What's coming up?    (calendar items, race events)
    body_data   — Body measurements    (weight, body composition, BP, hydration)
"""
