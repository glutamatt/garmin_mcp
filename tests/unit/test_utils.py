"""Unit tests for garmin_mcp.utils shared utilities."""

import pytest
from garmin_mcp.utils import (
    clean_nones,
    validate_date,
    format_duration,
    format_distance,
    format_pace,
)


# ── clean_nones ──────────────────────────────────────────────────────────────


class TestCleanNones:
    def test_removes_none_values(self):
        assert clean_nones({"a": 1, "b": None, "c": 3}) == {"a": 1, "c": 3}

    def test_nested_dict(self):
        result = clean_nones({"a": {"b": None, "c": 2}, "d": None})
        assert result == {"a": {"c": 2}}

    def test_list_of_dicts(self):
        result = clean_nones([{"a": 1, "b": None}, {"c": None, "d": 4}])
        assert result == [{"a": 1}, {"d": 4}]

    def test_empty_dict(self):
        assert clean_nones({}) == {}

    def test_all_none(self):
        assert clean_nones({"a": None, "b": None}) == {}

    def test_no_nones(self):
        assert clean_nones({"a": 1, "b": 2}) == {"a": 1, "b": 2}

    def test_preserves_zero_and_false(self):
        result = clean_nones({"a": 0, "b": False, "c": "", "d": None})
        assert result == {"a": 0, "b": False, "c": ""}

    def test_scalar_passthrough(self):
        assert clean_nones(42) == 42
        assert clean_nones("hello") == "hello"

    def test_deeply_nested(self):
        result = clean_nones({"a": [{"b": [{"c": None, "d": 1}]}]})
        assert result == {"a": [{"b": [{"d": 1}]}]}


# ── validate_date ────────────────────────────────────────────────────────────


class TestValidateDate:
    def test_valid_date(self):
        assert validate_date("2024-01-15") == "2024-01-15"

    def test_strips_whitespace(self):
        assert validate_date("  2024-01-15  ") == "2024-01-15"

    def test_rejects_non_string(self):
        with pytest.raises(ValueError, match="must be a string"):
            validate_date(20240115)

    def test_rejects_wrong_format(self):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            validate_date("15-01-2024")

    def test_rejects_invalid_date(self):
        with pytest.raises(ValueError):
            validate_date("2024-02-30")

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            validate_date("")

    def test_leap_year(self):
        assert validate_date("2024-02-29") == "2024-02-29"

    def test_non_leap_year(self):
        with pytest.raises(ValueError):
            validate_date("2023-02-29")


# ── format_duration ──────────────────────────────────────────────────────────


class TestFormatDuration:
    def test_hours_minutes_seconds(self):
        assert format_duration(5025) == "1h23m45s"

    def test_minutes_seconds(self):
        assert format_duration(1530) == "25m30s"

    def test_seconds_only(self):
        assert format_duration(45) == "45s"

    def test_zero(self):
        assert format_duration(0) == "0s"

    def test_negative(self):
        assert format_duration(-100) == "0s"

    def test_none(self):
        assert format_duration(None) == "0s"

    def test_string_number(self):
        assert format_duration("3600") == "1h00m00s"

    def test_invalid_string(self):
        assert format_duration("abc") == "0s"

    def test_exact_hour(self):
        assert format_duration(3600) == "1h00m00s"

    def test_exact_minute(self):
        assert format_duration(60) == "1m00s"


# ── format_distance ──────────────────────────────────────────────────────────


class TestFormatDistance:
    def test_kilometers(self):
        assert format_distance(10000) == "10.0 km"

    def test_meters(self):
        assert format_distance(800) == "800 m"

    def test_threshold(self):
        assert format_distance(1000) == "1.0 km"

    def test_decimal_km(self):
        assert format_distance(5123) == "5.1 km"

    def test_zero(self):
        assert format_distance(0) == "0 m"

    def test_negative(self):
        assert format_distance(-500) == "0 m"

    def test_none(self):
        assert format_distance(None) == "0 m"

    def test_string_number(self):
        assert format_distance("42195") == "42.2 km"


# ── format_pace ──────────────────────────────────────────────────────────────


class TestFormatPace:
    def test_normal_pace(self):
        # 1000m / 3.03 m/s ≈ 330s = 5:30 /km
        assert format_pace(3.03) == "5:30 /km"

    def test_fast_pace(self):
        # 1000m / 5.56 m/s ≈ 180s = 3:00 /km
        assert format_pace(5.56) == "2:59 /km"

    def test_slow_pace(self):
        # 1000m / 2.0 m/s = 500s = 8:20 /km
        assert format_pace(2.0) == "8:20 /km"

    def test_zero_speed(self):
        assert format_pace(0) is None

    def test_negative_speed(self):
        assert format_pace(-1) is None

    def test_none(self):
        assert format_pace(None) is None

    def test_string_number(self):
        assert format_pace("3.03") == "5:30 /km"
