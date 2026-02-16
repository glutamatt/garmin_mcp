"""Unit tests for garmin_mcp.api.workouts — preprocessing, normalization, CRUD."""

import json
import pytest
from unittest.mock import Mock
from garmin_mcp.api import workouts as api


@pytest.fixture
def client():
    return Mock()


# ── Preprocessing ─────────────────────────────────────────────────────────────


class TestPreprocessWorkoutInput:
    def test_simplified_format(self):
        data = {
            "workoutName": "Easy 5K",
            "sport": "running",
            "steps": [
                {"stepOrder": 1, "stepType": "warmup", "endCondition": "time", "endConditionValue": 600},
                {"stepOrder": 2, "stepType": "interval", "endCondition": "distance", "endConditionValue": 5000},
                {"stepOrder": 3, "stepType": "cooldown", "endCondition": "time", "endConditionValue": 300},
            ],
        }
        result = api.preprocess_workout_input(data)

        assert result["workoutName"] == "Easy 5K"
        assert result["sportType"]["sportTypeId"] == 1
        assert len(result["workoutSegments"]) == 1
        assert len(result["workoutSegments"][0]["workoutSteps"]) == 3
        step = result["workoutSegments"][0]["workoutSteps"][0]
        assert step["stepType"]["stepTypeKey"] == "warmup"
        assert step["endCondition"]["conditionTypeKey"] == "time"

    def test_already_full_format_passthrough(self):
        data = {
            "workoutName": "Test",
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSegments": [{
                "segmentOrder": 1,
                "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
                "workoutSteps": [{
                    "stepOrder": 1,
                    "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
                    "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
                }],
            }],
        }
        result = api.preprocess_workout_input(data)
        assert result == data  # Should pass through unchanged

    def test_repeat_group(self):
        data = {
            "workoutName": "Intervals",
            "sport": "running",
            "steps": [
                {
                    "stepOrder": 1,
                    "stepType": "repeat",
                    "numberOfIterations": 6,
                    "workoutSteps": [
                        {"stepOrder": 1, "stepType": "interval", "endCondition": "distance", "endConditionValue": 800},
                        {"stepOrder": 2, "stepType": "recovery", "endCondition": "distance", "endConditionValue": 200},
                    ],
                }
            ],
        }
        result = api.preprocess_workout_input(data)
        repeat = result["workoutSegments"][0]["workoutSteps"][0]
        assert repeat["numberOfIterations"] == 6
        assert len(repeat["workoutSteps"]) == 2

    def test_target_value_aliases(self):
        data = {
            "workoutName": "Pace",
            "sport": "running",
            "steps": [
                {
                    "stepOrder": 1,
                    "stepType": "interval",
                    "endCondition": "distance",
                    "endConditionValue": 1000,
                    "targetType": "pace.zone",
                    "targetValueHigh": 4.0,
                    "targetValueLow": 3.5,
                }
            ],
        }
        result = api.preprocess_workout_input(data)
        step = result["workoutSegments"][0]["workoutSteps"][0]
        assert step["targetValueOne"] == 4.0
        assert step["targetValueTwo"] == 3.5


# ── prepare_workout_json ──────────────────────────────────────────────────────


class TestPrepareWorkoutJson:
    def test_returns_valid_json(self):
        data = {
            "workoutName": "Test",
            "sport": "running",
            "steps": [
                {"stepOrder": 1, "stepType": "warmup", "endCondition": "time", "endConditionValue": 600},
            ],
        }
        result = api.prepare_workout_json(data)
        parsed = json.loads(result)
        assert parsed["workoutName"] == "Test"
        assert "workoutSegments" in parsed


# ── CRUD operations ───────────────────────────────────────────────────────────


class TestGetWorkouts:
    def test_returns_curated_list(self, client):
        client.get_workouts.return_value = [
            {"workoutId": 1, "workoutName": "Easy Run", "sportType": {"sportTypeKey": "running"}},
            {"workoutId": 2, "workoutName": "Tempo", "sportType": {"sportTypeKey": "running"}},
        ]
        result = api.get_workouts(client)
        assert result["count"] == 2
        assert result["workouts"][0]["id"] == 1
        assert result["workouts"][0]["sport"] == "running"

    def test_no_data(self, client):
        client.get_workouts.return_value = None
        result = api.get_workouts(client)
        assert "error" in result


class TestCreateWorkout:
    def test_create_only(self, client):
        client.upload_workout.return_value = {"workoutId": 42, "workoutName": "Test"}

        result = api.create_workout(client, {
            "workoutName": "Test",
            "sport": "running",
            "steps": [{"stepOrder": 1, "stepType": "warmup", "endCondition": "lap.button"}],
        })

        assert result["status"] == "created"
        assert result["workout_id"] == 42
        client.upload_workout.assert_called_once()
        client.schedule_workout.assert_not_called()

    def test_create_and_schedule(self, client):
        client.upload_workout.return_value = {"workoutId": 42, "workoutName": "Test"}
        client.schedule_workout.return_value = {"workoutScheduleId": 99}

        result = api.create_workout(client, {
            "workoutName": "Test",
            "sport": "running",
            "steps": [{"stepOrder": 1, "stepType": "warmup", "endCondition": "lap.button"}],
        }, date="2024-01-20")

        assert result["status"] == "planned"
        assert result["workout_id"] == 42
        assert result["schedule_id"] == 99
        assert result["scheduled_date"] == "2024-01-20"

    def test_schedule_failure_doesnt_lose_workout(self, client):
        client.upload_workout.return_value = {"workoutId": 42, "workoutName": "Test"}
        client.schedule_workout.side_effect = Exception("Scheduling failed")

        result = api.create_workout(client, {
            "workoutName": "Test",
            "sport": "running",
            "steps": [{"stepOrder": 1, "stepType": "warmup", "endCondition": "lap.button"}],
        }, date="2024-01-20")

        # Workout was created even though scheduling failed
        assert result["workout_id"] == 42
        assert "schedule_error" in result


class TestDeleteWorkout:
    def test_success(self, client):
        client.get_scheduled_workouts_for_range.return_value = []
        client.delete_workout.return_value = True

        result = api.delete_workout(client, 42)
        assert result["status"] == "deleted"

    def test_with_scheduled_cleanup(self, client):
        client.get_scheduled_workouts_for_range.return_value = [
            {"workout": {"workoutId": 42}, "workoutScheduleId": 99, "date": "2024-01-20"}
        ]
        client.unschedule_workout.return_value = True
        client.delete_workout.return_value = True

        result = api.delete_workout(client, 42)
        assert result["status"] == "deleted"
        assert result["unscheduled_count"] == 1


class TestUnscheduleWorkout:
    def test_success(self, client):
        client.unschedule_workout.return_value = True
        result = api.unschedule_workout(client, 99)
        assert result["status"] == "unscheduled"

    def test_failure(self, client):
        client.unschedule_workout.return_value = False
        result = api.unschedule_workout(client, 99)
        assert result["status"] == "failed"


class TestRescheduleWorkout:
    def test_success(self, client):
        client.reschedule_workout.return_value = {
            "workout": {"workoutName": "Tempo Run"}
        }
        result = api.reschedule_workout(client, 99, "2024-01-25")
        assert result["status"] == "rescheduled"
        assert result["new_date"] == "2024-01-25"
        assert result["workout_name"] == "Tempo Run"
