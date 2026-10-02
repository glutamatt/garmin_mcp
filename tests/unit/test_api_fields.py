"""Unit tests for the field registry (`api/fields.py`) and the activity table (`api/activity_fields.py`).

Synthetic data only. Real Garmin answers are tested in neural-runner (`tests/garmin-fixtures/`).
"""

from datetime import timedelta

import pytest

from garmin_mcp.api import activity_fields as af
from garmin_mcp.api.contract import InvalidInput
from garmin_mcp.api.fields import (
    Field,
    FieldSet,
    Source,
    dig,
    fahrenheit_to_celsius,
    iso_time,
    mph_to_mps,
    pace_s_per_km,
    shift_time,
)

A = Source("a", "thing list")
A_PLUS = Source("a_plus", "thing list", option="--with more")
B = Source("b", "thing get")

REGISTRY = (
    Field("id", "", "Id", {A: "thingId", A_PLUS: "thingId", B: "thingId"}),
    Field("distance_m", "m", "Distance", {A: "dist", B: "summary.dist"}, digits=0),
    Field("pace_s_per_km", "s/km", "Pace", {A: "speed", B: "summary.speed"}, pace_s_per_km, 0),
    Field("label", "", "Label", {A: "label", A_PLUS: "label"}),
    Field("effort", "", "Effort", {A_PLUS: "summary.rpe", B: "summary.rpe"}, lambda rpe: rpe / 10, 1),
    Field("double", "", "Computed", {A: lambda raw: raw["dist"] * 2 if "dist" in raw else None}),
    Field("load", "", "Load", {A: "load", B: "summary.load"}, feature="load"),
)
LIST = FieldSet(A, REGISTRY, items_key="things", always=("label",))
LIST_PLUS = FieldSet(A_PLUS, REGISTRY, items_key="things")
DETAIL = FieldSet(B, REGISTRY)


# ── Conversions ──────────────────────────────────────────────────────────────


class TestConversions:
    def test_pace(self):
        assert pace_s_per_km(2.5) == 400
        assert pace_s_per_km(0) is None

    def test_imperial(self):
        assert fahrenheit_to_celsius(212) == 100
        assert mph_to_mps(10) == pytest.approx(4.4704)

    @pytest.mark.parametrize("raw", ["2026-09-30 08:26:58", "2026-09-30T08:26:58.0", "2026-09-30T08:26:58.123"])
    def test_iso_time(self, raw):
        assert iso_time(raw) == "2026-09-30T08:26:58"

    def test_shift_time_crosses_midnight(self):
        assert shift_time("2026-09-30T23:30:00.0", timedelta(hours=2)) == "2026-10-01T01:30:00"

    def test_dig(self):
        assert dig({"a": {"b": 1}}, "a.b") == 1
        assert dig({"a": None}, "a.b") is None
        assert dig({}, "a") is None


# ── Curation ─────────────────────────────────────────────────────────────────


class TestCurate:
    def test_each_source_reads_its_own_key(self):
        assert LIST.curate({"thingId": 1, "dist": 999.6, "speed": 2.5, "label": "x"}) == {
            "id": 1, "distance_m": 1000, "pace_s_per_km": 400, "label": "x", "double": 1999.2,
        }
        assert DETAIL.curate({"thingId": 1, "summary": {"dist": 10.2, "rpe": 70}}) == {
            "id": 1, "distance_m": 10, "effort": 7.0,
        }

    def test_rounding_to_zero_digits_gives_an_int(self):
        assert isinstance(LIST.curate({"dist": 999.6})["distance_m"], int)

    def test_missing_values_are_left_out_and_zero_is_kept(self):
        assert LIST.curate({"dist": 0.0, "speed": 0.0}) == {"distance_m": 0, "double": 0.0}

    def test_names_follow_the_source(self):
        assert LIST.names == ("id", "distance_m", "pace_s_per_km", "label", "double", "load")
        assert LIST_PLUS.names == ("id", "label", "effort")
        assert DETAIL.names == ("id", "distance_m", "pace_s_per_km", "effort", "load")

    def test_value(self):
        assert DETAIL.value("effort", {"summary": {"rpe": 25}}) == 2.5
        assert DETAIL.value("effort", {}) is None


# ── --fields ─────────────────────────────────────────────────────────────────


