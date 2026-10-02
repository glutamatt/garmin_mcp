"""Unit tests for garmin_mcp.api.workouts — payload, preview, curation, CRUD."""

import pytest
from unittest.mock import Mock
from garmin_mcp.api import workouts as api
from garmin_mcp.api.contract import GarminWriteError, InvalidInput, NotFound


@pytest.fixture
def client():
    return Mock()


EASY = {"name": "Test", "sport": "running", "steps": [{"warmup": "lap"}]}


# ── Readable format → payload ─────────────────────────────────────────────────


class TestPrepareWorkout:
    def test_payload_of_a_readable_workout(self):
        native = api.prepare_workout({"name": "Test", "sport": "running", "steps": [
            {"warmup": "10:00"}, {"run": "5km", "pace": "5:00"}]})
        assert native["workoutName"] == "Test"
        assert native["estimatedDurationInSecs"] == 600 + 1500
        assert "avgTrainingSpeed" not in native

    def test_invalid_workout_is_invalid_input(self):
        with pytest.raises(InvalidInput):
            api.prepare_workout({"workoutName": "Test", "steps": []})


class TestPreviewWorkout:
    def test_steps_read_back_with_estimates(self):
        preview = api.preview_workout({"name": "Test", "sport": "running", "steps": [
            {"run": "1km", "pace": "5:30-5:00"}]})
        assert preview == {
            "workout": {"name": "Test", "sport": "running", "steps": [{"run": "1km", "pace": "5:00-5:30"}]},
            "estimated_duration_s": 315,
            "estimated_distance_m": 1000,
        }

    def test_missing_estimate_says_why(self):
        preview = api.preview_workout({"name": "Test", "sport": "running", "steps": [
            {"warmup": "lap"}, {"run": "30:00"}]})
        assert "estimated_duration_s" not in preview
        assert preview["not_estimated"] == {
            "duration_s": ["steps[0] (lap)"],
            "distance_m": ["steps[0] (lap)", "steps[1] (no pace)"],
        }


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

    def test_estimates_and_update_date(self, client):
        """Garmin's keys: `estimatedDurationInSecs`, `estimatedDistanceInMeters`; the list says `updateDate`."""
        client.get_workouts.return_value = [
            {"workoutId": 1, "estimatedDurationInSecs": 315, "estimatedDistanceInMeters": 1000.0,
             "updateDate": "2026-10-02T10:36:14.0"},
            {"workoutId": 2, "estimatedDurationInSecs": 0, "estimatedDistanceInMeters": 0.0},
        ]
        first, second = api.get_workouts(client)["workouts"]
        assert first["estimated_duration_s"] == 315
        assert first["estimated_distance_m"] == 1000
        assert first["updated_date"] == "2026-10-02T10:36:14.0"
        # 0 is Garmin's "no estimate".
        assert "estimated_duration_s" not in second
        assert "estimated_distance_m" not in second


