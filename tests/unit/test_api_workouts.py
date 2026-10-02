"""Unit tests for garmin_mcp.api.workouts — preprocessing, normalization, CRUD."""

import json
import pytest
from unittest.mock import Mock
from garmin_mcp.api import workouts as api
from garmin_mcp.api.contract import GarminWriteError, NotFound


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

    def test_no_data_is_an_empty_list(self, client):
        client.get_workouts.return_value = None
        assert api.get_workouts(client) == {"count": 0, "workouts": []}


class TestGetWorkoutById:
    def test_no_workout_is_not_found(self, client):
        client.get_workout_by_id.return_value = None
        with pytest.raises(NotFound, match="123"):
            api.get_workout_by_id(client, 123)


class TestGetScheduledWorkouts:
    def test_empty_range_is_an_empty_list(self, client):
        client.get_scheduled_workouts_for_range.return_value = []
        assert api.get_scheduled_workouts(client, "2024-01-01", "2024-01-31") == {
            "count": 0,
            "date_range": {"start": "2024-01-01", "end": "2024-01-31"},
            "scheduled_workouts": [],
        }


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

    def test_schedule_failure_fails_and_gives_the_workout_id(self, client):
        """The workout exists: the error says so, to schedule it, not create it twice."""
        client.upload_workout.return_value = {"workoutId": 42, "workoutName": "Test"}
        client.schedule_workout.side_effect = Exception("Scheduling failed")

        with pytest.raises(GarminWriteError) as raised:
            api.create_workout(client, {
                "workoutName": "Test",
                "sport": "running",
                "steps": [{"stepOrder": 1, "stepType": "warmup", "endCondition": "lap.button"}],
            }, date="2024-01-20")

        message = str(raised.value)
        assert "Workout 42 was created" in message
        assert "workouts schedule 42 --date 2024-01-20" in message

    def test_no_workout_id_fails(self, client):
        client.upload_workout.return_value = {}
        with pytest.raises(GarminWriteError, match="no workout ID"):
            api.create_workout(client, {"workoutName": "Test", "steps": []})


class TestDeleteWorkout:
    def test_success(self, client):
        client.get_scheduled_workouts_for_range.return_value = []
        client.delete_workout.return_value = True

        result = api.delete_workout(client, 42)
        assert result["status"] == "deleted"

    def test_with_scheduled_cleanup(self, client):
        client.get_scheduled_workouts_for_range.return_value = [
            {"workoutId": 42, "scheduledWorkoutId": 99, "scheduleDate": "2024-01-20"}
        ]
        client.unschedule_workout.return_value = True
        client.delete_workout.return_value = True

        result = api.delete_workout(client, 42)
        assert result["status"] == "deleted"
        assert result["unscheduled_count"] == 1

    def test_failure(self, client):
        client.get_scheduled_workouts_for_range.return_value = []
        client.delete_workout.return_value = False
        with pytest.raises(GarminWriteError, match="did not delete workout 42"):
            api.delete_workout(client, 42)


class TestUpdateWorkout:
    def test_no_workout_is_not_found(self, client):
        client.get_workout_by_id.return_value = None
        with pytest.raises(NotFound, match="42"):
            api.update_workout(client, 42, {"workoutName": "Test", "steps": []})
        client.garth.put.assert_not_called()


class TestScheduleWorkout:
    def test_success(self, client):
        client.schedule_workout.return_value = {"workoutScheduleId": 99}
        result = api.schedule_workout(client, 42, "2024-01-20")
        assert result["status"] == "scheduled"
        assert result["workout_id"] == 42
        assert result["date"] == "2024-01-20"
        assert result["schedule_id"] == 99
        client.schedule_workout.assert_called_once_with(42, "2024-01-20")

    def test_non_dict_response(self, client):
        client.schedule_workout.return_value = True
        result = api.schedule_workout(client, 42, "2024-01-20")
        assert result["status"] == "scheduled"
        assert "schedule_id" not in result


class TestUnscheduleWorkout:
    def test_success(self, client):
        client.unschedule_workout.return_value = True
        result = api.unschedule_workout(client, 99)
        assert result["status"] == "unscheduled"

    def test_failure(self, client):
        client.unschedule_workout.return_value = False
        with pytest.raises(GarminWriteError, match="did not unschedule 99"):
            api.unschedule_workout(client, 99)


class TestRescheduleWorkout:
    def test_success(self, client):
        client.get_scheduled_workouts_for_range.return_value = [
            {"scheduledWorkoutId": 99, "workoutId": 42, "workoutName": "Tempo Run"}
        ]
        client.unschedule_workout.return_value = True
        client.schedule_workout.return_value = {"workoutScheduleId": 100}

        result = api.reschedule_workout(client, 99, "2024-01-25")
        assert result["status"] == "rescheduled"
        assert result["new_date"] == "2024-01-25"
        assert result["workout_name"] == "Tempo Run"
        assert result["new_schedule_id"] == 100
        client.unschedule_workout.assert_called_once_with(99)
        client.schedule_workout.assert_called_once_with(42, "2024-01-25")

    def test_unknown_schedule_is_not_found(self, client):
        client.get_scheduled_workouts_for_range.return_value = []
        with pytest.raises(NotFound, match="99"):
            api.reschedule_workout(client, 99, "2024-01-25")
        client.unschedule_workout.assert_not_called()

    def test_unschedule_failure_moves_nothing(self, client):
        client.get_scheduled_workouts_for_range.return_value = [
            {"scheduledWorkoutId": 99, "workoutId": 42}
        ]
        client.unschedule_workout.return_value = False
        with pytest.raises(GarminWriteError, match="nothing was moved"):
            api.reschedule_workout(client, 99, "2024-01-25")
        client.schedule_workout.assert_not_called()

    def test_schedule_failure_says_how_to_put_it_back(self, client):
        client.get_scheduled_workouts_for_range.return_value = [
            {"scheduledWorkoutId": 99, "workoutId": 42}
        ]
        client.unschedule_workout.return_value = True
        client.schedule_workout.side_effect = Exception("boom")
        with pytest.raises(GarminWriteError, match="workouts schedule 42 --date 2024-01-25"):
            api.reschedule_workout(client, 99, "2024-01-25")