class TestCheck:
    def test_known_names_pass_even_from_another_source(self):
        LIST.check(["id", "effort"])  # `effort` is a registry field: not unknown, only empty here

    def test_unknown_name_is_invalid_input_with_the_valid_names(self):
        with pytest.raises(InvalidInput) as e:
            LIST.check(["id", "bogus", "speed"])
        message = str(e.value)
        assert "Unknown fields for thing list: bogus, speed." in message
        assert "Fields: id, distance_m, pace_s_per_km, label, double" in message

    def test_a_former_name_is_refused_with_the_new_one(self):
        renamed = FieldSet(A, (Field("distance_m", "m", "Distance", {A: "dist"}, formerly=("distance_meters",)),))
        with pytest.raises(InvalidInput, match=r"Unknown fields for thing list: distance_meters \(now distance_m\)\."):
            renamed.check(["distance_meters"])


class TestSelect:
    ANSWER = {"count": 2, "things": [
        {"id": 1, "distance_m": 10, "label": "a"},
        {"id": 2, "label": "b"},
    ]}

    def test_keeps_the_requested_fields_the_always_fields_and_the_metadata(self):
        assert LIST.select(self.ANSWER, ["id", "distance_m"]) == {"count": 2, "things": [
            {"id": 1, "distance_m": 10, "label": "a"},
            {"id": 2, "label": "b"},
        ]}

    def test_a_field_one_item_has_is_not_empty(self):
        assert "empty_fields" not in LIST.select(self.ANSWER, ["distance_m"])

    def test_empty_fields_say_why(self):
        selected = LIST.select(self.ANSWER, ["id", "pace_s_per_km", "effort", "load"])
        assert selected["empty_fields"] == {
            "pace_s_per_km": "no_data",          # this command gives it, Garmin had no value
            "effort": "only_in: thing list --with more, thing get",  # this command does not give it
            "load": "no_data",                   # no device reason asked for
        }

    def test_a_device_field_asks_the_device_reason(self):
        asked = []

        def missing_reason(feature):
            asked.append(feature)
            return "not_supported_by_device"

        selected = LIST.select(self.ANSWER, ["id", "pace_s_per_km", "load"], missing_reason)
        assert selected["empty_fields"] == {"pace_s_per_km": "no_data", "load": "not_supported_by_device"}
        assert asked == ["load"]

    def test_the_device_reason_is_not_asked_when_the_field_has_a_value(self):
        answer = {"count": 1, "things": [{"id": 1, "load": 80}]}
        assert "empty_fields" not in LIST.select(answer, ["load"], lambda feature: pytest.fail("asked"))

    def test_a_command_named_once_without_its_option_when_it_gives_the_field_without(self):
        """`label` is in `thing list` with and without `--with more`: the reason names `thing list`."""
        detail = {"id": 1}
        assert DETAIL.select(detail, ["label"])["empty_fields"] == {"label": "only_in: thing list"}

    def test_a_field_of_the_option(self):
        answer = {"count": 1, "things": [{"id": 1}]}
        assert LIST_PLUS.select(answer, ["effort"])["empty_fields"] == {"effort": "no_data"}

    def test_an_answer_without_items_says_nothing(self):
        empty = {"count": 0, "things": []}
        assert LIST.select(empty, ["id", "effort"]) == empty

    def test_one_item_answer(self):
        detail = {"id": 1, "distance_m": 10, "effort": 2.0}
        assert DETAIL.select(detail, ["distance_m", "label"]) == {
            "distance_m": 10, "empty_fields": {"label": "only_in: thing list"},
        }


# ── The activity table ───────────────────────────────────────────────────────

# Suffix → unit, from the naming rule (`api/fields.py`).
UNIT_SUFFIXES = {
    "_s_per_km": "s/km", "_mps": "m/s", "_ms": "ms", "_cm": "cm", "_m": "m", "_s": "s",
    "_bpm": "bpm", "_spm": "steps/min", "_kcal": "kcal", "_watts": "W", "_celsius": "°C", "_percent": "%",
}


# A measure named after its own unit has no suffix.
NAMED_UNITS = {"vo2_max": "mL/kg/min"}


def _suffix(name: str) -> str | None:
    return next((s for s in UNIT_SUFFIXES if name.endswith(s)), None)


ALL_ACTIVITY_FIELDS = af.FIELDS + af.WEATHER_FIELDS.registry


