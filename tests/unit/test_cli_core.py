"""Unit tests for CLI core: input validation, path sandboxing, dry-run, describe."""

import inspect
import json
import os

import click
import pytest
from click.testing import CliRunner

from garmin_mcp.cli import (
    _sanitize_path,
    _session_sandbox,
    _validate_command,
    _hoist_global_flags,
    garmin,
    execute,
    SANDBOX_DIR,
)


def _runner():
    """Create CliRunner compatible with Click 8.1 and 8.3+."""
    kwargs = {}
    if "mix_stderr" in inspect.signature(CliRunner).parameters:
        kwargs["mix_stderr"] = False
    return CliRunner(**kwargs)


class TestValidateCommand:
    def test_normal_command(self):
        assert _validate_command("activities list --limit 5") == "activities list --limit 5"

    def test_strips_whitespace(self):
        assert _validate_command("  activities list  ") == "activities list"

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Empty command"):
            _validate_command("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValueError, match="Empty command"):
            _validate_command("   ")

    def test_rejects_control_chars(self):
        with pytest.raises(ValueError, match="Control character"):
            _validate_command("activities\x00list")

    def test_rejects_semicolon(self):
        with pytest.raises(ValueError, match="Shell metacharacter"):
            _validate_command("activities list; rm -rf /")

    def test_rejects_pipe(self):
        with pytest.raises(ValueError, match="Shell metacharacter"):
            _validate_command("activities list | grep run")

    def test_rejects_and(self):
        with pytest.raises(ValueError, match="Shell metacharacter"):
            _validate_command("activities list && echo pwned")

    def test_rejects_or(self):
        with pytest.raises(ValueError, match="Shell metacharacter"):
            _validate_command("activities list || true")

    def test_rejects_backtick(self):
        with pytest.raises(ValueError, match="Shell metacharacter"):
            _validate_command("activities list `whoami`")

    def test_rejects_dollar_paren(self):
        with pytest.raises(ValueError, match="Shell metacharacter"):
            _validate_command("activities list $(id)")

    def test_rejects_dollar_brace(self):
        with pytest.raises(ValueError, match="Shell metacharacter"):
            _validate_command("activities list ${HOME}")

    def test_rejects_redirect(self):
        with pytest.raises(ValueError, match="Shell metacharacter"):
            _validate_command("activities list > /etc/passwd")


class TestHoistGlobalFlags:
    def test_flags_already_at_front(self):
        args = ["--fields", "id,name", "activities", "list"]
        assert _hoist_global_flags(args) == ["--fields", "id,name", "activities", "list"]

    def test_flags_after_subcommand(self):
        args = ["activities", "list", "--fields", "id,name", "--limit", "5"]
        result = _hoist_global_flags(args)
        assert result == ["--fields", "id,name", "activities", "list", "--limit", "5"]

    def test_multiple_global_flags(self):
        args = ["activities", "list", "--fields", "id", "--format", "table", "--limit", "3"]
        result = _hoist_global_flags(args)
        assert result[:4] == ["--fields", "id", "--format", "table"]
        assert "activities" in result
        assert "--limit" in result

    def test_dry_run_boolean(self):
        args = ["workouts", "create", "--dry-run", "--json", "{}"]
        result = _hoist_global_flags(args)
        assert result[0] == "--dry-run"
        assert "workouts" in result

    def test_output_flag(self):
        args = ["activities", "list", "--output", "/tmp/garmin/test.json"]
        result = _hoist_global_flags(args)
        assert result[:2] == ["--output", "/tmp/garmin/test.json"]

    def test_no_global_flags(self):
        args = ["activities", "list", "--limit", "5"]
        assert _hoist_global_flags(args) == args

    def test_equals_style(self):
        args = ["activities", "list", "--fields=id,name"]
        result = _hoist_global_flags(args)
        assert result[0] == "--fields=id,name"


class TestSanitizePath:
    def test_absolute_under_sandbox(self):
        result = _sanitize_path("/tmp/garmin/data.json")
        assert result == "/tmp/garmin/data.json"

    def test_nested_under_sandbox(self):
        result = _sanitize_path("/tmp/garmin/sub/data.json")
        assert result.startswith(SANDBOX_DIR)

    def test_traversal_gets_sandboxed(self):
        result = _sanitize_path("/tmp/garmin/../../etc/passwd")
        # Should be sandboxed — basename "passwd" under SANDBOX_DIR
        assert result.startswith(SANDBOX_DIR)
        assert "etc" not in result

    def test_relative_gets_sandboxed(self):
        result = _sanitize_path("output.json")
        assert result.startswith(SANDBOX_DIR)
        assert result.endswith("output.json")

    def test_absolute_outside_sandbox(self):
        result = _sanitize_path("/home/user/data.json")
        assert result == os.path.join(SANDBOX_DIR, "data.json")

    def test_session_sandbox(self):
        """Files are sandboxed under session tmp_dir."""
        result = _sanitize_path("data.json", "/tmp/s/abc123")
        assert result == "/tmp/s/abc123/data.json"

    def test_session_sandbox_traversal(self):
        """Traversal from session sandbox still stays sandboxed."""
        result = _sanitize_path("/tmp/s/abc123/../../etc/passwd", "/tmp/s/abc123")
        assert result.startswith("/tmp/s/abc123")
        assert "etc" not in result


class TestSessionSandbox:
    def test_with_tmp_dir(self):
        ctx = click.Context(garmin, obj={"_tmp_dir": "/tmp/s/abc123"})
        assert _session_sandbox(ctx) == "/tmp/s/abc123"

    def test_without_tmp_dir(self):
        ctx = click.Context(garmin, obj={})
        assert _session_sandbox(ctx) == SANDBOX_DIR

    def test_rejects_non_tmp_dir(self):
        """tmp_dir outside /tmp/ falls back to SANDBOX_DIR."""
        ctx = click.Context(garmin, obj={"_tmp_dir": "/home/evil"})
        assert _session_sandbox(ctx) == SANDBOX_DIR

    def test_none_tmp_dir(self):
        ctx = click.Context(garmin, obj={"_tmp_dir": None})
        assert _session_sandbox(ctx) == SANDBOX_DIR


class TestExecuteValidation:
    def test_rejects_shell_injection(self):
        result = execute("activities list; rm -rf /", "fake_token")
        assert result["exit_code"] == 2
        assert "Shell metacharacter" in result["stderr"]

    def test_rejects_control_chars(self):
        result = execute("activities\x00list", "fake_token")
        assert result["exit_code"] == 2
        assert "Control character" in result["stderr"]

    def test_rejects_empty(self):
        result = execute("", "fake_token")
        assert result["exit_code"] == 2
        assert "Empty command" in result["stderr"]


class TestJsonExtraction:
    """Test that --json values survive shlex.split (unquoted JSON from AI agents)."""

    def test_unquoted_json_create(self):
        result = execute('--dry-run workouts create --json {"workoutName":"Test","steps":[]}', "fake")
        assert result["exit_code"] == 0
        data = json.loads(result["stdout"])
        assert data["name"] == "Test"

    def test_nested_json(self):
        result = execute('--dry-run workouts create --json {"workoutName":"Tempo","sportType":{"sportTypeId":1}}', "fake")
        assert result["exit_code"] == 0
        data = json.loads(result["stdout"])
        assert data["name"] == "Tempo"

    def test_json_with_trailing_flags(self):
        result = execute('workouts create --json {"workoutName":"Test","steps":[]} --dry-run --date 2026-03-15', "fake")
        assert result["exit_code"] == 0
        data = json.loads(result["stdout"])
        assert data["dry_run"] is True
        assert data["date"] == "2026-03-15"

    def test_quoted_json_still_works(self):
        result = execute("--dry-run workouts create --json '{}'", "fake")
        assert result["exit_code"] == 0


class TestDryRun:
    """Test --dry-run flag on mutation commands (no real API calls)."""

    def test_dry_run_needs_no_token(self):
        """--dry-run should validate and return preview even with a bad token."""
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake_token_for_dry_run",
            "--dry-run",
            "workouts", "create",
            "--json", json.dumps({"workoutName": "Test", "steps": []}),
        ], catch_exceptions=True)
        # Should succeed (dry_run intercepts before API call)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert data["action"] == "create_workout"
        assert data["name"] == "Test"

    def test_dry_run_delete(self):
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "--dry-run",
            "workouts", "delete", "12345",
        ], catch_exceptions=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert data["action"] == "delete_workout"
        assert data["workout_id"] == 12345

    def test_dry_run_add_weight(self):
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "--dry-run",
            "body", "add-weight", "75.5", "--unit", "kg",
        ], catch_exceptions=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert data["action"] == "add_weight"
        assert data["weight"] == 75.5

    def test_no_dry_run_on_reads(self):
        """Read commands ignore --dry-run (no preview to show)."""
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "--dry-run",
            "activities", "list",
        ], catch_exceptions=True)
        # This will fail because fake token can't create a client,
        # but the point is it DOESN'T short-circuit with dry_run preview
        assert result.exit_code != 0  # No client, so errors

    def test_dry_run_warns_unknown_keys(self):
        """--dry-run should surface unknown key warnings."""
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "--dry-run",
            "workouts", "create",
            "--json", json.dumps({
                "workoutName": "Test",
                "sport": "running",
                "bogusField": 42,
                "steps": [{"stepOrder": 1, "stepType": "warmup", "endCondition": "time", "endConditionValue": 600}],
            }),
        ], catch_exceptions=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert "warnings" in data
        assert any("bogusField" in w for w in data["warnings"])

    def test_dry_run_warns_empty_steps(self):
        """--dry-run should warn about workouts with no steps."""
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "--dry-run",
            "workouts", "create",
            "--json", json.dumps({"workoutName": "Empty", "sport": "running"}),
        ], catch_exceptions=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert any("no steps" in w for w in data.get("warnings", []))

    def test_dry_run_no_warnings_for_valid_workout(self):
        """Valid workout should have no warnings in dry-run."""
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "--dry-run",
            "workouts", "create",
            "--json", json.dumps({
                "workoutName": "Good Workout",
                "sport": "running",
                "steps": [{"stepOrder": 1, "stepType": "warmup", "endCondition": "time", "endConditionValue": 600}],
            }),
        ], catch_exceptions=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "warnings" not in data


class TestDescribe:
    def test_describe_all(self):
        runner = _runner()
        result = runner.invoke(garmin, ["describe"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        commands = data["commands"]
        # Should have all our commands
        names = [c["command"] for c in commands]
        assert "activities list" in names
        assert "health snapshot" in names
        assert "workouts create" in names

    def test_describe_group(self):
        runner = _runner()
        result = runner.invoke(garmin, ["describe", "activities"], catch_exceptions=False)
        assert result.exit_code == 0
        data = json.loads(result.output)
        names = [c["command"] for c in data["commands"]]
        assert all(n.startswith("activities ") for n in names)
        assert not any("health" in n for n in names)

    def test_describe_includes_params(self):
        runner = _runner()
        result = runner.invoke(garmin, ["describe", "activities"], catch_exceptions=False)
        data = json.loads(result.output)
        list_cmd = next(c for c in data["commands"] if c["command"] == "activities list")
        param_names = [p["name"] for p in list_cmd["params"]]
        assert "--from" in param_names or "--limit" in param_names

    def test_describe_unknown_command(self):
        runner = _runner()
        result = runner.invoke(garmin, ["describe", "nonexistent"], catch_exceptions=True)
        assert result.exit_code != 0
