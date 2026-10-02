"""
Readable workout format — the one an agent writes and reads — and Garmin's native JSON.

`workouts create` / `update` take it and `workouts get` gives it (`--raw`: Garmin's
own JSON), so get → edit → create works as is:

    {"name": "Easy 45", "sport": "running", "description": "Relaxed",
     "steps": [
       {"warmup": "10:00"},
       {"run": "30:00", "pace": "5:30-6:00", "note": "nose breathing"},
       {"repeat": 6, "steps": [{"run": "200m", "pace": "4:30"}, {"recover": "1:00"}]},
       {"cooldown": "lap"}]}

A step is one kind word (`warmup`, `run`, `recover`, `rest`, `cooldown`, `other`).
Its value says when the step ends: a duration "m:ss" or "h:mm:ss", a distance
"1km" / "1.5km" / "200m", or "lap" (lap button). A step can have one target
(`pace`, `hr`, `hr_zone`, `cadence`) and a `note`, shown on the watch.

Conventions, decided here once:
- `pace` is min:ss per km; Garmin stores m/s. Garmin Connect puts the FASTER
  bound first (`targetValueOne`, the higher m/s): checked on a pace range made
  in Garmin Connect. The bounds can be written in any order. One value ("4:30")
  is a range of one pace.
- `hr` (bpm) and `cadence` (steps/min running, rpm cycling): the LOWER bound
  first, as Garmin Connect does (checked on a heart-rate range made there).
- `repeat` does all its steps n times, like Garmin Connect. With
  `"skip_last_recover": true`, the last round ends before its final recover
  (or rest) step.

Anything else is invalid input (exit 2), with the valid words: no silent
fallback to another step kind, end or target. `from_garmin` says what a
Garmin workout has that this format cannot say (`not_readable`, `warnings`).

Pure functions: no Garmin call here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from garmin_mcp.api.contract import InvalidInput

# ── Vocabulary ───────────────────────────────────────────────────────────────

SPORTS = {
    "running": {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
    "cycling": {"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2},
}

# Step kind word → Garmin step type (id = displayOrder).
STEP_KINDS = {
    "warmup": ("warmup", 1),
    "run": ("interval", 3),
    "recover": ("recovery", 4),
    "rest": ("rest", 5),
    "cooldown": ("cooldown", 2),
    "other": ("other", 7),
}
_KIND_OF_STEP_TYPE = {key: word for word, (key, _) in STEP_KINDS.items()}
_REPEAT_TYPE = {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6}
# Garmin skips this kind of step at the end of the last round (`skipLastRestStep`).
_RECOVER_KINDS = ("recovery", "rest")

_LAP = "lap"
_END_CONDITIONS = {
    _LAP: {"conditionTypeId": 1, "conditionTypeKey": "lap.button", "displayOrder": 1, "displayable": True},
    "time": {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True},
    "distance": {"conditionTypeId": 3, "conditionTypeKey": "distance", "displayOrder": 3, "displayable": True},
}
_ITERATIONS = {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False}

_NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
_PACE_TARGET = {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone", "displayOrder": 6}
_HR_TARGET = {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 4}
_CADENCE_TARGET = {"workoutTargetTypeId": 3, "workoutTargetTypeKey": "cadence", "displayOrder": 3}

TARGETS = ("pace", "hr", "hr_zone", "cadence")
_STEP_OPTIONS = (*TARGETS, "note")
_REPEAT_KEYS = ("repeat", "steps", "skip_last_recover")
WORKOUT_KEYS = ("name", "sport", "description", "steps")
# Keys of the `workouts get` answer that are not part of the workout: ignored on input.
READ_ONLY_KEYS = ("id", "estimated_duration_s", "estimated_distance_m",
                  "created_date", "updated_date", "provider", "warnings")
NOT_READABLE = "not_readable"

# Garmin's own keys: a native workout is refused with a pointer to this format.
_NATIVE_WORKOUT_KEYS = {"workoutName", "sportType", "workoutSegments", "workoutSteps", "segments"}
_NATIVE_STEP_KEYS = {"stepType", "endCondition", "endConditionValue", "targetType",
                     "targetValueOne", "targetValueTwo", "zoneNumber", "stepOrder",
                     "numberOfIterations", "workoutSteps"}

# Bounds that catch a unit mistake (ms for s, a pace in m/s), not a hard limit of Garmin.
MAX_STEP_S = 10 * 3600
MAX_STEP_M = 500_000
PACE_S_PER_KM = (120, 1200)  # 2:00 to 20:00 /km
HR_BPM = (30, 230)
CADENCE = (20, 250)
HR_ZONES = (1, 5)
MAX_REPEAT = 99

_DURATION = re.compile(r"^(?:(\d+):)?(\d+):(\d\d)$")
_DISTANCE = re.compile(r"^(\d+(?:\.\d+)?)\s*(km|m)$", re.IGNORECASE)
_PACE = re.compile(r"^(\d{1,2}):(\d\d)$")
_RANGE = re.compile(r"^(\d+)\s*-\s*(\d+)$")

_END_HELP = '"m:ss" or "h:mm:ss", a distance like "1km" or "200m", or "lap"'
_KINDS_HELP = ", ".join(STEP_KINDS)

FORMAT_HELP = f"""\
\b
Readable format (the one `workouts get` gives):
  {{"name": "Easy 45", "sport": "running", "description": "...",
   "steps": [{{"warmup": "5:00"}},
             {{"run": "30:00", "pace": "5:30-6:00", "note": "relaxed"}},
             {{"repeat": 6, "steps": [{{"run": "200m", "pace": "4:30"}},
                                    {{"recover": "1:00"}}]}},
             {{"cooldown": "lap"}}]}}
  sport: {", ".join(SPORTS)}
  step: one of {_KINDS_HELP}; its value = when it ends:
        {_END_HELP} (lap button)
  target, one per step:
        pace "m:ss-m:ss" or "m:ss", per km (running; the code orders the bounds)
        hr "140-150" (bpm) | hr_zone 1-5 | cadence "170-180" (spm, rpm on a bike)
  note: text shown on the watch during the step
  repeat: {{"repeat": n, "steps": [...]}}; "skip_last_recover": true ends the
        last round before its final recover/rest step
