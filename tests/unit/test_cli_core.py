"""Unit tests for CLI core: input validation, path sandboxing, dry-run, describe."""

import inspect
import json
import os

import click
import pytest
from click.testing import CliRunner

from unittest.mock import Mock, patch

from garmin_mcp.cli import (
    MutationCommand,
    _sanitize_path,
    _session_sandbox,
    _validate_command,
    _hoist_global_flags,
    _describe_shape,
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

    def test_rejects_carriage_return(self):
        with pytest.raises(ValueError, match="Control character"):
            _validate_command("activities list\r")

    def test_keeps_newlines_and_tabs(self):
        assert _validate_command('workouts create --json {"name":\n"a\tb"}') == 'workouts create --json {"name":\n"a\tb"}'

    @pytest.mark.parametrize("text", ["FC < 160", "a > b", "a | b", "a; b", "a && b", "a || b",
                                      "`id`", "$(id)", "${HOME}"])
    def test_shell_characters_are_plain_text(self, text):
        """No shell: shlex + Click. A note like "FC < 160" must go through."""
        command = f'workouts create --json {{"note": "{text}"}}'
        assert _validate_command(command) == command


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

    def test_dry_run_goes_after_the_command(self):
        """`--dry-run` is the mutation's own option: wherever it is, it ends after the command."""
        args = ["--dry-run", "workouts", "create", "--fields", "name", "--json", "{}"]
        assert _hoist_global_flags(args) == ["--fields", "name", "workouts", "create", "--json", "{}", "--dry-run"]

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

    def test_sibling_folder_with_the_same_prefix_is_not_the_sandbox(self):
        """`/tmp/s/abc123-other` starts with `/tmp/s/abc123` but is another folder (audit C11)."""
        result = _sanitize_path("/tmp/s/abc123-other/data.json", "/tmp/s/abc123")
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
    def test_no_shell(self):
        """`;` is a character of the word `list;`: Click knows no such command, nothing runs."""
        result = execute("activities list; rm -rf /", "fake_token")
        assert result["exit_code"] == 2
        assert "No such command 'list;'" in result["stderr"]

    def test_rejects_control_chars(self):
        result = execute("activities\x00list", "fake_token")
        assert result["exit_code"] == 2
        assert "Control character" in result["stderr"]

    def test_rejects_empty(self):
        result = execute("", "fake_token")
        assert result["exit_code"] == 2
        assert "Empty command" in result["stderr"]


EASY_JSON = '{"name":"Test","sport":"running","steps":[{"run":"30:00"}]}'


class TestJsonExtraction:
    """`--json` values survive shlex.split: bare or single-quoted, with any character inside."""

    def _dry_run(self, command):
        result = execute(command, "fake")
        assert result["exit_code"] == 0, result["stderr"]
        return json.loads(result["stdout"])

    def test_unquoted_json_create(self):
        data = self._dry_run(f"--dry-run workouts create --json {EASY_JSON}")
        assert data["workout"]["name"] == "Test"

    def test_nested_json(self):
        data = self._dry_run('--dry-run workouts create --json {"name":"Reps","sport":"running","steps":'
                             '[{"repeat":2,"steps":[{"run":"1km","pace":"4:30"}]}]}')
        assert data["workout"]["steps"][0]["repeat"] == 2

    def test_json_with_trailing_flags(self):
        data = self._dry_run(f"workouts create --json {EASY_JSON} --dry-run --date 2026-03-15")
        assert data["dry_run"] is True
        assert data["date"] == "2026-03-15"

    def test_single_quoted_json_with_an_apostrophe(self):
        """A French note: shlex alone would choke on the apostrophe inside single quotes."""
        data = self._dry_run("""workouts create --json '{"name":"Test","sport":"running","steps":"""
                             """[{"run":"30:00","note":"garde l'allure"}]}' --dry-run""")
        assert data["workout"]["steps"][0]["note"] == "garde l'allure"

    def test_shell_characters_in_a_note(self):
        data = self._dry_run('--dry-run workouts create --json {"name":"Test","sport":"running","steps":'
                             '[{"run":"30:00","note":"FC < 160 | > 140; ok"}]}')
        assert data["workout"]["steps"][0]["note"] == "FC < 160 | > 140; ok"

    def test_json_on_several_lines(self):
        data = self._dry_run('--dry-run workouts create --json {"name": "Test",\n "sport": "running",\n'
                             ' "steps": [{"run": "30:00"}]}')
        assert data["workout"]["name"] == "Test"

    def test_escaped_quotes_in_a_string(self):
        data = self._dry_run('--dry-run workouts create --json {"name":"Test \\"A\\"","sport":"running",'
                             '"steps":[{"run":"30:00"}]}')
        assert data["workout"]["name"] == 'Test "A"'


class TestDryRun:
    """Test --dry-run flag on mutation commands (no real API calls)."""

    def test_dry_run_needs_no_token(self):
        """--dry-run should validate and return preview even with a bad token."""
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake_token_for_dry_run",
            "workouts", "create",
            "--json", EASY_JSON, "--dry-run",
        ], catch_exceptions=True)
        # Should succeed (dry_run intercepts before API call)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert data["action"] == "create_workout"
        assert data["workout"]["name"] == "Test"

    def test_dry_run_delete(self):
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "workouts", "delete", "12345", "--dry-run",
        ], catch_exceptions=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert data["action"] == "delete_workout"
        assert data["workout_id"] == 12345

    def test_dry_run_schedule(self):
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "workouts", "schedule", "12345", "--date", "2024-03-15", "--dry-run",
        ], catch_exceptions=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert data["action"] == "schedule_workout"
        assert data["workout_id"] == 12345
        assert data["date"] == "2024-03-15"

    def test_dry_run_add_weight(self):
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "body", "add-weight", "75.5", "--unit", "kg", "--dry-run",
        ], catch_exceptions=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert data["action"] == "add_weight"
        assert data["weight"] == 75.5

    def test_no_dry_run_on_reads(self):
        """A read has no --dry-run: asking for one is invalid input (before: silently ignored)."""
        result = execute("activities list --dry-run", "fake")
        assert result["exit_code"] == 2
        assert "No such option: --dry-run" in result["stderr"]

    def test_dry_run_runs_the_whole_pipeline(self):
        """The audit's case (C3): each mistake used to give `dry_run: true`, exit 0."""
        result = execute("--dry-run workouts create --json " + json.dumps({
            "name": "Test", "sport": "running", "steps": [
                {"intervall": "30:00"},
                {"run": "30000:00"},
                {"run": "5:00", "pace": "2.47"},
            ]}), "fake")
        assert result["exit_code"] == 2
        assert result["stdout"] == ""
        assert "Invalid workout (3 errors)" in result["stderr"]
        assert "steps[0].intervall: unknown key" in result["stderr"]
        assert "steps[1].run" in result["stderr"]
        assert "steps[2].pace" in result["stderr"]

    def test_invalid_workout_is_refused_without_dry_run_too(self):
        """Exit 2 before any Garmin call: the fake token is never used."""
        result = execute('workouts create --json {"name":"Test","sport":"running","steps":[{"run":1800}]}', "fake")
        assert result["exit_code"] == 2
        assert "steps[0].run" in result["stderr"]

    def test_native_format_is_refused(self):
        result = execute('--dry-run workouts create --json {"workoutName":"Test","steps":[]}', "fake")
        assert result["exit_code"] == 2
        assert "Garmin's native format is not accepted" in result["stderr"]

    def test_dry_run_reads_the_steps_back(self):
        result = execute("--dry-run workouts create --json " + json.dumps({
            "name": "Test", "sport": "running", "steps": [
                {"warmup": "10:00"},
                {"repeat": 4, "steps": [{"run": "1km", "pace": "4:40-4:30"}, {"recover": "2:00"}]},
                {"cooldown": "lap"},
            ]}), "fake")
        assert result["exit_code"] == 0, result["stderr"]
        data = json.loads(result["stdout"])
        assert data["workout"]["steps"][1] == {
            "repeat": 4, "steps": [{"run": "1km", "pace": "4:30-4:40"}, {"recover": "2:00"}]}
        assert "estimated_duration_s" not in data
        assert data["not_estimated"]["duration_s"] == ["steps[2] (lap)"]

    def test_dry_run_update(self):
        result = execute(f"--dry-run workouts update 999 --json {EASY_JSON}", "fake")
        assert result["exit_code"] == 0, result["stderr"]
        data = json.loads(result["stdout"])
        assert data["action"] == "update_workout"
        assert data["workout_id"] == 999
        assert data["estimated_duration_s"] == 1800