RAW_WORKOUT = {
    "workoutId": 7, "workoutName": "Easy", "description": "Flat", "createdDate": "2026-10-01T14:23:37.0",
    "updatedDate": "2026-10-01T14:23:37.0", "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
    "estimatedDurationInSecs": 0, "estimatedDistanceInMeters": 0.0, "avgTrainingSpeed": 2.5,
    "workoutSegments": [{"segmentOrder": 1, "workoutSteps": [
        {"type": "ExecutableStepDTO", "stepOrder": 1,
         "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
         "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 2400.0,
         "targetType": {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone"},
         "targetValueOne": 3.0303, "targetValueTwo": 3.3333, "description": "HR < 160"},
    ]}],
}


class TestGetWorkoutById:
    def test_no_workout_is_not_found(self, client):
        client.get_workout_by_id.return_value = None
        with pytest.raises(NotFound, match="123"):
            api.get_workout_by_id(client, 123)

    def test_readable_format(self, client):
        client.get_workout_by_id.return_value = RAW_WORKOUT
        result = api.get_workout_by_id(client, 7)
        assert result["id"] == 7
        assert result["name"] == "Easy"
        assert result["sport"] == "running"
        assert result["description"] == "Flat"
        assert result["steps"] == [{"run": "40:00", "pace": "5:00-5:30", "note": "HR < 160"}]
        assert result["created_date"] == "2026-10-01T14:23:37.0"
        # Our own upload default, not Garmin's: never shown.
        assert "avg_training_speed_mps" not in result
        assert "estimated_duration_s" not in result
        assert result["warnings"][0].startswith("steps[0].pace: Garmin has the slower bound first")

    def test_raw_is_garmin_json_unchanged(self, client):
        client.get_workout_by_id.return_value = RAW_WORKOUT
        assert api.get_workout_by_id(client, 7, raw=True) is RAW_WORKOUT

    def test_get_output_goes_back_into_create(self, client):
        """get → create as is: the read-only keys are ignored, the pace order is fixed."""
        client.get_workout_by_id.return_value = RAW_WORKOUT
        native = api.prepare_workout(api.get_workout_by_id(client, 7))
        (step,) = native["workoutSegments"][0]["workoutSteps"]
        assert step["targetValueOne"] == pytest.approx(3.3333, abs=1e-4)
        assert step["targetValueTwo"] == pytest.approx(3.0303, abs=1e-4)
        assert native["estimatedDurationInSecs"] == 2400


class TestGetScheduledWorkouts:
    def test_estimates(self, client):
        client.get_scheduled_workouts_for_range.return_value = [
            {"scheduledWorkoutId": 9, "workoutId": 7, "scheduleDate": "2026-10-03",
             "estimatedDurationInSecs": 2400, "estimatedDistanceInMeters": 0.0}]
        (item,) = api.get_scheduled_workouts(client, "2026-10-01", "2026-10-31")["scheduled_workouts"]
        assert item["estimated_duration_s"] == 2400
        assert "estimated_distance_m" not in item

    def test_empty_range_is_an_empty_list(self, client):
        client.get_scheduled_workouts_for_range.return_value = []
        assert api.get_scheduled_workouts(client, "2024-01-01", "2024-01-31") == {
            "count": 0,
            "date_range": {"start": "2024-01-01", "end": "2024-01-31"},
            "scheduled_workouts": [],
        }


class TestCreateWorkout:
    def test_uploads_the_payload(self, client):
        client.upload_workout.return_value = {"workoutId": 42}
        api.create_workout(client, EASY)
        (payload,) = client.upload_workout.call_args.args
        assert payload == api.prepare_workout(EASY)

    def test_invalid_workout_uploads_nothing(self, client):
        with pytest.raises(InvalidInput):
            api.create_workout(client, {"name": "Test", "sport": "running", "steps": [{"intervall": "5:00"}]})
        client.upload_workout.assert_not_called()

    def test_create_only(self, client):
        client.upload_workout.return_value = {"workoutId": 42, "workoutName": "Test"}

        result = api.create_workout(client, EASY)

        assert result["status"] == "created"
        assert result["workout_id"] == 42
        client.upload_workout.assert_called_once()
        client.schedule_workout.assert_not_called()

    def test_create_and_schedule(self, client):
        client.upload_workout.return_value = {"workoutId": 42, "workoutName": "Test"}
        client.schedule_workout.return_value = {"workoutScheduleId": 99}

        result = api.create_workout(client, EASY, date="2024-01-20")

        assert result["status"] == "planned"
        assert result["workout_id"] == 42
        assert result["schedule_id"] == 99
        assert result["scheduled_date"] == "2024-01-20"

    def test_schedule_failure_fails_and_gives_the_workout_id(self, client):
        """The workout exists: the error says so, to schedule it, not create it twice."""
        client.upload_workout.return_value = {"workoutId": 42, "workoutName": "Test"}
        client.schedule_workout.side_effect = Exception("Scheduling failed")

        with pytest.raises(GarminWriteError) as raised:
            api.create_workout(client, EASY, date="2024-01-20")

        message = str(raised.value)
        assert "Workout 42 was created" in message
        assert "workouts schedule 42 --date 2024-01-20" in message

    def test_no_workout_id_fails(self, client):
        client.upload_workout.return_value = {}
        with pytest.raises(GarminWriteError, match="no workout ID"):
            api.create_workout(client, EASY)


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
            api.update_workout(client, 42, EASY)
        client.garth.put.assert_not_called()

    def test_invalid_workout_calls_nothing(self, client):
        with pytest.raises(InvalidInput):
            api.update_workout(client, 42, {"workoutName": "Test", "steps": []})
        client.get_workout_by_id.assert_not_called()
        client.garth.put.assert_not_called()

    def test_puts_the_payload_with_its_id(self, client):
        client.get_workout_by_id.return_value = RAW_WORKOUT
        client.garth.put.return_value.text = ""
        result = api.update_workout(client, 7, EASY)
        url = client.garth.put.call_args.args[1]
        payload = client.garth.put.call_args.kwargs["json"]
        assert url == "/workout-service/workout/7"
        assert payload["workoutId"] == 7
        assert payload["workoutName"] == "Test"
        assert result == {"status": "updated", "workout_id": 7, "name": "Test"}


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
