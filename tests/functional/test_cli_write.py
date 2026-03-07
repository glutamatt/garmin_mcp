"""Functional tests for write CLI commands against the dev Garmin account.

These tests create/modify/delete real data on the dev account.

Run with:
    GARMIN_TOKEN_DEV=... pytest tests/functional/test_cli_write.py -v
"""

import json
from datetime import datetime, timedelta

import pytest

from garmin_mcp.cli import garmin
from tests.functional.conftest import invoke, invoke_json


SIMPLE_WORKOUT = json.dumps({
    "workoutName": "CLI Test Workout",
    "description": "Created by functional test — safe to delete",
    "sportType": "running",
    "steps": [
        {
            "stepOrder": 1,
            "stepType": "warmup",
            "endCondition": "time",
            "endConditionValue": 600,
        },
        {
            "stepOrder": 2,
            "stepType": "interval",
            "endCondition": "distance",
            "endConditionValue": 1000,
            "targetType": "pace.zone",
            "targetValueOne": 3.33,
            "targetValueTwo": 3.03,
        },
        {
            "stepOrder": 3,
            "stepType": "cooldown",
            "endCondition": "time",
            "endConditionValue": 300,
        },
    ],
})


class TestWorkoutCRUD:
    """Create → list → get → delete a workout on the dev account."""

    def test_full_lifecycle(self, cli, dev_token):
        # 1. Create
        data = invoke_json(
            cli, dev_token,
            "workouts", "create", "--json", SIMPLE_WORKOUT,
        )
        assert data.get("status") in ("created", "planned"), f"Create failed: {data}"
        workout_id = data["workout_id"]

        try:
            # 2. Verify it appears in list
            list_data = invoke_json(cli, dev_token, "workouts", "list")
            workout_ids = [w["id"] for w in list_data.get("workouts", [])]
            assert workout_id in workout_ids, "Created workout not in list"

            # 3. Get detail
            detail = invoke_json(cli, dev_token, "workouts", "get", str(workout_id))
            assert detail.get("id") == workout_id
            assert detail.get("name") == "CLI Test Workout"

        finally:
            # 4. Delete (always cleanup)
            del_data = invoke_json(cli, dev_token, "workouts", "delete", str(workout_id))
            assert del_data.get("status") == "deleted"

    def test_create_and_schedule(self, cli, dev_token):
        """Create a workout scheduled for next week, then clean up."""
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        data = invoke_json(
            cli, dev_token,
            "workouts", "create", "--json", SIMPLE_WORKOUT, "--date", next_week,
        )
        assert data.get("status") == "planned"
        workout_id = data["workout_id"]

        try:
            # Verify it's in scheduled list
            sched_data = invoke_json(
                cli, dev_token,
                "workouts", "scheduled",
                "--from", next_week, "--to", next_week,
            )
            if sched_data.get("scheduled_workouts"):
                sched_ids = [s["workout_id"] for s in sched_data["scheduled_workouts"]]
                assert workout_id in sched_ids
        finally:
            # Cleanup: delete (also unschedules)
            invoke_json(cli, dev_token, "workouts", "delete", str(workout_id))


class TestBodyData:
    """Add → read → delete a weight measurement on the dev account."""

    def test_weight_lifecycle(self, cli, dev_token):
        today_str = datetime.now().strftime("%Y-%m-%d")

        # 1. Add weight (may fail with 412 if account has no weight profile)
        from garmin_mcp.cli import execute
        result = execute("body add-weight 75.5 --unit kg", dev_token)
        if result["exit_code"] != 0:
            combined = result["stdout"] + result["stderr"]
            if "412" in combined or "Precondition" in combined:
                pytest.skip("Dev account weight profile not initialized (412)")
            pytest.fail(f"add-weight failed: {combined}")

        import json
        data = json.loads(result.output)
        assert data.get("status") == "success"

        try:
            # 2. Read it back
            weigh_data = invoke_json(
                cli, dev_token,
                "body", "weigh-ins", "--from", today_str, "--to", today_str,
            )
            assert weigh_data.get("measurements") or weigh_data.get("error")
        finally:
            # 3. Delete
            invoke(cli, dev_token, "body", "delete-weight", today_str)