Keys of `workouts get` that are not the workout (id, estimated_*, ...) are ignored.
An unknown word is an error (exit 2) that lists the valid ones."""


# ── Readable → Garmin ────────────────────────────────────────────────────────


class _Errors:
    """Every problem of an input, with where it is (`steps[2].pace`), raised at once."""

    def __init__(self):
        self.items: list[str] = []

    def add(self, path: str, message: str):
        self.items.append(f"{path}: {message}" if path else message)

    def raise_any(self):
        if self.items:
            lines = "\n".join(f"- {item}" for item in self.items)
            raise InvalidInput(f"Invalid workout ({len(self.items)} error{'s' * (len(self.items) > 1)}):\n{lines}")


def to_garmin(workout) -> dict:
    """Garmin's native JSON for a readable workout, with its estimated duration and distance.

    Raises `InvalidInput` (exit 2) with every error found.
    """
    errors = _Errors()
    if not isinstance(workout, dict):
        errors.add("", f"a workout is a JSON object, got {type(workout).__name__}")
        errors.raise_any()
    native_keys = sorted(_NATIVE_WORKOUT_KEYS & workout.keys())
    if native_keys:
        errors.add("", f"{', '.join(native_keys)}: Garmin's native format is not accepted. "
                       "Write the readable format (`help workouts create`); "
                       "`workouts get <id>` shows a workout in it")
        errors.raise_any()
    for key in workout:
        if key not in WORKOUT_KEYS and key not in READ_ONLY_KEYS:
            errors.add(key, f"unknown key; valid: {', '.join(WORKOUT_KEYS)}")

    name = workout.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.add("name", "required, a non-empty string")
    description = workout.get("description")
    if description is not None and not isinstance(description, str):
        errors.add("description", "a string")
    sport = workout.get("sport")
    if sport not in SPORTS:
        errors.add("sport", f"{'required' if sport is None else repr(sport) + ' unknown'}; valid: {', '.join(SPORTS)}")
        sport = None

    steps = workout.get("steps")
    native_steps = []
    if not isinstance(steps, list) or not steps:
        errors.add("steps", 'required, a non-empty list of steps, like [{"run": "30:00"}]')
    else:
        order = [0]
        native_steps = [_parse_step(step, f"steps[{i}]", sport, errors, order) for i, step in enumerate(steps)]
    errors.raise_any()

    sport_type = SPORTS[sport]
    native = {
        "workoutName": name.strip(),
        "sportType": dict(sport_type),
        "workoutSegments": [{"segmentOrder": 1, "sportType": dict(sport_type), "workoutSteps": native_steps}],
    }
    if description:
        native["description"] = description
    if sport == "running":
        native["isWheelchair"] = False
    totals = estimate(native_steps)
    if totals.duration_s is not None:
        native["estimatedDurationInSecs"] = totals.duration_s
    if totals.distance_m is not None:
        native["estimatedDistanceInMeters"] = float(totals.distance_m)
    return native


def _next_order(order: list[int]) -> int:
    """Garmin numbers the steps depth-first: a repeat, then its steps, then the next step."""
    order[0] += 1
    return order[0]


def _parse_step(step, path: str, sport: str | None, errors: _Errors, order: list[int],
                in_repeat: bool = False) -> dict | None:
    if not isinstance(step, dict):
        errors.add(path, 'a step is an object, like {"run": "5:00"}')
        return None
    if "repeat" in step:
        if in_repeat:
            errors.add(path, "a repeat cannot hold another repeat")
            return None
        return _parse_repeat(step, path, sport, errors, order)
    if NOT_READABLE in step:
        errors.add(path, f"this step uses what the readable format cannot say ({_join(step[NOT_READABLE])}): "
                         "remove the step or change it in Garmin Connect")
        return None
    native_keys = sorted(_NATIVE_STEP_KEYS & step.keys())
    if native_keys:
        errors.add(path, f"{', '.join(native_keys)}: Garmin's native format; a step is "
                         f'{{"<kind>": <end>, <target>, "note"}}, kind one of {_KINDS_HELP}')
        return None

    kinds = [key for key in step if key in STEP_KINDS]
    unknown = [key for key in step if key not in STEP_KINDS and key not in _STEP_OPTIONS]
    for key in unknown:
        errors.add(f"{path}.{key}", f"unknown key; a step has one kind ({_KINDS_HELP}), "
                                    f"at most one target ({', '.join(TARGETS)}) and a note")
    if not kinds and unknown:
        return None
    if len(kinds) != 1:
        errors.add(path, f"{'no step kind' if not kinds else 'several kinds: ' + ', '.join(kinds)}; "
                         f"write exactly one of {_KINDS_HELP} (or repeat)")
        return None
    kind = kinds[0]
    step_order = _next_order(order)
    type_key, type_id = STEP_KINDS[kind]
    native = {
        "type": "ExecutableStepDTO",
        "stepId": step_order,
        "stepOrder": step_order,
        "stepType": {"stepTypeId": type_id, "stepTypeKey": type_key, "displayOrder": type_id},
    }

    end = _parse_end(step[kind], f"{path}.{kind}", errors)
    if end is not None:
        condition, value = end
        native["endCondition"] = dict(_END_CONDITIONS[condition])
        if value is not None:
            native["endConditionValue"] = float(value)

    targets = [key for key in TARGETS if key in step]
    if len(targets) > 1:
        errors.add(path, f"one target per step, got {', '.join(targets)}")
    native.update(_parse_target(targets[0], step[targets[0]], f"{path}.{targets[0]}", sport, errors)
                  if len(targets) == 1 else {"targetType": dict(_NO_TARGET)})

    note = step.get("note")
    if note is not None:
        if not isinstance(note, str):
            errors.add(f"{path}.note", "a string")
        elif note.strip():
            native["description"] = note

    native["strokeType"] = {"strokeTypeId": 0, "displayOrder": 0}
    native["equipmentType"] = {"equipmentTypeId": 0, "displayOrder": 0}
    return native


def _parse_repeat(step: dict, path: str, sport: str | None, errors: _Errors, order: list[int]) -> dict | None:
    for key in step:
        if key not in _REPEAT_KEYS:
            errors.add(f"{path}.{key}", f"unknown key; a repeat has {', '.join(_REPEAT_KEYS)}")
    times = step["repeat"]
    if isinstance(times, bool) or not isinstance(times, int) or not 1 <= times <= MAX_REPEAT:
        errors.add(f"{path}.repeat", f"the number of rounds, an integer from 1 to {MAX_REPEAT}")
        times = 1
    skip = step.get("skip_last_recover", False)
    if not isinstance(skip, bool):
        errors.add(f"{path}.skip_last_recover", "true or false")
        skip = False
    step_order = _next_order(order)
    inner = step.get("steps")
    children = []
    if not isinstance(inner, list) or not inner:
        errors.add(f"{path}.steps", "required, the non-empty list of steps to repeat")
    else:
        children = [_parse_step(s, f"{path}.steps[{i}]", sport, errors, order, in_repeat=True)
                    for i, s in enumerate(inner)]
    return {
        "type": "RepeatGroupDTO",
        "stepId": step_order,
        "stepOrder": step_order,
        "stepType": dict(_REPEAT_TYPE),
        "numberOfIterations": times,
        "endCondition": dict(_ITERATIONS),
        "endConditionValue": float(times),
        "skipLastRestStep": skip,
        "smartRepeat": False,
        "workoutSteps": children,
    }


def _parse_end(value, path: str, errors: _Errors) -> tuple[str, float | None] | None:
    """("time", s) | ("distance", m) | ("lap", None), from "5:00", "1km", "200m" or "lap"."""
    if not isinstance(value, str):
        errors.add(path, f"when the step ends: a duration {_END_HELP}; got {value!r}")
        return None
    text = value.strip()
    if text.lower() == _LAP:
        return _LAP, None
    if (seconds := parse_duration(text)) is not None:
        if not 0 < seconds <= MAX_STEP_S:
            errors.add(path, f"{text} is not a step duration (more than 0, at most 10:00:00)")
        return "time", seconds
    if (meters := parse_distance(text)) is not None:
        if not 0 < meters <= MAX_STEP_M:
            errors.add(path, f"{text} is not a step distance (more than 0, at most 500km)")
        return "distance", meters
    errors.add(path, f"{value!r}: write a duration {_END_HELP}")
    return None


def _parse_target(key: str, value, path: str, sport: str | None, errors: _Errors) -> dict:
    """The target fields of a native step (`targetType`, values or zone)."""
    no_target = {"targetType": dict(_NO_TARGET)}
    if key == "pace":
        if sport is not None and sport != "running":
            errors.add(path, f"pace is for running; on {sport}: hr, hr_zone or cadence")
            return no_target
        bounds = _parse_pace_range(value, path, errors)
        if bounds is None:
            return no_target
        fast, slow = bounds
        # Garmin Connect's order: the faster bound (higher m/s) first.
        return {"targetType": dict(_PACE_TARGET),
                "targetValueOne": 1000 / fast, "targetValueTwo": 1000 / slow}
    if key == "hr_zone":
        if isinstance(value, bool) or not isinstance(value, int) or not HR_ZONES[0] <= value <= HR_ZONES[1]:
            errors.add(path, f"a heart rate zone, an integer from {HR_ZONES[0]} to {HR_ZONES[1]}; got {value!r}")
            return no_target
        return {"targetType": dict(_HR_TARGET), "zoneNumber": value}
    unit, limits, target = ("bpm", HR_BPM, _HR_TARGET) if key == "hr" else ("per minute", CADENCE, _CADENCE_TARGET)
    bounds = _parse_int_range(value, path, unit, limits, errors)
    if bounds is None:
        return no_target
    low, high = bounds
    return {"targetType": dict(target), "targetValueOne": float(low), "targetValueTwo": float(high)}


def _parse_pace_range(value, path: str, errors: _Errors) -> tuple[int, int] | None:
    """(fast, slow) in s/km from "5:30-6:00" (any order, "/km" allowed) or "4:30"."""
    text = value.strip() if isinstance(value, str) else None
    paces = [parse_pace(part.strip().removesuffix("/km").strip()) for part in text.split("-")] if text else [None]
    if len(paces) > 2 or None in paces:
        errors.add(path, f'a pace per km, "m:ss" or a range "m:ss-m:ss"; got {value!r}')
        return None
    low, high = PACE_S_PER_KM
    for pace in paces:
        if not low <= pace <= high:
            errors.add(path, f"{format_pace_s(pace)}/km is not a running pace "
                             f"({format_pace_s(low)} to {format_pace_s(high)}/km)")
            return None
    return min(paces), max(paces)


def _parse_int_range(value, path: str, unit: str, limits: tuple[int, int], errors: _Errors):
    """(low, high) from "140-150", in any order."""
    match = _RANGE.match(value.strip()) if isinstance(value, str) else None
    if not match:
        errors.add(path, f'a range "low-high" ({unit}), like "140-150"; got {value!r}')
        return None
    low, high = sorted(int(group) for group in match.groups())
    if low < limits[0] or high > limits[1]:
        errors.add(path, f"{low}-{high} is out of {limits[0]}-{limits[1]} {unit}")
        return None
    return low, high


def parse_duration(text: str) -> int | None:
    """Seconds from "m:ss" or "h:mm:ss", or None if `text` is not one."""
    match = _DURATION.match(text)
    if not match:
        return None
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    if seconds >= 60 or (match.group(1) and minutes >= 60):
        return None
    return hours * 3600 + minutes * 60 + seconds


def parse_distance(text: str) -> float | None:
    """Meters from "1km", "1.5 km" (or "1,5km") or "200m", or None if `text` is not one."""
    match = _DISTANCE.match(text.replace(",", "."))
    if not match:
        return None
    number = float(match.group(1))
    return number * 1000 if match.group(2).lower() == "km" else number


def parse_pace(text: str) -> int | None:
    """Seconds per km from "m:ss", or None."""
    match = _PACE.match(text)
    if not match or int(match.group(2)) >= 60:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


# ── Garmin → readable ────────────────────────────────────────────────────────


def from_garmin(workout: dict) -> dict:
    """The readable form of a native Garmin workout.

    What the format cannot say is in the step (`not_readable`) and in `warnings`,
    with the pace or heart-rate bounds stored in the reverse of Garmin Connect's order.
    """
    warnings: list[str] = []
    segments = workout.get("workoutSegments") or []
    if len(segments) > 1:
        warnings.append(f"{len(segments)} segments (multisport): their steps are listed one after "
                        "the other; `workouts get --raw` shows the segments")
    raw_steps = [step for segment in segments for step in segment.get("workoutSteps") or []]
    readable = {
        "name": workout.get("workoutName"),
        "sport": (workout.get("sportType") or {}).get("sportTypeKey"),
    }
    if workout.get("description"):
        readable["description"] = workout["description"]
    readable["steps"] = [_render_step(step, f"steps[{i}]", warnings) for i, step in enumerate(raw_steps)]
    if warnings:
        readable["warnings"] = warnings
    return readable


def _is_repeat(step: dict) -> bool:
    return step.get("type") == "RepeatGroupDTO" or (step.get("stepType") or {}).get("stepTypeKey") == "repeat"


def _render_step(step: dict, path: str, warnings: list[str]) -> dict:
    if _is_repeat(step):
        return _render_repeat(step, path, warnings)
    not_readable: list[str] = []
    readable: dict = {}

    type_key = (step.get("stepType") or {}).get("stepTypeKey")
    kind = _KIND_OF_STEP_TYPE.get(type_key)
    end = _render_end(step, not_readable)
    if kind:
        readable[kind] = end
    else:
        not_readable.append(f"step type {type_key}")

    readable.update(_render_target(step, path, not_readable, warnings))
    if step.get("description"):
        readable["note"] = step["description"]

    if step.get("category") or step.get("exerciseName"):
        not_readable.append(f"exercise {step.get('category')}/{step.get('exerciseName')}")
    if (step.get("secondaryTargetType") or {}).get("workoutTargetTypeKey") not in (None, "no.target"):
        not_readable.append(f"secondary target {step['secondaryTargetType']['workoutTargetTypeKey']}")
    if (step.get("strokeType") or {}).get("strokeTypeId") or (step.get("equipmentType") or {}).get("equipmentTypeId"):
        not_readable.append("swim stroke or equipment")
    if step.get("weightValue") is not None:
        not_readable.append(f"weight {step['weightValue']}")

    if not_readable:
        readable[NOT_READABLE] = not_readable
        warnings.append(f"{path}: not readable ({_join(not_readable)}). `workouts get --raw` shows it; "
                        "a create or update with this step is refused")
    return readable


def _render_repeat(step: dict, path: str, warnings: list[str]) -> dict:
    readable = {
        "repeat": int(step.get("numberOfIterations") or step.get("endConditionValue") or 0),
        "steps": [_render_step(s, f"{path}.steps[{i}]", warnings) for i, s in enumerate(step.get("workoutSteps") or [])],
    }
    if step.get("skipLastRestStep"):
        readable["skip_last_recover"] = True
    if step.get("smartRepeat"):
        readable[NOT_READABLE] = ["smart repeat"]
        warnings.append(f"{path}: not readable (smart repeat). `workouts get --raw` shows it; "
                        "a create or update with this step is refused")
    return readable


def _render_end(step: dict, not_readable: list[str]) -> str:
    """The end of a step; an end with no word ("10 reps") is also named in `not_readable`."""
    condition = (step.get("endCondition") or {}).get("conditionTypeKey")
    value = step.get("endConditionValue")
    if condition == "lap.button":
        return _LAP
    if condition == "time" and value:
        return format_duration(value)
    if condition == "distance" and value:
        return format_distance(value)
    as_text = f"{value:g} {condition}" if isinstance(value, (int, float)) else str(condition)
    not_readable.append(f"ends on {as_text}")
    return as_text


def _render_target(step: dict, path: str, not_readable: list[str], warnings: list[str]) -> dict:
    target = (step.get("targetType") or {}).get("workoutTargetTypeKey")
    target_id = (step.get("targetType") or {}).get("workoutTargetTypeId")
    one, two, zone = step.get("targetValueOne"), step.get("targetValueTwo"), step.get("zoneNumber")
    if target in (None, "no.target"):
        return {}
    if target == "heart.rate.zone" and zone and one is None and two is None:
        return {"hr_zone": int(zone)}
    if one and two:
        if target == "pace.zone":
            fast, slow = sorted((one, two), reverse=True)
            if one < two:
                warnings.append(f"{path}.pace: Garmin has the slower bound first "
                                f"({format_pace(one)} then {format_pace(two)}); Garmin Connect puts the "
                                "faster first. An update with these steps stores them in that order")
            return {"pace": _pace_range(fast, slow)}
        if target == "heart.rate.zone" or _is_cadence(target, target_id):
            key = "hr" if target == "heart.rate.zone" else "cadence"
            if one > two:
                warnings.append(f"{path}.{key}: Garmin has the higher bound first ({one:g} then {two:g}); "
                                "Garmin Connect puts the lower first. An update with these steps "
                                "stores them in that order")
            low, high = sorted((one, two))
            return {key: f"{round(low)}-{round(high)}"}
    not_readable.append(f"target {target} {_target_values(one, two, zone)}")
    return {}


def _is_cadence(target: str, target_id) -> bool:
    return target_id == _CADENCE_TARGET["workoutTargetTypeId"] or target.startswith("cadence")


def _target_values(one, two, zone) -> str:
    return f"zone {zone}" if zone else f"{one}-{two}"


def _pace_range(fast_mps: float, slow_mps: float) -> str:
    fast, slow = format_pace(fast_mps), format_pace(slow_mps)
    return fast if fast == slow else f"{fast}-{slow}"


def _join(items) -> str:
    return ", ".join(items) if isinstance(items, list) else str(items)


def format_duration(seconds: float) -> str:
    """ "m:ss" under an hour, "h:mm:ss" from an hour."""
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def format_distance(meters: float) -> str:
    """ "200m" under a kilometer, "1km" / "1.5km" from a kilometer."""
    if meters < 1000:
        return f"{round(meters)}m"
    return f"{meters / 1000:.3f}".rstrip("0").rstrip(".") + "km"


def format_pace_s(seconds_per_km: float) -> str:
    total = round(seconds_per_km)
    return f"{total // 60}:{total % 60:02d}"


def format_pace(speed_mps: float) -> str:
    """ "m:ss" per km from a speed in m/s."""
    return format_pace_s(1000 / speed_mps)


# ── Estimates ────────────────────────────────────────────────────────────────


@dataclass
class Estimate:
    """Duration and distance of a workout; None when a step does not give it.

    A step gives its time when it ends on time, or on distance with a pace target
    (at the middle of the range, as Garmin Connect estimates: 1km at 5:00-5:30 = 5:15);
    its distance likewise. `no_duration` / `no_distance`: the steps that do not, and why.
    """

    duration_s: int | None
    distance_m: int | None
    no_duration: list[str]
    no_distance: list[str]


def estimate(steps: list) -> Estimate:
    """The estimate of native steps (`workoutSteps` of a segment)."""
    no_duration: list[str] = []
    no_distance: list[str] = []
    duration, distance = _totals(steps, "steps", no_duration, no_distance)
    return Estimate(None if duration is None else round(duration),
                    None if distance is None else round(distance),
                    no_duration, no_distance)


def _totals(steps: list, path: str, no_duration: list[str], no_distance: list[str]):
    duration = distance = 0.0
    for i, step in enumerate(steps):
        step_path = f"{path}[{i}]"
        if _is_repeat(step):
            children = step.get("workoutSteps") or []
            one_round = _totals(children, f"{step_path}.steps", no_duration, no_distance)
            times = step.get("numberOfIterations") or 0
            step_time, step_distance = (None if part is None else part * times for part in one_round)
            last = children[-1] if children else {}
            if step.get("skipLastRestStep") and (last.get("stepType") or {}).get("stepTypeKey") in _RECOVER_KINDS:
                skipped = _totals([last], "", [], [])
                step_time = _minus(step_time, skipped[0])
                step_distance = _minus(step_distance, skipped[1])
        else:
            step_time, step_distance, why = _step_totals(step)
            if step_time is None:
                no_duration.append(f"{step_path} ({why})")
            if step_distance is None:
                no_distance.append(f"{step_path} ({why})")
        duration = None if duration is None or step_time is None else duration + step_time
        distance = None if distance is None or step_distance is None else distance + step_distance
    return duration, distance


def _minus(total: float | None, part: float | None) -> float | None:
    return None if total is None or part is None else total - part


def _step_totals(step: dict) -> tuple[float | None, float | None, str]:
    """(time s, distance m, why one is missing) of one executable step."""
    condition = (step.get("endCondition") or {}).get("conditionTypeKey")
    value = step.get("endConditionValue")
    speed = _mid_pace_speed(step)
    if condition == "time" and value:
        return value, None if speed is None else value * speed, "no pace"
    if condition == "distance" and value:
        return None if speed is None else value / speed, value, "no pace"
    return None, None, "lap" if condition == "lap.button" else f"ends on {condition}"


def _mid_pace_speed(step: dict) -> float | None:
    """m/s at the middle (in min/km) of the step's pace range, or None without one."""
    if (step.get("targetType") or {}).get("workoutTargetTypeKey") != "pace.zone":
        return None
    one, two = step.get("targetValueOne"), step.get("targetValueTwo")
    if not one or not two:
        return None
    return 1000 / ((1000 / one + 1000 / two) / 2)