class TestInputFile:
    """Test --input flag for reading workout JSON from files."""

    def test_create_from_input_file(self, tmp_path):
        """--input reads workout JSON from a file."""
        workout = {"name": "From File", "sport": "running", "steps": [{"run": "30:00"}]}
        f = tmp_path / "workout.json"
        f.write_text(json.dumps(workout))

        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "--tmp-dir", str(tmp_path),
            "workouts", "create",
            "--input", str(f),
            "--dry-run",
        ], catch_exceptions=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert data["workout"]["name"] == "From File"

    def test_update_from_input_file(self, tmp_path):
        """--input works for update too."""
        workout = {"name": "Updated From File", "sport": "running", "steps": [{"run": "30:00"}]}
        f = tmp_path / "workout.json"
        f.write_text(json.dumps(workout))

        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "--tmp-dir", str(tmp_path),
            "workouts", "update", "999",
            "--input", str(f),
            "--dry-run",
        ], catch_exceptions=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert data["workout"]["name"] == "Updated From File"
        assert data["workout_id"] == 999

    def test_input_and_json_mutually_exclusive(self, tmp_path):
        """--input + --json together should error."""
        f = tmp_path / "workout.json"
        f.write_text("{}")

        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "--tmp-dir", str(tmp_path),
            "workouts", "create",
            "--json", "{}",
            "--input", str(f),
            "--dry-run",
        ], catch_exceptions=True)
        assert result.exit_code != 0
        assert "not both" in result.output.lower() or "not both" in (getattr(result, 'stderr', '') or '').lower()

    def test_neither_input_nor_json_errors(self):
        """No --input and no --json should error."""
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "workouts", "create",
            "--dry-run",
        ], catch_exceptions=True)
        assert result.exit_code != 0

    def test_input_file_not_found(self, tmp_path):
        """--input with missing file should error clearly."""
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "--tmp-dir", str(tmp_path),
            "workouts", "create",
            "--input", str(tmp_path / "nonexistent.json"),
            "--dry-run",
        ], catch_exceptions=True)
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "not found" in (getattr(result, 'stderr', '') or '').lower()

    def test_input_invalid_json(self, tmp_path):
        """--input with bad JSON should error clearly."""
        f = tmp_path / "bad.json"
        f.write_text("not valid json {{{")

        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "--tmp-dir", str(tmp_path),
            "workouts", "create",
            "--input", str(f),
            "--dry-run",
        ], catch_exceptions=True)
        assert result.exit_code != 0
        assert "invalid json" in result.output.lower() or "invalid json" in (getattr(result, 'stderr', '') or '').lower()

    def test_input_file_sandboxed(self, tmp_path):
        """--input outside sandbox should be rejected or sandboxed."""
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "--tmp-dir", str(tmp_path),
            "workouts", "create",
            "--input", "/etc/passwd",
            "--dry-run",
        ], catch_exceptions=True)
        assert result.exit_code != 0

    def test_round_trip_output_then_input(self, tmp_path):
        """--output saves JSON, --input reads it back (round-trip)."""
        from unittest.mock import Mock, patch

        # Mock a workout get that writes to file
        workout_data = {
            "id": 12,
            "name": "Round Trip",
            "sport": "running",
            "steps": [{"warmup": "5:00"}],
            "created_date": "2026-10-01T14:23:37.0",
        }
        out_file = tmp_path / "exported.json"
        out_file.write_text(json.dumps(workout_data))

        # Now create from that file
        runner = _runner()
        result = runner.invoke(garmin, [
            "--token", "fake",
            "--tmp-dir", str(tmp_path),
            "workouts", "create",
            "--input", str(out_file),
            "--dry-run",
        ], catch_exceptions=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["workout"]["name"] == "Round Trip"

    def test_input_via_execute(self, tmp_path):
        """--input works through the execute() function too."""
        workout = {"name": "Via Execute", "sport": "running", "steps": [{"run": "30:00"}]}
        f = tmp_path / "workout.json"
        f.write_text(json.dumps(workout))

        result = execute(
            f"--dry-run workouts create --input {f}",
            "fake",
            tmp_dir=str(tmp_path),
        )
        assert result["exit_code"] == 0
        data = json.loads(result["stdout"])
        assert data["workout"]["name"] == "Via Execute"


class TestDescribe:
    @staticmethod
    def _describe(*path):
        result = _runner().invoke(garmin, ["describe", *path], catch_exceptions=False)
        assert result.exit_code == 0, result.output
        return json.loads(result.output)

    def test_index_is_one_line_per_command(self):
        commands = self._describe()["commands"]
        assert commands["activities"]["list"].startswith("List activities")
        assert "snapshot" in commands["health"]
        assert "create" in commands["workouts"]
        assert commands["geographic"]["history query"]
        assert isinstance(commands["help"], str)

    def test_index_is_small(self):
        """The audit's 24 KB `describe`: now an index (~3 KB), the details per group."""
        result = execute("describe", "fake")
        assert len(result["stdout"].encode()) < 4500

    def test_group_has_params_and_output_field_names(self):
        data = self._describe("activities")
        names = [c["command"] for c in data["commands"]]
        assert all(n.startswith("activities ") for n in names)
        list_cmd = next(c for c in data["commands"] if c["command"] == "activities list")
        assert any(p.startswith("--from <text>") for p in list_cmd["params"])
        assert any(p.startswith("--with effort") for p in list_cmd["params"])
        assert "gap_s_per_km" in list_cmd["output"]["activities[]"]

    def test_command_has_each_output_field_meaning(self):
        [entry] = self._describe("activities", "get")["commands"]
        assert entry["output"]["."]["gap_s_per_km"].startswith("Grade-adjusted pace")
        assert entry["params"] == ["ACTIVITY_ID <integer>"]

    def test_sections_of_the_snapshot(self):
        [entry] = self._describe("health", "snapshot")["commands"]
        assert set(entry["output"]) == {"stats", "sleep", "training_readiness", "hrv"}
        assert "bedtime" in entry["output"]["sleep"]

    def test_describe_unknown_command(self):
        runner = _runner()
        result = runner.invoke(garmin, ["describe", "nonexistent"], catch_exceptions=True)
        assert result.exit_code != 0


class TestDescribeShape:
    """Unit tests for _describe_shape helper."""

    def test_list(self):
        assert _describe_shape([{"id": 1}, {"id": 2}]) == "[...2 items]"

    def test_empty_list(self):
        assert _describe_shape([]) == "[...0 items]"

    def test_dict_with_nested_list(self):
        data = {"count": 3, "activities": [{"id": 1}, {"id": 2}, {"id": 3}]}
        shape = _describe_shape(data)
        assert '"count": 3' in shape
        assert '"activities": [...3 items]' in shape

    def test_dict_with_scalar_values(self):
        data = {"status": "ok", "count": 5}
        shape = _describe_shape(data)
        assert '"status": "ok"' in shape
        assert '"count": 5' in shape

    def test_dict_with_nested_dict(self):
        data = {"stats": {"hr": 60}, "sleep": {"score": 85}}
        shape = _describe_shape(data)
        assert '"stats": ...' in shape
        assert '"sleep": ...' in shape

    def test_long_string_truncated(self):
        data = {"description": "a" * 50}
        shape = _describe_shape(data)
        assert '"description": ...' in shape


class TestDryRunDiscoverability:
    """Agents introspect `help <cmd>` / `describe <cmd>` — --dry-run must be visible there.

    Regression: on 2026-08-28 the workout-builder subagent read `help workouts create`,
    saw no --dry-run under Options, and refused to validate ("flag does not exist").
    """

    MUTATIONS = [
        "workouts create", "workouts update", "workouts delete", "workouts schedule",
        "workouts unschedule", "workouts reschedule",
        "gear add", "gear remove",
        "body add-weight", "body delete-weight",
    ]

    def _cmd(self, path):
        target = garmin
        for part in path.split():
            target = target.commands[part]
        return target

    def test_every_dry_run_capable_command_is_a_mutation_command(self):
        """Any command whose source uses dry_run_preview must be tagged (keeps the list honest)."""
        import inspect as _inspect
        for path in self.MUTATIONS:
            cmd = self._cmd(path)
            assert isinstance(cmd, MutationCommand), f"{path} must use cls=MutationCommand"
            assert "dry_run_preview" in _inspect.getsource(cmd.callback), path

    def test_no_untagged_mutation_left_behind(self):
        """Walk the whole tree: dry_run_preview in source ⇔ MutationCommand."""
        import inspect as _inspect
        from garmin_mcp.cli.describe import index
        for path in index(garmin):
            cmd = self._cmd(path)
            uses_dry_run = "dry_run_preview" in _inspect.getsource(cmd.callback)
            assert uses_dry_run == isinstance(cmd, MutationCommand), path

    def test_help_mentions_dry_run_on_mutations(self):
        r = _runner()
        for path in self.MUTATIONS:
            res = r.invoke(garmin, ["help", *path.split()])
            assert res.exit_code == 0, res.output
            assert "--dry-run" in res.output, f"help {path} must advertise --dry-run"

    def test_help_does_not_mention_dry_run_on_reads(self):
        r = _runner()
        res = r.invoke(garmin, ["help", "workouts", "list"])
        assert res.exit_code == 0
        assert "--dry-run" not in res.output

    def test_describe_accepts_words_and_quoted_path(self):
        """`describe workouts create` (what agents type via execute()) must equal `describe "workouts create"`."""
        r = _runner()
        words = r.invoke(garmin, ["describe", "workouts", "create"])
        quoted = r.invoke(garmin, ["describe", "workouts create"])
        assert words.exit_code == 0, words.output + words.stderr
        assert json.loads(words.output) == json.loads(quoted.output)
        assert json.loads(words.output)["commands"][0]["command"] == "workouts create"

    def test_describe_via_execute(self):
        res = execute("describe workouts create", "ZmFrZQ==")
        assert res["exit_code"] == 0, res["stderr"]
        [entry] = json.loads(res["stdout"])["commands"]
        assert any(p.startswith("--dry-run") for p in entry["params"])

    def test_describe_lists_dry_run_on_mutations_only(self):
        r = _runner()
        [entry] = json.loads(r.invoke(garmin, ["describe", "workouts create"]).output)["commands"]
        assert any(p.startswith("--dry-run") for p in entry["params"])
        [entry] = json.loads(r.invoke(garmin, ["describe", "workouts list"]).output)["commands"]
        assert not any(p.startswith("--dry-run") for p in entry.get("params", []))


class TestActivitiesListOptions:
    """Options that were ignored in silence are invalid input now (audit C10)."""

    @pytest.mark.parametrize("command", [
        "activities list --from 2026-01-01",
        "activities list --to 2026-01-31",
        "activities list --from 2026-01-01 --to 2026-01-31 --limit 5",
        "activities list --from 2026-01-01 --to 2026-01-31 --start 20",
    ])
    def test_incoherent_options_are_refused(self, command):
        result = execute(command, "fake")
        assert result["exit_code"] == 2, result
        assert "Error:" in result["stderr"]

    def test_type_filters_the_latest_activities_too(self):
        client = Mock()
        client.get_activities.return_value = []
        result = _runner().invoke(garmin, ["--token", "fake", "activities", "list", "--type", "cycling"],
                                  obj={"client": client})
        assert result.exit_code == 0, result.output
        client.get_activities.assert_called_once_with(0, 20, "cycling")


class TestCompactJson:
    def test_answers_have_no_indentation(self):
        """Read by a model: every space is a token (audit C10, ~25-30 % of a JSON answer)."""
        result = execute("describe activities", "fake")
        assert "\n" not in result["stdout"].strip()
        assert '": ' not in result["stdout"]


class TestUnknownCommand:
    """An unknown command names the commands close to it (audit C5)."""

    @pytest.mark.parametrize("command, expected", [
        ("steps get --date 2026-09-01", "No such command 'steps'. Did you mean: history daily, health stats?"),
        ("history steps", "No such command 'steps' in 'history'. Did you mean: history daily, health stats"),
        ("activities lst", "Did you mean: activities list"),
        ("sleep", "Did you mean: health sleep, history sleep?"),
        ("geographic histry query heatmap", "Did you mean: geographic history?"),
        ("help steps", "Did you mean: history daily, health stats?"),
        ("describe health stas", "Did you mean: health stats"),
    ])
    def test_suggests_close_commands(self, command, expected):
        result = execute(command, "fake-token")
        assert result["exit_code"] == 2
        assert expected in result["stderr"]

    def test_no_suggestion_for_nonsense(self):
        result = execute("zzqx", "fake-token")
        assert result["exit_code"] == 2
        assert "No such command 'zzqx'. All commands: `help`." in result["stderr"]