class TestActivityTable:
    def test_names_are_unique(self):
        names = [f.name for f in af.FIELDS]
        assert len(names) == len(set(names))

    def test_former_names_belong_to_fields_and_are_not_current_names(self):
        names = {f.name for f in af.FIELDS}
        assert set(af._FORMER_NAMES) <= names
        former = [old for olds in af._FORMER_NAMES.values() for old in olds]
        assert not set(former) & names

    @pytest.mark.parametrize("field", ALL_ACTIVITY_FIELDS, ids=lambda f: f.name)
    def test_the_name_says_the_unit(self, field):
        suffix = _suffix(field.name)
        if field.name in NAMED_UNITS:
            assert suffix is None and field.unit == NAMED_UNITS[field.name]
        elif field.unit:
            assert suffix and UNIT_SUFFIXES[suffix] == field.unit
        else:
            assert suffix is None

    @pytest.mark.parametrize("field", ALL_ACTIVITY_FIELDS, ids=lambda f: f.name)
    def test_every_field_is_documented(self, field):
        assert field.doc

    @pytest.mark.parametrize("field", [f for f in af.FIELDS if f.name.endswith("_s_per_km")], ids=lambda f: f.name)
    def test_paces_are_integers(self, field):
        assert field.convert is pace_s_per_km
        assert field.digits == 0

    def test_same_concept_same_name_in_list_get_and_splits(self):
        shared = set(af.LIST_FIELDS.names) & set(af.DETAIL_FIELDS.names) & set(af.LAP_FIELDS.names)
        assert {"start_time", "start_time_gmt", "distance_m", "duration_s", "avg_pace_s_per_km",
                "gap_s_per_km", "moving_pace_s_per_km", "elevation_gain_m", "elevation_loss_m",
                "avg_hr_bpm", "calories_kcal", "avg_cadence_spm"} <= shared

    def test_effort_is_only_in_the_detail_and_the_list_with_effort(self):
        """Garmin's list has no RPE (checked on real answers): `--fields perceived_effort` on a list
        says where it is."""
        assert "perceived_effort" not in af.LIST_FIELDS.names
        answer = {"count": 1, "activities": [{"id": 1, "sport": "running"}]}
        assert af.LIST_FIELDS.select(answer, ["id", "perceived_effort"])["empty_fields"] == {
            "perceived_effort": "only_in: activities list --with effort, activities get",
        }

    def test_the_list_with_effort_has_every_list_field_and_the_effort(self):
        assert set(af.LIST_EFFORT_FIELDS.names) == set(af.LIST_FIELDS.names) | {"perceived_effort", "workout_feel"}

    def test_the_list_with_effort_reads_the_added_detail_summary(self):
        raw = {"activityId": 1, "distance": 5000.0, "summaryDTO": {"directWorkoutRpe": 40, "directWorkoutFeel": 75}}
        assert af.LIST_EFFORT_FIELDS.curate(raw) == {
            "id": 1, "distance_m": 5000, "perceived_effort": 4.0, "workout_feel": 75,
        }

    def test_training_load_depends_on_the_device(self):
        (field,) = [f for f in af.FIELDS if f.name == "training_load"]
        assert field.feature == "training_load"

    def test_sport_is_always_kept(self):
        answer = {"count": 1, "activities": [{"id": 1, "sport": "running", "distance_m": 5000}]}
        assert af.LIST_FIELDS.select(answer, ["id"])["activities"] == [{"id": 1, "sport": "running"}]

    def test_list_moving_pace_is_distance_over_moving_time(self):
        """The list has no averageMovingSpeed: the detail's value is distance / movingDuration."""
        assert af.LIST_FIELDS.value("moving_pace_s_per_km", {"distance": 5000.0, "movingDuration": 1500.0}) == 300
        assert af.LIST_FIELDS.value("moving_pace_s_per_km", {"distance": 5000.0, "movingDuration": 0}) is None

    def test_list_hr_zones(self):
        raw = {"hrTimeInZone_1": 149.4, "hrTimeInZone_2": 0.0, "hrTimeInZone_3": 2049.7}
        assert af.LIST_FIELDS.value("hr_zones_s", raw) == {"z1": 149, "z3": 2050}
        assert af.LIST_FIELDS.value("hr_zones_s", {}) is None

    def test_perceived_effort_is_cr10(self):
        assert af.DETAIL_FIELDS.value("perceived_effort", {"summaryDTO": {"directWorkoutRpe": 70}}) == 7.0
