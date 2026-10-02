"""Unit tests for garmin_mcp.api.workout_format — the readable workout format and Garmin's JSON."""

import pytest

from garmin_mcp.api import workout_format as fmt
from garmin_mcp.api.contract import InvalidInput
from garmin_mcp.api.workouts import WorkoutData


def _workout(*steps, sport="running", **extra):
    return {"name": "Test", "sport": sport, "steps": list(steps), **extra}


def _steps(native: dict) -> list:
    return native["workoutSegments"][0]["workoutSteps"]


def _errors(workout) -> str:
    with pytest.raises(InvalidInput) as raised:
        fmt.to_garmin(workout)
    assert raised.value.exit_code == 2
    return str(raised.value)


# A step as Garmin Connect stores it (shape of a real answer).
def _garmin_step(order, type_key, type_id, condition, value, target=None, one=None, two=None, **extra):
    target = target or {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
    condition_ids = {"lap.button": 1, "time": 2, "distance": 3, "reps": 10}
    return {
        "type": "ExecutableStepDTO", "stepId": 1000 + order, "stepOrder": order, "childStepId": None,
        "stepType": {"stepTypeId": type_id, "stepTypeKey": type_key, "displayOrder": type_id},
        "description": None,
        "endCondition": {"conditionTypeId": condition_ids[condition], "conditionTypeKey": condition,
                         "displayOrder": condition_ids[condition], "displayable": True},
        "endConditionValue": value, "targetType": target, "targetValueOne": one, "targetValueTwo": two,
        "zoneNumber": None, "secondaryTargetType": None, "category": None, "exerciseName": None,
        "strokeType": {"strokeTypeId": 0, "strokeTypeKey": None, "displayOrder": 0},
        "equipmentType": {"equipmentTypeId": 0, "equipmentTypeKey": None, "displayOrder": 0},
        "weightValue": None, **extra,
    }


PACE = {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone", "displayOrder": 6}
HR = {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 4}


def _garmin_workout(*steps, sport=("running", 1)):
    sport_type = {"sportTypeId": sport[1], "sportTypeKey": sport[0], "displayOrder": sport[1]}
    return {"workoutId": 1, "workoutName": "GC", "description": None, "sportType": sport_type,
            "workoutSegments": [{"segmentOrder": 1, "sportType": sport_type, "workoutSteps": list(steps)}]}


# ── Readable → Garmin ────────────────────────────────────────────────────────


class TestToGarmin:
    def test_easy_run(self):
        native = fmt.to_garmin(_workout(
            {"warmup": "5:00"},
            {"run": "40:00", "pace": "5:00-5:30", "note": "HR < 160"},
            {"cooldown": "3:00"},
            description="Easy",
        ))
        assert native["workoutName"] == "Test"
        assert native["description"] == "Easy"
        assert native["sportType"] == {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}
        warmup, run, cooldown = _steps(native)
        assert warmup["stepType"]["stepTypeKey"] == "warmup"
        assert warmup["endCondition"]["conditionTypeKey"] == "time"
        assert warmup["endConditionValue"] == 300.0
        assert warmup["targetType"]["workoutTargetTypeKey"] == "no.target"
        assert run["stepType"] == {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3}
        assert run["endConditionValue"] == 2400.0
        assert run["description"] == "HR < 160"
        assert cooldown["stepType"]["stepTypeKey"] == "cooldown"

    def test_pace_faster_bound_first_whatever_the_order_written(self):
        """Garmin Connect's order: targetValueOne = the faster bound (higher m/s)."""
        for written in ("5:00-5:30", "5:30-5:00", "5:30 - 5:00/km", "5:00/km-5:30/km"):
            (step,) = _steps(fmt.to_garmin(_workout({"run": "1km", "pace": written})))
            assert step["targetType"]["workoutTargetTypeKey"] == "pace.zone"
            assert step["targetValueOne"] == pytest.approx(1000 / 300)  # 5:00/km
            assert step["targetValueTwo"] == pytest.approx(1000 / 330)  # 5:30/km

    def test_one_pace_is_a_range_of_one(self):
        (step,) = _steps(fmt.to_garmin(_workout({"run": "200m", "pace": "4:30"})))
        assert step["targetValueOne"] == step["targetValueTwo"] == pytest.approx(1000 / 270)

    def test_heart_rate_lower_bound_first(self):
        (step,) = _steps(fmt.to_garmin(_workout({"run": "10:00", "hr": "150-140"})))
        assert step["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
        assert (step["targetValueOne"], step["targetValueTwo"]) == (140.0, 150.0)
        assert "zoneNumber" not in step

    def test_heart_rate_zone(self):
        (step,) = _steps(fmt.to_garmin(_workout({"run": "10:00", "hr_zone": 2})))
        assert step["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
        assert step["zoneNumber"] == 2
        assert "targetValueOne" not in step

    def test_cadence(self):
        (step,) = _steps(fmt.to_garmin(_workout({"run": "50:00", "cadence": "85-95"}, sport="cycling")))
        assert step["targetType"]["workoutTargetTypeId"] == 3
        assert (step["targetValueOne"], step["targetValueTwo"]) == (85.0, 95.0)

    def test_distances(self):
        values = [s["endConditionValue"] for s in _steps(fmt.to_garmin(_workout(
            {"run": "1km"}, {"run": "1.5km"}, {"run": "1,5 km"}, {"run": "200m"}, {"run": "400 M"})))]
        assert values == [1000.0, 1500.0, 1500.0, 200.0, 400.0]
        assert all(s["endCondition"]["conditionTypeKey"] == "distance"
                   for s in _steps(fmt.to_garmin(_workout({"run": "1km"}))))

    def test_durations(self):
        values = [s["endConditionValue"] for s in _steps(fmt.to_garmin(_workout(
            {"run": "0:20"}, {"run": "5:00"}, {"run": "90:00"}, {"run": "1:05:30"})))]
        assert values == [20.0, 300.0, 5400.0, 3930.0]

    def test_lap_button(self):
        (step,) = _steps(fmt.to_garmin(_workout({"recover": "lap"})))
        assert step["endCondition"]["conditionTypeKey"] == "lap.button"
        assert step["endCondition"]["conditionTypeId"] == 1
        assert "endConditionValue" not in step

    def test_every_step_kind(self):
        kinds = [s["stepType"]["stepTypeKey"] for s in _steps(fmt.to_garmin(_workout(
            {"warmup": "1:00"}, {"run": "1:00"}, {"recover": "1:00"}, {"rest": "1:00"},
            {"cooldown": "1:00"}, {"other": "1:00"})))]
        assert kinds == ["warmup", "interval", "recovery", "rest", "cooldown", "other"]

    def test_repeat_and_depth_first_order(self):
        """Garmin Connect numbers the steps depth-first: the repeat, its steps, the next one."""
        native = fmt.to_garmin(_workout(
            {"warmup": "10:00"},
            {"repeat": 6, "steps": [{"run": "400m", "pace": "4:00"}, {"recover": "1:30"}]},
            {"cooldown": "5:00"},
        ))
        warmup, repeat, cooldown = _steps(native)
        assert repeat["type"] == "RepeatGroupDTO"
        assert repeat["numberOfIterations"] == 6
        assert repeat["endCondition"]["conditionTypeKey"] == "iterations"
        assert repeat["skipLastRestStep"] is False
        orders = [warmup["stepOrder"], repeat["stepOrder"],
                  *(s["stepOrder"] for s in repeat["workoutSteps"]), cooldown["stepOrder"]]
        assert orders == [1, 2, 3, 4, 5]
        assert [warmup["stepId"], repeat["stepId"], cooldown["stepId"]] == [1, 2, 5]

    def test_skip_last_recover(self):
        (repeat,) = _steps(fmt.to_garmin(_workout(
            {"repeat": 3, "steps": [{"run": "1:00"}, {"recover": "1:00"}], "skip_last_recover": True})))
        assert repeat["skipLastRestStep"] is True

    def test_sports(self):
        assert fmt.to_garmin(_workout({"run": "1:00"}))["isWheelchair"] is False
        cycling = fmt.to_garmin(_workout({"run": "1:00"}, sport="cycling"))
        assert cycling["sportType"] == {"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2}
        assert "isWheelchair" not in cycling

    def test_payload_passes_the_model(self):
        native = fmt.to_garmin(_workout(
            {"warmup": "lap"},
            {"repeat": 4, "steps": [{"run": "1km", "pace": "4:30-4:40"}, {"recover": "2:00", "hr": "120-140"}]},
            {"run": "10:00", "hr_zone": 2, "note": "easy"},
            {"cooldown": "5:00"},
        ))
        WorkoutData.model_validate(native)

    def test_read_only_keys_of_get_are_ignored(self):
        native = fmt.to_garmin(_workout({"run": "1:00"}, id=12, estimated_duration_s=60, estimated_distance_m=0,
                                        created_date="x", updated_date="y", provider="z", warnings=["w"]))
        assert set(native) == {"workoutName", "sportType", "workoutSegments", "isWheelchair",
                               "estimatedDurationInSecs"}

    def test_empty_note_and_description_are_left_out(self):
        native = fmt.to_garmin(_workout({"run": "1:00", "note": " "}, description=""))
        assert "description" not in native
        assert "description" not in _steps(native)[0]


class TestEstimates:
    def test_distance_at_the_middle_of_the_pace_range(self):
        """1km at 5:00-5:30/km = 5:15: the middle of the range, as Garmin Connect estimates."""
        native = fmt.to_garmin(_workout({"run": "1km", "pace": "5:00-5:30"}))
        assert native["estimatedDurationInSecs"] == 315
        assert native["estimatedDistanceInMeters"] == 1000.0

    def test_time_with_pace_gives_a_distance(self):
        native = fmt.to_garmin(_workout({"run": "30:00", "pace": "6:00"}))
        assert native["estimatedDistanceInMeters"] == 5000.0

    def test_repeats_count_every_round(self):
        estimate = fmt.estimate(_steps(fmt.to_garmin(_workout(
            {"warmup": "10:00"},
            {"repeat": 3, "steps": [{"run": "5:00", "hr": "150-165"}, {"recover": "2:00"}]},
            {"cooldown": "10:00"}))))
        assert estimate.duration_s == 600 + 3 * (300 + 120) + 600

    def test_skip_last_recover_leaves_one_recover_out(self):
        estimate = fmt.estimate(_steps(fmt.to_garmin(_workout(
            {"repeat": 6, "steps": [{"run": "200m", "pace": "4:30"}, {"recover": "1:00"}],
             "skip_last_recover": True}))))
        assert estimate.duration_s == 6 * (54 + 60) - 60

    def test_unknown_parts_are_named(self):
        estimate = fmt.estimate(_steps(fmt.to_garmin(_workout(
            {"warmup": "lap"}, {"run": "30:00"}, {"run": "1km", "pace": "5:00"}))))
        assert estimate.duration_s is None
        assert estimate.distance_m is None
        assert estimate.no_duration == ["steps[0] (lap)"]
        assert estimate.no_distance == ["steps[0] (lap)", "steps[1] (no pace)"]

    def test_no_estimate_is_sent_when_a_step_does_not_give_it(self):
        native = fmt.to_garmin(_workout({"warmup": "lap"}, {"run": "30:00"}))
        assert "estimatedDurationInSecs" not in native
        assert "estimatedDistanceInMeters" not in native
        assert "avgTrainingSpeed" not in native


class TestInvalidInput:
    def test_unknown_step_kind_lists_the_valid_ones(self):
        message = _errors(_workout({"intervall": "5:00"}))
        assert "steps[0].intervall: unknown key" in message
        assert "warmup, run, recover, rest, cooldown, other" in message

    def test_no_kind(self):
        assert "steps[0]: no step kind" in _errors(_workout({"pace": "5:00"}))

    def test_two_kinds(self):
        assert "several kinds: warmup, run" in _errors(_workout({"warmup": "5:00", "run": "5:00"}))

    @pytest.mark.parametrize("value", [1800, "1800", "1800000", "5min", "5:7", "", "5:60"])
    def test_end_must_say_its_unit(self, value):
        assert '"m:ss" or "h:mm:ss", a distance like "1km" or "200m", or "lap"' in _errors(_workout({"run": value}))

    def test_duration_guard_catches_milliseconds(self):
        assert "at most 10:00:00" in _errors(_workout({"run": "30000:00"}))

    def test_distance_guard(self):
        assert "at most 500km" in _errors(_workout({"run": "900km"}))
        assert "more than 0" in _errors(_workout({"run": "0m"}))

    @pytest.mark.parametrize("value", [2.47, "2.47", "5:00-5:30-6:00", "6:75"])
    def test_pace_must_be_min_per_km(self, value):
        assert "steps[0].pace" in _errors(_workout({"run": "1km", "pace": value}))

    def test_pace_out_of_range(self):
        assert "is not a running pace" in _errors(_workout({"run": "1km", "pace": "45:00"}))

    def test_pace_is_for_running(self):
        assert "pace is for running" in _errors(_workout({"run": "1:00", "pace": "3:00"}, sport="cycling"))

    def test_one_target_per_step(self):
        assert "one target per step, got pace, hr" in _errors(
            _workout({"run": "1:00", "pace": "5:00", "hr": "140-150"}))

    @pytest.mark.parametrize("value", ["150", 150, "100-300", "abc"])
    def test_heart_rate_range(self, value):
        assert "steps[0].hr" in _errors(_workout({"run": "1:00", "hr": value}))

    @pytest.mark.parametrize("value", [0, 6, "2", True])
    def test_heart_rate_zone(self, value):
        assert "steps[0].hr_zone" in _errors(_workout({"run": "1:00", "hr_zone": value}))

    def test_unknown_sport(self):
        assert "sport: 'runing' unknown; valid: running, cycling" in _errors(_workout({"run": "1:00"}, sport="runing"))

    def test_sport_is_required(self):
        workout = _workout({"run": "1:00"})
        del workout["sport"]
        assert "sport: required" in _errors(workout)

    def test_name_is_required(self):
        assert "name: required" in _errors({"sport": "running", "steps": [{"run": "1:00"}]})

    def test_steps_are_required(self):
        assert "steps: required" in _errors(_workout())

    def test_unknown_top_level_key(self):
        assert "avg_training_speed_mps: unknown key" in _errors(_workout({"run": "1:00"}, avg_training_speed_mps=2.5))

    def test_native_format_is_refused_with_a_pointer(self):
        message = _errors({"workoutName": "Easy", "sportType": {"sportTypeId": 1}, "workoutSegments": []})
        assert "Garmin's native format is not accepted" in message
        assert "workouts get <id>" in message

    def test_native_step_is_refused(self):
        message = _errors(_workout({"stepType": "interval", "endCondition": "time", "endConditionValue": 600}))
        assert "steps[0]: endCondition, endConditionValue, stepType: Garmin's native format" in message

    def test_repeat_errors(self):
        assert "steps[0].repeat: the number of rounds" in _errors(_workout({"repeat": 0, "steps": [{"run": "1:00"}]}))
        assert "steps[0].steps: required" in _errors(_workout({"repeat": 3}))
        assert "cannot hold another repeat" in _errors(
            _workout({"repeat": 2, "steps": [{"repeat": 2, "steps": [{"run": "1:00"}]}]}))
        assert "steps[0].skip_last_recover: true or false" in _errors(
            _workout({"repeat": 2, "steps": [{"run": "1:00"}], "skip_last_recover": "yes"}))
        assert "steps[0].times: unknown key" in _errors(_workout({"repeat": 2, "times": 2, "steps": [{"run": "1:00"}]}))

    def test_errors_in_a_repeat_have_their_path(self):
        assert "steps[1].steps[0].pace" in _errors(
            _workout({"warmup": "1:00"}, {"repeat": 2, "steps": [{"run": "1:00", "pace": "fast"}]}))

    def test_every_error_at_once(self):
        message = _errors({"name": "", "sport": "x", "steps": [{"run": "1"}, {"warmup": "lap", "hr_zone": 9}]})
        assert message.startswith("Invalid workout (4 errors):")

    def test_not_readable_step_is_refused(self):
        message = _errors(_workout({"run": "10 reps", "not_readable": ["ends on 10 reps"]}))
        assert "steps[0]: this step uses what the readable format cannot say (ends on 10 reps)" in message

    def test_not_an_object(self):
        assert "a workout is a JSON object" in _errors(["run"])
        assert "steps[0]: a step is an object" in _errors(_workout("run 5:00"))


# ── Garmin → readable ────────────────────────────────────────────────────────


class TestFromGarmin:
    def test_garmin_connect_pace_step(self):
        """The shape of a step made in Garmin Connect: 1km at 5:00-5:30/km, with a note."""
        raw = _garmin_workout(_garmin_step(1, "interval", 3, "distance", 1000.0, PACE,
                                           3.3333333, 3.0303030, description="NOTE"))
        assert fmt.from_garmin(raw) == {
            "name": "GC", "sport": "running",
            "steps": [{"run": "1km", "pace": "5:00-5:30", "note": "NOTE"}],
        }

    def test_garmin_connect_repeat_with_heart_rate(self):
        raw = _garmin_workout(
            _garmin_step(1, "warmup", 1, "time", 600.0, two=0.0),
            {"type": "RepeatGroupDTO", "stepId": 2, "stepOrder": 2, "childStepId": 1,
             "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
             "numberOfIterations": 3, "endConditionValue": 3.0, "smartRepeat": False, "skipLastRestStep": None,
             "workoutSteps": [_garmin_step(3, "interval", 3, "time", 300.0, HR, 150.0, 165.0),
                              _garmin_step(4, "recovery", 4, "time", 120.0, two=0.0)]},
            _garmin_step(5, "cooldown", 2, "time", 600.0),
            sport=("cycling", 2),
        )
        assert fmt.from_garmin(raw)["steps"] == [
            {"warmup": "10:00"},
            {"repeat": 3, "steps": [{"run": "5:00", "hr": "150-165"}, {"recover": "2:00"}]},
            {"cooldown": "10:00"},
        ]

    def test_reversed_pace_is_shown_in_order_and_flagged(self):
        raw = _garmin_workout(_garmin_step(1, "interval", 3, "time", 2400.0, PACE, 3.0303, 3.3333))
        readable = fmt.from_garmin(raw)
        assert readable["steps"] == [{"run": "40:00", "pace": "5:00-5:30"}]
        (warning,) = readable["warnings"]
        assert warning.startswith("steps[0].pace: Garmin has the slower bound first (5:30 then 5:00)")

    def test_reversed_heart_rate_is_flagged(self):
        raw = _garmin_workout(_garmin_step(1, "interval", 3, "time", 600.0, HR, 150.0, 140.0))
        readable = fmt.from_garmin(raw)
        assert readable["steps"] == [{"run": "10:00", "hr": "140-150"}]
        assert readable["warnings"][0].startswith("steps[0].hr: Garmin has the higher bound first")

    def test_right_order_has_no_warning(self):
        raw = _garmin_workout(_garmin_step(1, "interval", 3, "time", 600.0, PACE, 3.3333, 3.0303))
        assert "warnings" not in fmt.from_garmin(raw)

    def test_heart_rate_zone_lap_and_long_durations(self):
        raw = _garmin_workout(
            _garmin_step(1, "warmup", 1, "lap.button", None),
            _garmin_step(2, "interval", 3, "time", 4500.0, HR, zoneNumber=2),
            _garmin_step(3, "rest", 5, "distance", 1609.0),
        )
        assert fmt.from_garmin(raw)["steps"] == [
            {"warmup": "lap"}, {"run": "1:15:00", "hr_zone": 2}, {"rest": "1.609km"}]

    def test_strength_steps_are_not_readable(self):
        raw = _garmin_workout(
            _garmin_step(1, "interval", 3, "reps", 10.0, category="PUSH_UP", exerciseName="PUSH_UP"),
            sport=("strength_training", 5))
        readable = fmt.from_garmin(raw)
        (step,) = readable["steps"]
        assert step["run"] == "10 reps"
        assert step["not_readable"] == ["ends on 10 reps", "exercise PUSH_UP/PUSH_UP"]
        assert "steps[0]: not readable" in readable["warnings"][0]
        assert "--raw" in readable["warnings"][0]

    def test_unknown_target_is_not_readable(self):
        power = {"workoutTargetTypeId": 2, "workoutTargetTypeKey": "power.zone", "displayOrder": 2}
        readable = fmt.from_garmin(_garmin_workout(_garmin_step(1, "interval", 3, "time", 60.0, power, 200.0, 250.0)))
        assert readable["steps"][0]["not_readable"] == ["target power.zone 200.0-250.0"]


class TestRoundTrip:
    @pytest.mark.parametrize("steps", [
        [{"warmup": "5:00", "note": "easy"}, {"run": "40:00", "pace": "5:00-5:30"}, {"cooldown": "3:00"}],
        [{"warmup": "lap"}, {"repeat": 8, "steps": [{"run": "400m", "pace": "3:50"}, {"recover": "1:30"}],
                             "skip_last_recover": True}, {"cooldown": "1.5km"}],
        [{"run": "1:00:00", "hr": "140-150"}, {"rest": "0:30"}, {"other": "2km", "hr_zone": 3}],
    ])
    def test_readable_garmin_readable(self, steps):
        workout = _workout(*steps, description="d")
        back = fmt.from_garmin(fmt.to_garmin(workout))
        assert back == workout

    def test_cadence_round_trip(self):
        workout = _workout({"run": "50:00", "cadence": "85-95"}, sport="cycling")
        assert fmt.from_garmin(fmt.to_garmin(workout)) == workout


class TestFormatting:
    @pytest.mark.parametrize("seconds, text", [(20, "0:20"), (300, "5:00"), (3599, "59:59"), (3600, "1:00:00")])
    def test_duration(self, seconds, text):
        assert fmt.format_duration(seconds) == text

    @pytest.mark.parametrize("meters, text", [(200, "200m"), (999, "999m"), (1000, "1km"), (1500, "1.5km"),
                                              (21097.5, "21.098km")])
    def test_distance(self, meters, text):
        assert fmt.format_distance(meters) == text

    def test_pace(self):
        assert fmt.format_pace(1000 / 300) == "5:00"
        assert fmt.format_pace(3.0303) == "5:30"
