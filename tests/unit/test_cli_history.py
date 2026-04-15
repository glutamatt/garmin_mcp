"""Unit tests for `garmin history` CLI — CSV output, sandbox, filename echo."""

import csv
import inspect
from pathlib import Path

import pytest
from click.testing import CliRunner

from garmin_mcp.cli import garmin


def _runner():
    kwargs = {}
    if "mix_stderr" in inspect.signature(CliRunner).parameters:
        kwargs["mix_stderr"] = False
    return CliRunner(**kwargs)


def _read_csv(path: str) -> tuple[list[str], list[dict]]:
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames or [], list(reader)


@pytest.fixture
def mock_client():
    """Mock Garmin client with predictable stubs for every history endpoint."""
    from unittest.mock import Mock
    from garmin_mcp.api.history import _daterange

    c = Mock()

    def _connectapi(path, params=None, **_):
        # running / cycling aggregated reports
        if path == "/fitnessstats-service/activity":
            sport = params.get("activityType", "running")
            return [
                {
                    "date": "2026-04-06",
                    "countOfActivities": 3,
                    "stats": {sport: {
                        "distance": {"count": 3, "min": 500000.0, "max": 1200000.0, "avg": 800000.0, "sum": 2400000.0},
                        "avgHr": {"count": 3, "min": 150.0, "max": 170.0, "avg": 160.0, "sum": 480.0},
                    }},
                },
                {
                    "date": "2026-04-13",
                    "countOfActivities": 2,
                    "stats": {sport: {
                        "distance": {"count": 2, "min": 600000.0, "max": 900000.0, "avg": 750000.0, "sum": 1500000.0},
                    }},
                },
            ]
        # heart-rate daily ranged
        if path.startswith("/usersummary-service/stats/heartRate/daily/"):
            parts = path.rsplit("/", 2)
            s, e = parts[-2], parts[-1]
            return [
                {"calendarDate": d, "values": {"restingHR": 57, "wellnessMaxAvgHR": 160, "wellnessMinAvgHR": 55}}
                for d in _daterange(s, e)
            ]
        # heart-rate weekly ranged
        if path.startswith("/usersummary-service/stats/heartRate/weekly/"):
            return [
                {"calendarDate": "2026-04-09", "values": {"avgRestingHR": 59, "wellnessMaxAvgHR": 167, "wellnessMinAvgHR": 57}},
                {"calendarDate": "2026-04-02", "values": {"avgRestingHR": 60, "wellnessMaxAvgHR": 165, "wellnessMinAvgHR": 58}},
            ]
        # vo2max ranged per sport
        if path.startswith("/metrics-service/metrics/maxmet/"):
            sport = (params or {}).get("sport")
            if sport == "running":
                return [
                    {"generic": {"calendarDate": "2026-04-14", "vo2MaxValue": 50, "vo2MaxPreciseValue": 50.4, "fitnessAge": None, "fitnessAgeDescription": None, "maxMetCategory": 0}},
                    {"generic": {"calendarDate": "2026-04-15", "vo2MaxValue": 50, "vo2MaxPreciseValue": 50.5, "fitnessAge": None, "fitnessAgeDescription": None, "maxMetCategory": 0}},
                ]
            return []  # empty cycling
        # sleep ranged endpoint: /sleep-service/stats/sleep/daily/<start>/<end>
        if path.startswith("/sleep-service/stats/sleep/daily/"):
            parts = path.rsplit("/", 2)
            s, e = parts[-2], parts[-1]
            return {
                "overallStats": {"averageSleepScore": 75},
                "individualStats": [
                    {
                        "calendarDate": d,
                        "values": {
                            "sleepScore": 77,
                            "sleepScoreQuality": "FAIR",
                            "totalSleepTimeInSeconds": 24000,
                            "avgOvernightHrv": 45.0,
                            "hrv7dAverage": 43.0,
                            "hrvStatus": "BALANCED",
                            "restingHeartRate": 58,
                        },
                    }
                    for d in _daterange(s, e)
                ],
            }
        raise NotImplementedError(f"Unexpected connectapi call: {path}")
    c.connectapi.side_effect = _connectapi
    # sleep: per-day mock
    c.get_sleep_data.return_value = {
        "dailySleepDTO": {
            "calendarDate": "2026-04-15",
            "sleepTimeSeconds": 24000,
            "sleepScores": {"overall": {"value": 77, "qualifierKey": "FAIR"}},
        }
    }
    # heart-rate: per-day mock
    c.get_heart_rates.return_value = {
        "calendarDate": "2026-04-15",
        "restingHeartRate": 57,
        "maxHeartRate": 167,
        "heartRateValues": [[1, 60], [2, 80]],
    }
    # hrv: per-day mock
    c.get_hrv_data.return_value = {
        "hrvSummary": {"calendarDate": "2026-04-15", "lastNightAvg": 45, "weeklyAvg": 48, "status": "BALANCED"}
    }
    # vo2max: per-day mock
    c.get_max_metrics.return_value = [{"metricType": "RUNNING", "vo2MaxValue": 52.5}]
    # race-predictions: single-call range
    c.get_race_predictions.return_value = [
        {"calendarDate": "2026-04-15", "time5K": 1200, "time10K": 2500},
    ]
    return c


