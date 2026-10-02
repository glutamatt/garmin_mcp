"""The output contract, seen from `execute()` (the `/cli` endpoint Apex calls).

- empty → a normal answer, exit 0;
- unavailable → `{"available": false, "reason"}`, exit 0, `--fields` keeps the reason;
- failure → message on stderr, nothing on stdout, exit 1 (2 for invalid input);
  `--fields` and `--output` never apply to it.
"""

import json
import os
import subprocess
import sys
import textwrap
from unittest.mock import Mock, patch

import pytest
from garminconnect import GarminConnectConnectionError, GarminConnectTooManyRequestsError
from garth.exc import GarthHTTPError
from requests import HTTPError

from garmin_mcp.api.contract import (
    AuthError,
    GarminError,
    NotFound,
    RateLimited,
    Unavailable,
    as_garmin_error,
)
from garmin_mcp.cli import execute
from garmin_mcp.client_factory import GarminTokenError


def _run(command: str, client: Mock, tmp_dir: str | None = None) -> dict:
    with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
        return execute(command, "fake_token", tmp_dir=tmp_dir)


def _http_error(status: int) -> Exception:
    """What the SDK raises for an HTTP error: its own error, caused by garth's."""
    response = Mock(status_code=status)
    garth_error = GarthHTTPError(msg="Error in request", error=HTTPError(response=response))
    try:
        raise GarminConnectConnectionError(f"API client error ({status})") from garth_error
    except GarminConnectConnectionError as e:
        return e


# ── Empty ────────────────────────────────────────────────────────────────────


class TestEmpty:
    def test_empty_schedule_is_an_answer(self):
        client = Mock()
        client.get_scheduled_workouts_for_range.return_value = []
        result = _run("workouts scheduled --from 2027-01-01 --to 2027-01-31", client)
        assert result["exit_code"] == 0
        assert result["stderr"] == ""
        assert json.loads(result["stdout"])["count"] == 0

    def test_empty_list_with_fields_keeps_its_shape_and_warns_nothing(self):
        client = Mock()
        client.get_activities_by_date.return_value = []
        result = _run("activities list --from 2024-01-01 --to 2024-01-07 --fields id,name", client)
        assert result["exit_code"] == 0
        assert result["stderr"] == ""
        assert json.loads(result["stdout"]) == {
            "count": 0,
            "date_range": {"start": "2024-01-01", "end": "2024-01-07"},
            "activities": [],
        }

    @pytest.mark.parametrize("command, method, list_key", [
        ("calendar month 2024 1", "get_calendar_month", "items"),
        ("calendar upcoming --days 7", "get_calendar_items_for_range", "items"),
        ("body weigh-ins --from 2024-01-01 --to 2024-01-31", "get_weigh_ins", "measurements"),
    ])
    def test_cli_curated_lists_are_empty_answers(self, command, method, list_key):
        client = Mock()
        getattr(client, method).return_value = None
        result = _run(command, client)
        assert result["exit_code"] == 0
        data = json.loads(result["stdout"])
        assert data["count"] == 0
        assert data[list_key] == []

    def test_no_event_is_an_empty_list(self):
        client = Mock()
        client.garth.connectapi.return_value = None
        result = _run("calendar events --from 2024-01-01 --to 2024-01-31", client)
        assert result["exit_code"] == 0
        assert json.loads(result["stdout"]) == []


# ── Unavailable ──────────────────────────────────────────────────────────────


class TestUnavailable:
    def test_day_without_data_is_an_answer_that_says_why(self):
        client = Mock()
        client.get_training_readiness.return_value = []
        result = _run("health training-readiness 2024-01-15", client)
        assert result["exit_code"] == 0
        assert json.loads(result["stdout"]) == {
            "date": "2024-01-15", "available": False, "reason": "no_data",
        }

    def test_fields_keep_the_reason(self):
        client = Mock()
        client.get_hrv_data.return_value = None
        result = _run("training hrv 2024-01-15 --fields last_night_avg_hrv_ms", client)
        assert result["exit_code"] == 0
        assert result["stderr"] == ""
        assert json.loads(result["stdout"])["reason"] == "no_data"


