"""Unit tests for CLI output module: field filtering + formatting + CSV writer."""

import csv
import json

from garmin_mcp.cli.output import filter_fields, find_missing_fields, format_output, write_csv_file


class TestFilterFields:
    def test_flat_dict(self):
        data = {"id": 1, "name": "Run", "distance_meters": 5000, "calories": 350}
        result = filter_fields(data, ["id", "name"])
        assert result == {"id": 1, "name": "Run"}

    def test_dict_with_list(self):
        data = {
            "count": 2,
            "activities": [
                {"id": 1, "name": "Run", "distance_meters": 5000},
                {"id": 2, "name": "Bike", "distance_meters": 20000},
            ],
        }
        result = filter_fields(data, ["id", "name"])
        assert result["count"] == 2  # metadata kept
        assert result["activities"] == [
            {"id": 1, "name": "Run"},
            {"id": 2, "name": "Bike"},
        ]

    def test_list_of_dicts(self):
        data = [
            {"id": 1, "name": "A", "extra": "x"},
            {"id": 2, "name": "B", "extra": "y"},
        ]
        result = filter_fields(data, ["id"])
        assert result == [{"id": 1}, {"id": 2}]

    def test_preserves_metadata(self):
        data = {
            "count": 1,
            "date_range": {"start": "2025-01-01", "end": "2025-01-31"},
            "items": [{"id": 1, "name": "X", "value": 42}],
        }
        result = filter_fields(data, ["id", "name"])
        assert result["count"] == 1
        assert result["date_range"] == {"start": "2025-01-01", "end": "2025-01-31"}
        assert result["items"] == [{"id": 1, "name": "X"}]

    def test_nonexistent_fields(self):
        data = {"id": 1, "name": "Run"}
        result = filter_fields(data, ["nonexistent"])
        assert result == {}

    def test_no_filter(self):
        data = {"id": 1}
        # filter_fields shouldn't be called with None, but test robustness
        result = filter_fields(data, ["id"])
        assert result == {"id": 1}


class TestFindMissingFields:
    def test_detects_missing_in_dict_with_list(self):
        data = {
            "count": 2,
            "activities": [
                {"id": 1, "name": "Run", "avg_hr_bpm": 150},
            ],
        }
        missing = find_missing_fields(data, ["id", "perceived_exertion", "fake_field"])
        assert "perceived_exertion" in missing
        assert "fake_field" in missing
        assert "id" not in missing

    def test_no_missing(self):
        data = {"id": 1, "name": "Run"}
        assert find_missing_fields(data, ["id", "name"]) == []

    def test_flat_dict(self):
        data = {"id": 1}
        assert find_missing_fields(data, ["id", "missing"]) == ["missing"]

    def test_list_of_dicts(self):
        data = [{"id": 1, "name": "X"}]
        assert find_missing_fields(data, ["id", "nope"]) == ["nope"]

    def test_empty_data(self):
        assert find_missing_fields([], ["id"]) == []
        assert find_missing_fields({}, ["id"]) == []


class TestFormatOutput:
    def test_json_format(self):
        data = {"id": 1, "name": "Run"}
        result = format_output(data, "json")
        parsed = json.loads(result)
        assert parsed == data

    def test_table_flat_dict(self):
        data = {"id": 1, "name": "Run", "distance_meters": 5000.0}
        result = format_output(data, "table")
        assert "id" in result
        assert "Run" in result
        assert "5.0 km" in result  # smart formatting

    def test_table_with_list(self):
        data = {
            "count": 2,
            "activities": [
                {"id": 1, "name": "Run"},
                {"id": 2, "name": "Bike"},
            ],
        }
        result = format_output(data, "table")
        assert "count: 2" in result
        assert "Run" in result
        assert "Bike" in result
        # Should have header separator
        assert "---" in result

    def test_table_error(self):
        data = {"error": "No data found"}
        result = format_output(data, "table")
        assert "Error: No data found" in result

    def test_table_duration_formatting(self):
        data = {"duration_seconds": 3661}
        result = format_output(data, "table")
        assert "1h01m01s" in result

    def test_table_empty_list(self):
        data = {"count": 0, "activities": []}
        result = format_output(data, "table")
        assert "count: 0" in result


def _read_csv(path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames or [], list(reader)


class TestWriteCsvFile:
    def test_writes_basic(self, tmp_path):
        p = str(tmp_path / "out.csv")
        meta = write_csv_file(p, [{"a": 1, "b": 2}, {"a": 3, "b": 4}])
        assert meta["rows"] == 2
        assert meta["columns"] == 2
        assert meta["dropped"] == 0
        fields, rows = _read_csv(p)
        assert fields == ["a", "b"]
        assert len(rows) == 2

    def test_drops_all_null_columns_by_default(self, tmp_path):
        p = str(tmp_path / "out.csv")
        rows = [
            {"date": "2026-04-01", "has_data": 10, "always_null": None, "always_zero": 0},
            {"date": "2026-04-02", "has_data": 20, "always_null": None, "always_zero": 0},
        ]
        meta = write_csv_file(p, rows)
        assert meta["dropped"] == 2  # always_null + always_zero
        fields, _ = _read_csv(p)
        assert "date" in fields
        assert "has_data" in fields
        assert "always_null" not in fields
        assert "always_zero" not in fields

    def test_keeps_column_with_any_signal(self, tmp_path):
        """A column is kept if AT LEAST ONE row has non-null non-zero value."""
        p = str(tmp_path / "out.csv")
        rows = [
            {"val": 0},
            {"val": 0},
            {"val": 42},  # signal!
            {"val": None},
        ]
        meta = write_csv_file(p, rows)
        assert meta["dropped"] == 0
        fields, _ = _read_csv(p)
        assert "val" in fields

    def test_drop_empty_opt_out(self, tmp_path):
        p = str(tmp_path / "out.csv")
        rows = [{"date": "d1", "null_col": None}, {"date": "d2", "null_col": None}]
        meta = write_csv_file(p, rows, drop_empty=False)
        assert meta["dropped"] == 0
        fields, _ = _read_csv(p)
        assert "null_col" in fields

    def test_keeps_string_columns_with_any_non_empty(self, tmp_path):
        p = str(tmp_path / "out.csv")
        rows = [{"status": "BALANCED"}, {"status": None}, {"status": ""}]
        meta = write_csv_file(p, rows)
        assert meta["dropped"] == 0
        fields, _ = _read_csv(p)
        assert "status" in fields

    def test_drops_all_empty_string_column(self, tmp_path):
        p = str(tmp_path / "out.csv")
        rows = [{"status": ""}, {"status": ""}]
        meta = write_csv_file(p, rows)
        assert meta["dropped"] == 1
        fields, _ = _read_csv(p)
        assert "status" not in fields

    def test_empty_rows_writes_empty_file(self, tmp_path):
        p = str(tmp_path / "out.csv")
        meta = write_csv_file(p, [])
        assert meta["rows"] == 0
        assert meta["columns"] == 0

    def test_preserves_first_seen_column_order(self, tmp_path):
        """Column order = order of first appearance across rows."""
        p = str(tmp_path / "out.csv")
        rows = [
            {"a": 1, "b": 2},  # a,b first
            {"c": 3, "b": 5},  # c appears
            {"a": 4},
        ]
        meta = write_csv_file(p, rows)
        assert meta["dropped"] == 0
        fields, _ = _read_csv(p)
        assert fields == ["a", "b", "c"]