def _invoke(runner, mock_client, tmp_path, *cmd_args):
    return runner.invoke(
        garmin,
        ["--token", "fake", "--tmp-dir", str(tmp_path), "history", *cmd_args],
        obj={"client": mock_client},
        catch_exceptions=True,
    )


class TestHistoryRunning:
    def test_writes_default_filename(self, tmp_path, mock_client):
        result = _invoke(_runner(), mock_client, tmp_path, "running", "--days", "7", "--end", "2026-04-15")
        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert "history_running.csv" in result.output
        assert "2 rows" in result.output
        assert "[2026-04-08 → 2026-04-15]" in result.output

        path = tmp_path / "history_running.csv"
        assert path.exists()
        fields, rows = _read_csv(str(path))
        assert "date" in fields
        assert "countOfActivities" in fields
        assert "distance_sum" in fields
        assert "avgHr_avg" in fields
        assert {r["date"] for r in rows} == {"2026-04-06", "2026-04-13"}

    def test_agg_flag_passes_through(self, tmp_path, mock_client):
        result = _invoke(
            _runner(), mock_client, tmp_path, "running", "--agg", "monthly",
            "--days", "90", "--end", "2026-04-15",
        )
        assert result.exit_code == 0, result.output
        # grab the connectapi call
        p = mock_client.connectapi.call_args[1]["params"]
        assert p["aggregation"] == "monthly"
        assert p["activityType"] == "running"

    def test_invalid_agg_rejected(self, tmp_path, mock_client):
        result = _invoke(_runner(), mock_client, tmp_path, "running", "--agg", "hourly")
        assert result.exit_code != 0
        assert "hourly" in (result.output + (result.stderr or ""))


class TestHistoryCycling:
    def test_cycling_activity_type(self, tmp_path, mock_client):
        result = _invoke(_runner(), mock_client, tmp_path, "cycling", "--days", "7", "--end", "2026-04-15")
        assert result.exit_code == 0, result.output
        p = mock_client.connectapi.call_args[1]["params"]
        assert p["activityType"] == "cycling"
        assert "avgBikeCadence" in p["metric"]
        assert len(p["metric"]) == 35  # same verbatim list for every sport
        path = tmp_path / "history_cycling.csv"
        assert path.exists()


class TestHistoryOutputOverride:
    def test_output_overrides_filename(self, tmp_path, mock_client):
        # --output is a root-group option → must precede the subcommand path
        result = _runner().invoke(
            garmin,
            [
                "--token", "fake",
                "--tmp-dir", str(tmp_path),
                "--output", "my_runs.csv",
                "history", "running",
                "--days", "7",
                "--end", "2026-04-15",
            ],
            obj={"client": mock_client},
            catch_exceptions=True,
        )
        assert result.exit_code == 0, result.output
        assert "my_runs.csv" in result.output
        assert (tmp_path / "my_runs.csv").exists()
        assert not (tmp_path / "history_running.csv").exists()


class TestHistorySleep:
    def test_writes_daily_rows_from_chunked_endpoint(self, tmp_path, mock_client):
        result = _invoke(_runner(), mock_client, tmp_path, "sleep", "--days", "2", "--end", "2026-04-15")
        assert result.exit_code == 0, result.output + (result.stderr or "")
        path = tmp_path / "history_sleep.csv"
        fields, rows = _read_csv(str(path))
        # Raw Garmin field names, passed through
        assert "sleepScore" in fields
        assert "totalSleepTimeInSeconds" in fields
        assert "avgOvernightHrv" in fields  # HRV columns included — no history hrv command
        assert "hrv7dAverage" in fields
        assert "hrvStatus" in fields
        # 3 days (2026-04-13..2026-04-15)
        assert len(rows) == 3
        # Single chunk (3 days fits in 28-day window) → 1 HTTP call
        sleep_calls = [c for c in mock_client.connectapi.call_args_list
                       if c.args and c.args[0].startswith("/sleep-service/stats/sleep/daily/")]
        assert len(sleep_calls) == 1