# ── Failure ──────────────────────────────────────────────────────────────────


class TestFailure:
    def test_not_found_exits_1_with_message_on_stderr_only(self):
        client = Mock()
        client.get_activity.return_value = None
        result = _run("activities get 999", client)
        assert result["exit_code"] == 1
        assert result["stdout"] == ""
        assert result["stderr"] == "Error: No activity 999\n"

    def test_fields_and_output_never_apply_to_a_failure(self, tmp_path):
        client = Mock()
        client.get_activity.return_value = None
        result = _run("activities get 999 --fields id,name --output act.json", client, str(tmp_path))
        assert result["exit_code"] == 1
        assert result["stdout"] == ""
        assert "unknown fields" not in result["stderr"]
        assert "No activity 999" in result["stderr"]
        assert not os.path.exists(tmp_path / "act.json")

    def test_rate_limit_is_a_failure(self):
        client = Mock()
        client.get_activities_by_date.side_effect = GarminConnectTooManyRequestsError("Rate limit exceeded")
        result = _run("activities list --from 2024-01-01 --to 2024-01-07", client)
        assert result["exit_code"] == 1
        assert "rate limit (HTTP 429)" in result["stderr"]

    def test_failed_mutation_exits_1(self):
        client = Mock()
        client.unschedule_workout.return_value = False
        result = _run("workouts unschedule 99", client)
        assert result["exit_code"] == 1
        assert result["stdout"] == ""
        assert "did not unschedule 99" in result["stderr"]

    @pytest.mark.parametrize("command, method", [
        ("calendar month 2024 1", "get_calendar_month"),
        ("body weigh-ins --from 2024-01-01 --to 2024-01-31", "get_weigh_ins"),
        ("profile name", "get_full_name"),
    ])
    def test_commands_curated_in_the_cli_report_their_failure(self, command, method):
        """These commands called Garmin outside `_run`: a failure was exit 1 with an empty stderr."""
        client = Mock()
        getattr(client, method).side_effect = GarminConnectConnectionError("Connection error: timeout")
        result = _run(command, client)
        assert result["exit_code"] == 1
        assert "Garmin did not answer" in result["stderr"]

    def test_uncaught_exception_still_says_why(self):
        """Last safety net of `execute()`: an exception outside any `_run` is reported."""
        result = _run("history running --end not-a-date", Mock())
        assert result["exit_code"] == 1
        assert result["stderr"].startswith("Error: ValueError: ")

    def test_library_logs_stay_out_of_the_command_stderr(self):
        """The SDK logs a traceback on every HTTP error: it belongs in the server log.

        Run in a fresh process like the server (`create_app()` first): under pytest,
        pytest's own log handler hides the leak.
        """
        script = textwrap.dedent("""
            import json, logging
            from unittest.mock import Mock, patch
            from garmin_mcp.server import create_app
            from garmin_mcp.cli import execute

            create_app()
            client = Mock()
            client.garth.dumps.return_value = "fake"  # the token did not change
            def get_activity(activity_id):
                logging.getLogger("garminconnect").exception("API call failed")
                raise RuntimeError("404")
            client.get_activity.side_effect = get_activity
            with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
                print(json.dumps(execute("activities get 1", "fake")))
        """)
        process = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
        result = json.loads(process.stdout.strip().splitlines()[-1])
        assert result["exit_code"] == 1
        assert result["stderr"] == "Error: RuntimeError: 404\n"
        assert "API call failed" in process.stderr  # the server log

    def test_usage_error_is_not_copied_to_stdout(self):
        result = _run("activities list --bogus", Mock())
        assert result["exit_code"] == 2
        assert result["stdout"] == ""
        assert "No such option" in result["stderr"]


# ── Invalid input: exit 2 ────────────────────────────────────────────────────


