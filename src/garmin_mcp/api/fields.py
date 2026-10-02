"""
Field registry — one place for the name, unit, raw key and conversion of each output field.

A curated answer is built from a registry, not field by field in each function:
the same concept has the same name and unit in every command that gives it, and
`--fields` is checked against the registry, not against the data (an empty field
is absent from the data, it is not unknown).

Naming rule (audit C7):
- snake_case, the unit as suffix: `_m`, `_cm`, `_s`, `_ms`, `_mps` (m/s),
  `_s_per_km`, `_bpm`, `_spm` (steps/min), `_kcal`, `_watts`, `_celsius`, `_percent`.
  No suffix for counts, scores, labels and ids, nor for a measure named after
  its unit (`vo2_max`, mL/kg/min).
- SI units. Imperial values from Garmin (°F, mph) are converted. A pace is an
  integer `_s_per_km`.
- Rounding at the source: `digits` per field (0 gives an int).
- Times: `YYYY-MM-DDTHH:MM:SS`. `start_time` is local time; GMT is `start_time_gmt`.
- Ids: an object's own id is `id`; a reference to another object is `<object>_id`.

Pure data and functions: no Garmin call here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping, Union

from garmin_mcp.api.contract import NO_DATA, InvalidInput

# Reason given in `empty_fields` for a field this command does not give.
ONLY_IN = "only_in"


@dataclass(frozen=True)
class Source:
    """One shape of raw Garmin data (a list item, a detail, a lap), and the command that shows it."""

    name: str
    command: str


# How to read a raw value: a dotted path in the raw item, or a function of the raw item.
Reader = Union[str, Callable[[dict], Any]]


@dataclass(frozen=True)
class Field:
    """One output field: its name (with unit), where each source keeps it, how to convert it."""

    name: str
    unit: str  # "" when the value has no unit (count, label, id)
    doc: str
    keys: Mapping[Source, Reader]
    convert: Callable[[Any], Any] | None = None
    digits: int | None = None  # rounding after `convert`; 0 gives an int

    def read(self, source: Source, raw: dict) -> Any:
        """The curated value of this field in `raw`, or None when Garmin has none."""
        reader = self.keys[source]
        value = reader(raw) if callable(reader) else dig(raw, reader)
        if value is not None and self.convert is not None:
            value = self.convert(value)
        return _round(value, self.digits)


@dataclass(frozen=True)
class FieldSet:
    """The fields of one command: a registry seen from one source.

    `items_key` says where the curated items are in the command's answer
    (`"activities"`, `"laps"`), or None when the answer is the item itself.
    `always` fields are kept by `--fields` even when not asked for.
    """

    source: Source
    registry: tuple[Field, ...]
    items_key: str | None = None
    always: tuple[str, ...] = ()

    @property
    def fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.registry if self.source in f.keys)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)

    def curate(self, raw: dict) -> dict:
        """One raw item → its curated fields, in registry order. Fields Garmin has no value for are left out."""
        curated = {}
        for field in self.fields:
            value = field.read(self.source, raw)
            if value is not None:
                curated[field.name] = value
        return curated

    def value(self, name: str, raw: dict) -> Any:
        """One curated field of a raw item (None when Garmin has no value)."""
        field = next(f for f in self.fields if f.name == name)
        return field.read(self.source, raw)

    def check(self, requested: list[str]) -> None:
        """Refuse a `--fields` name the registry does not know (the data is not looked at)."""
        known = {f.name for f in self.registry}
        unknown = [name for name in requested if name not in known]
        if unknown:
            raise InvalidInput(
                f"Unknown fields for {self.source.command}: {', '.join(unknown)}. "
                f"Fields: {', '.join(self.names)}"
            )

    def select(self, answer: dict, requested: list[str]) -> dict:
        """The answer with only the requested fields in its items, and why some of them are empty.

        `empty_fields` maps each requested field that no item has to its reason:
        `no_data` (Garmin gave no value), or `only_in: <commands>` (this command
        does not give it). An answer without items says nothing: empty is empty.
        """
        keep = set(requested) | set(self.always)
        if self.items_key is None:
            items = [answer]
            selected = _only(answer, keep)
        else:
            items = answer[self.items_key]
            selected = {**answer, self.items_key: [_only(item, keep) for item in items]}
        empty = self.empty_fields(items, requested) if items else {}
        if empty:
            selected["empty_fields"] = empty
        return selected

    def empty_fields(self, items: list[dict], requested: list[str]) -> dict[str, str]:
        by_name = {f.name: f for f in self.registry}
        present = {name for item in items for name in item}
        empty = {}
        for name in requested:
            if name in present or name not in by_name:
                continue
            field = by_name[name]
            if self.source in field.keys:
                empty[name] = NO_DATA
            else:
                empty[name] = f"{ONLY_IN}: {', '.join(s.command for s in field.keys)}"
        return empty


def dig(raw: Any, path: str) -> Any:
    """The value at a dotted path (`"summaryDTO.distance"`), or None when a step is missing."""
    value = raw
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _only(item: dict, keep: set[str]) -> dict:
    return {k: v for k, v in item.items() if k in keep}


def _round(value: Any, digits: int | None) -> Any:
    if digits is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    return round(value) if digits == 0 else round(value, digits)


# ── Conversions ──────────────────────────────────────────────────────────────


def pace_s_per_km(speed_mps: float) -> float | None:
    """m/s → seconds per km. No pace for a speed of 0 (standing still)."""
    return 1000 / speed_mps if speed_mps > 0 else None


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    return (fahrenheit - 32) * 5 / 9


def mph_to_mps(mph: float) -> float:
    return mph * 0.44704


_GARMIN_TIME = "%Y-%m-%dT%H:%M:%S"


def parse_time(value: str) -> datetime:
    """Garmin's time strings: `2026-09-30 08:26:58` (list) or `2026-09-30T08:26:58.0` (detail, laps)."""
    return datetime.strptime(value.replace(" ", "T")[:19], _GARMIN_TIME)


def iso_time(value: str) -> str:
    """Any Garmin time string → `YYYY-MM-DDTHH:MM:SS`."""
    return parse_time(value).strftime(_GARMIN_TIME)


def shift_time(value: str, offset: timedelta) -> str:
    """A Garmin time string moved by `offset` (GMT → local time), as `YYYY-MM-DDTHH:MM:SS`."""
    return (parse_time(value) + offset).strftime(_GARMIN_TIME)
