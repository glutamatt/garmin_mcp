"""Unit tests for CLI core: input validation, path sandboxing, dry-run, describe."""

import inspect
import json
import os

import pytest
from click.testing import CliRunner

from garmin_mcp.cli import (
    _sanitize_path,
    _validate_command,
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
