"""Functional tests for read-only CLI commands against real Garmin data.

Run with:
    GARMIN_TOKEN_READONLY=... pytest tests/functional/test_cli_read.py -v
"""

import json
from datetime import datetime, timedelta

import pytest

from garmin_mcp.cli import garmin, execute
from tests.functional.conftest import invoke, invoke_json


# ── Helpers ──────────────────────────────────────────────────────────────────

def today():
    return datetime.now().strftime("%Y-%m-%d")


def yesterday():
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def week_ago():
    return (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")


def month_ago():
    return (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")


# ── Help / basics ────────────────────────────────────────────────────────────


class TestBasics:
    def test_help(self, cli):
        result = cli.invoke(garmin, ["--help"])
        assert result.exit_code == 0
        assert "Garmin Connect CLI" in result.output

    def test_activities_help(self, cli):
        result = cli.invoke(garmin, ["activities", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "get" in result.output

    def test_health_help(self, cli):
        result = cli.invoke(garmin, ["health", "--help"])
        assert result.exit_code == 0
        assert "snapshot" in result.output

    def test_no_token_error(self, cli):
        result = cli.invoke(garmin, ["activities", "list"])
        assert result.exit_code != 0
        assert "token" in result.output.lower() or "token" in getattr(result, "stderr", "").lower()


# ── Activities ───────────────────────────────────────────────────────────────


class TestActivities:
    def test_list_recent(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "activities", "list", "--limit", "3")
        assert "activities" in data
        assert isinstance(data["activities"], list)
        assert len(data["activities"]) <= 3

    def test_list_by_date_range(self, cli, readonly_token):
        data = invoke_json(
            cli, readonly_token,
            "activities", "list", "--from", month_ago(), "--to", today()
        )
        assert "activities" in data or "error" in data

    def test_list_with_fields(self, cli, readonly_token):
        data = invoke_json(
            cli, readonly_token,
            "--fields", "id,name,distance_meters",
            "activities", "list", "--limit", "2",
        )
        if data.get("activities"):
            activity = data["activities"][0]
            assert set(activity.keys()) <= {"id", "name", "distance_meters"}

    def test_list_table_format(self, cli, readonly_token):
        result = invoke(
            cli, readonly_token,
            "--format", "table",
            "activities", "list", "--limit", "3",
        )
        assert result.exit_code == 0
        # Table format should have header line with dashes
        lines = result.output.strip().split("\n")
        assert len(lines) >= 1

    def test_get_activity(self, cli, readonly_token):
        """Get detail of first activity from list."""
        data = invoke_json(cli, readonly_token, "activities", "list", "--limit", "1")
        if not data.get("activities"):
            pytest.skip("No activities found")
        activity_id = data["activities"][0]["id"]

        detail = invoke_json(cli, readonly_token, "activities", "get", str(activity_id))
        assert detail.get("id") == activity_id
        assert "name" in detail

    def test_splits(self, cli, readonly_token):
        """Get splits of first activity."""
        data = invoke_json(cli, readonly_token, "activities", "list", "--limit", "1")
        if not data.get("activities"):
            pytest.skip("No activities found")
        activity_id = data["activities"][0]["id"]

        splits = invoke_json(cli, readonly_token, "activities", "splits", str(activity_id))
        assert "laps" in splits or "error" in splits

    def test_types(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "activities", "types")
        assert "activity_types" in data
        assert len(data["activity_types"]) > 0

    def test_download_csv(self, cli, readonly_token):
        """Download activity as preprocessed CSV and validate structure."""
        import csv
        import os

        # Get a recent activity
        data = invoke_json(cli, readonly_token, "activities", "list", "--limit", "1")
        if not data.get("activities"):
            pytest.skip("No activities found")
        activity_id = data["activities"][0]["id"]

        result = invoke_json(cli, readonly_token, "activities", "download", str(activity_id))

        # Metadata structure
        assert result["activity_id"] == activity_id
        assert result["format"] == "csv"
        assert result["rows"] > 0
        assert result["size_kb"] > 0
        assert isinstance(result["columns"], list)
        assert "timestamp" in result["columns"]
        assert "elapsed_s" in result["columns"]
        assert "heart_rate" in result["columns"]
        assert "speed_ms" in result["columns"]

        # File exists and is valid CSV
        csv_path = result["path"]
        assert os.path.isfile(csv_path)
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == result["rows"]

        # Spot-check first row
        first = rows[0]
        assert first["elapsed_s"] == "0.0"
        assert "T" in first["timestamp"]  # ISO format

        # Cadence column name depends on sport type
        has_cadence = "cadence_spm" in result["columns"] or "cadence_rpm" in result["columns"]
        # Cadence may be absent if no sensor (all-null → dropped)
        if has_cadence and "cadence_spm" in result["columns"]:
            # Running cadence should be doubled (typically 150-200 spm)
            cadences = [int(r["cadence_spm"]) for r in rows if r["cadence_spm"]]
            if cadences:
                assert max(cadences) > 100, "cadence_spm should be doubled (>100 spm)"


# ── Health ───────────────────────────────────────────────────────────────────


class TestHealth:
    def test_snapshot(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "health", "snapshot", yesterday())
        assert "date" in data
        # At least one section should be present
        assert any(
            k in data for k in ("stats", "sleep", "training_readiness", "body_battery", "hrv")
        )

    def test_stats(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "health", "stats", yesterday())
        assert "date" in data or "error" in data

    def test_sleep(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "health", "sleep", yesterday())
        # Either has sleep data or error (no sleep data for date)
        assert isinstance(data, dict)

    def test_stress(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "health", "stress", yesterday())
        assert isinstance(data, dict)

    def test_heart_rate(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "health", "heart-rate", yesterday())
        assert isinstance(data, dict)

    def test_respiration(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "health", "respiration", yesterday())
        assert isinstance(data, dict)

    def test_body_battery(self, cli, readonly_token):
        data = invoke_json(
            cli, readonly_token,
            "health", "body-battery", "--from", week_ago(), "--to", today(),
        )
        assert "days" in data or "error" in data

    def test_spo2(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "health", "spo2", yesterday())
        assert isinstance(data, dict)

    def test_training_readiness(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "health", "training-readiness", yesterday())
        assert isinstance(data, dict)

    def test_snapshot_with_fields(self, cli, readonly_token):
        data = invoke_json(
            cli, readonly_token,
            "--fields", "date,stats",
            "health", "snapshot", yesterday(),
        )
        assert "date" in data or "stats" in data
        assert "sleep" not in data


# ── Training ─────────────────────────────────────────────────────────────────


class TestTraining:
    def test_max_metrics(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "training", "max-metrics", today())
        assert isinstance(data, dict)

    def test_hrv(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "training", "hrv", yesterday())
        assert isinstance(data, dict)

    def test_status(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "training", "status", today())
        assert isinstance(data, dict)

    def test_progress(self, cli, readonly_token):
        data = invoke_json(
            cli, readonly_token,
            "training", "progress",
            "--from", month_ago(), "--to", today(), "--metric", "distance",
        )
        assert "metric" in data or "error" in data

    def test_race_predictions(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "training", "race-predictions")
        assert isinstance(data, (dict, list))

    def test_goals(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "training", "goals")
        assert isinstance(data, (dict, list))

    def test_personal_records(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "training", "personal-records")
        assert isinstance(data, (dict, list))


# ── Profile ──────────────────────────────────────────────────────────────────


class TestProfile:
    def test_name(self, cli, readonly_token):
        result = invoke(cli, readonly_token, "profile", "name")
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0

    def test_info(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "profile", "info")
        # Profile may have display_name, user_profile_id, or settings
        assert "user_profile_id" in data or "display_name" in data or "settings" in data or "error" in data

    def test_devices(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "profile", "devices")
        assert "devices" in data or "error" in data


# ── Calendar ─────────────────────────────────────────────────────────────────


class TestCalendar:
    def test_month(self, cli, readonly_token):
        now = datetime.now()
        data = invoke_json(
            cli, readonly_token,
            "calendar", "month", str(now.year), str(now.month),
        )
        assert "items" in data or "error" in data

    def test_upcoming(self, cli, readonly_token):
        data = invoke_json(cli, readonly_token, "calendar", "upcoming")
        assert isinstance(data, (dict, list))


# ── Output to file ───────────────────────────────────────────────────────────


class TestFileOutput:
    def test_output_to_file(self, cli, readonly_token, tmp_path):
        outfile = str(tmp_path / "activities.json")
        result = invoke(
            cli, readonly_token,
            "--output", outfile,
            "activities", "list", "--limit", "2",
        )
        assert result.exit_code == 0
        assert "Written to" in result.output

        with open(outfile) as f:
            data = json.load(f)
        assert "activities" in data


# ── execute() helper ─────────────────────────────────────────────────────────


class TestExecuteHelper:
    """Test the execute() function used by the HTTP handler."""

    def test_execute_basic(self, readonly_token):
        result = execute("activities list --limit 2", readonly_token)
        assert result["exit_code"] == 0
        data = json.loads(result["stdout"])
        assert "activities" in data

    def test_execute_with_fields(self, readonly_token):
        result = execute("--fields id,name activities list --limit 1", readonly_token)
        assert result["exit_code"] == 0
        data = json.loads(result["stdout"])
        if data.get("activities"):
            assert set(data["activities"][0].keys()) <= {"id", "name"}

    def test_execute_bad_command(self, readonly_token):
        result = execute("nonexistent command", readonly_token)
        assert result["exit_code"] != 0