class TestHistoryHeartRate:
    def test_daily_writes_csv(self, tmp_path, mock_client):
        result = _invoke(
            _runner(), mock_client, tmp_path, "heart-rate", "--days", "2", "--end", "2026-04-15"
        )
        assert result.exit_code == 0, result.output
        path = tmp_path / "history_heart_rate.csv"
        fields, rows = _read_csv(str(path))
        # Raw Garmin field names
        assert "restingHR" in fields
        assert "wellnessMaxAvgHR" in fields
        assert "wellnessMinAvgHR" in fields
        assert len(rows) == 3

    def test_weekly_flag(self, tmp_path, mock_client):
        result = _invoke(
            _runner(), mock_client, tmp_path, "heart-rate", "--agg", "weekly",
            "--days", "30", "--end", "2026-04-15",
        )
        assert result.exit_code == 0, result.output
        path = tmp_path / "history_heart_rate.csv"
        fields, rows = _read_csv(str(path))
        assert "avgRestingHR" in fields  # weekly-specific field
        # Single call, no chunking
        hr_calls = [c for c in mock_client.connectapi.call_args_list
                    if c.args and "/heartRate/weekly/" in c.args[0]]
        assert len(hr_calls) == 1


class TestHistoryVo2Max:
    def test_writes_csv(self, tmp_path, mock_client):
        result = _invoke(_runner(), mock_client, tmp_path, "vo2max", "--days", "30", "--end", "2026-04-15")
        assert result.exit_code == 0, result.output
        path = tmp_path / "history_vo2max.csv"
        fields, rows = _read_csv(str(path))
        assert "vo2MaxPreciseValue" in fields
        assert "sport" in fields
        # 2 running entries, 0 cycling
        assert len(rows) == 2
        assert all(r["sport"] == "running" for r in rows)

    def test_agg_flag(self, tmp_path, mock_client):
        result = _invoke(
            _runner(), mock_client, tmp_path, "vo2max", "--agg", "weekly",
            "--days", "30", "--end", "2026-04-15",
        )
        assert result.exit_code == 0, result.output
        # URL must contain /weekly/
        paths = [c.args[0] for c in mock_client.connectapi.call_args_list
                 if c.args and "/maxmet/" in c.args[0]]
        assert paths, "no maxmet calls captured"
        assert all("/maxmet/weekly/" in p for p in paths)


class TestHistoryRacePredictions:
    def test_single_api_call(self, tmp_path, mock_client):
        result = _invoke(
            _runner(),
            mock_client,
            tmp_path,
            "race-predictions",
            "--days",
            "30",
            "--end",
            "2026-04-15",
        )
        assert result.exit_code == 0, result.output
        # race-predictions uses a single range call regardless of window size
        mock_client.get_race_predictions.assert_called_once_with(
            startdate="2026-03-16", enddate="2026-04-15", _type="daily"
        )
        path = tmp_path / "history_race_predictions.csv"
        fields, rows = _read_csv(str(path))
        assert "race_5k_seconds" in fields
        assert "race_10k_seconds" in fields
        assert len(rows) == 1


class TestHistoryEmpty:
    def test_empty_csv_still_written(self, tmp_path, mock_client):
        # Override the side_effect to return empty for fitnessstats
        mock_client.connectapi.side_effect = lambda path, params=None, **_: []
        result = _invoke(
            _runner(), mock_client, tmp_path, "running", "--days", "7", "--end", "2026-04-15"
        )
        assert result.exit_code == 0, result.output
        assert "0 rows" in result.output
        path = tmp_path / "history_running.csv"
        assert path.exists()
        assert path.read_text() == ""  # empty file


class TestHistoryDescribe:
    def test_history_group_listed(self, tmp_path):
        result = _runner().invoke(
            garmin,
            ["--token", "fake", "describe", "history"],
            catch_exceptions=True,
        )
        assert result.exit_code == 0
        out = result.output
        assert "history running" in out
        assert "history cycling" in out
        assert "history sleep" in out
        assert "history heart-rate" in out
        assert "history hrv" not in out  # dropped — HRV is in history_sleep.csv
        assert "history vo2max" in out
        assert "history race-predictions" in out