class TestInvalidInput:
    def test_invalid_inline_json(self):
        result = _run("workouts create --json {bad --dry-run", Mock())
        assert result["exit_code"] == 2
        assert "Invalid JSON" in result["stderr"]

    def test_workout_must_be_an_object(self):
        result = _run('workouts create --json ["a"] --dry-run', Mock())
        assert result["exit_code"] == 2
        assert "JSON object" in result["stderr"]

    def test_missing_input_file(self, tmp_path):
        result = _run("workouts create --input nope.json --dry-run", Mock(), str(tmp_path))
        assert result["exit_code"] == 2
        assert "File not found" in result["stderr"]

    def test_json_and_input_together(self, tmp_path):
        result = _run('workouts create --json {"a":1} --input w.json', Mock(), str(tmp_path))
        assert result["exit_code"] == 2
        assert "not both" in result["stderr"]

    def test_unknown_describe_path(self):
        result = _run("describe nonexistent", Mock())
        assert result["exit_code"] == 2
        assert "Unknown command" in result["stderr"]

    def test_history_window_too_long(self, tmp_path):
        result = _run("history race-predictions --days 400 --end 2024-12-31", Mock(), str(tmp_path))
        assert result["exit_code"] == 2
        assert "capped at 365 days" in result["stderr"]

    @pytest.mark.parametrize("command, method", [
        ("activities get 1", "get_activity"),
        ("activities splits 1", "get_activity_splits"),
    ])
    def test_unknown_field_is_refused_before_garmin_is_called(self, command, method):
        client = Mock()
        result = _run(f"{command} --fields distance_meters", client)
        assert result["exit_code"] == 2
        assert result["stdout"] == ""
        assert "Unknown fields" in result["stderr"] and "distance_m" in result["stderr"]
        getattr(client, method).assert_not_called()


# ── Field registry: a known field is never "unknown" ─────────────────────────


class TestEmptyFields:
    def test_detail_says_which_fields_are_empty_and_why(self):
        client = Mock()
        client.get_activity.return_value = {"activityId": 1, "summaryDTO": {"distance": 5000.0}}
        client.get_activity_weather.return_value = None
        result = _run("activities get 1 --fields distance_m,training_load,vo2_max", client)
        assert result["exit_code"] == 0
        assert result["stderr"] == ""
        assert json.loads(result["stdout"]) == {
            "distance_m": 5000,
            "empty_fields": {"training_load": "no_data", "vo2_max": "only_in: activities list"},
        }

    def test_laps_say_which_fields_are_empty_and_why(self):
        client = Mock()
        client.get_activity_splits.return_value = {"lapDTOs": [{"lapIndex": 1, "distance": 1000.0}]}
        client.get_activity.return_value = {"summaryDTO": {}}
        result = _run("activities splits 1 --fields lap_number,gap_s_per_km,perceived_effort", client)
        assert result["exit_code"] == 0
        assert json.loads(result["stdout"]) == {
            "activity_id": 1, "lap_count": 1, "laps": [{"lap_number": 1}],
            "empty_fields": {"gap_s_per_km": "no_data", "perceived_effort": "only_in: activities get"},
        }


# ── as_garmin_error ──────────────────────────────────────────────────────────


class TestAsGarminError:
    @pytest.mark.parametrize("status, kind", [
        (401, AuthError), (404, NotFound), (429, RateLimited), (500, Unavailable),
    ])
    def test_http_status_from_the_chain_of_causes(self, status, kind):
        assert type(as_garmin_error(_http_error(status))) is kind

    def test_unreadable_token_is_an_auth_error_with_its_message(self):
        error = as_garmin_error(GarminTokenError("Garmin is not available in this session"))
        assert isinstance(error, AuthError)
        assert str(error) == "Garmin is not available in this session"

    def test_typed_error_is_kept(self):
        error = NotFound("No workout 1")
        assert as_garmin_error(error) is error

    def test_other_exception_keeps_its_type_name(self):
        error = as_garmin_error(KeyError("steps"))
        assert type(error) is GarminError
        assert str(error) == "KeyError: 'steps'"
