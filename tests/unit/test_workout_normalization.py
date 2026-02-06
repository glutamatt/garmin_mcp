"""
Unit tests for workout normalization functions and Pydantic models.

Tests that AI-generated simplified workout structures are correctly
transformed into Garmin Connect API-compatible format.
"""
import pytest

from garmin_mcp.workouts import (
    WorkoutData,
    SportType,
    StepType,
    EndCondition,
    TargetType,
    WorkoutStep,
    RepeatGroup,
    WorkoutSegment,
    _preprocess_workout_input,
    _normalize_workout_structure,
    _normalize_executable_step,
    _normalize_repeat_group,
    _normalize_steps,
    _restructure_flat_repeats,
)


# =============================================================================
# Pydantic Model Tests
# =============================================================================


class TestPydanticModels:
    """Test Pydantic model validation and serialization."""

    def test_sport_type_valid(self):
        st = SportType(sportTypeId=1, sportTypeKey="running")
        assert st.sportTypeId == 1
        assert st.sportTypeKey == "running"

    def test_workout_step_minimal(self):
        step = WorkoutStep(
            stepOrder=1,
            stepType=StepType(stepTypeId=1, stepTypeKey="warmup"),
            endCondition=EndCondition(conditionTypeId=1, conditionTypeKey="lap.button"),
        )
        assert step.stepOrder == 1
        assert step.targetType is None
        assert step.endConditionValue is None

    def test_workout_step_with_target(self):
        step = WorkoutStep(
            stepOrder=1,
            stepType=StepType(stepTypeId=3, stepTypeKey="interval"),
            endCondition=EndCondition(conditionTypeId=2, conditionTypeKey="time"),
            endConditionValue=300,
            targetType=TargetType(
                workoutTargetTypeId=6, workoutTargetTypeKey="pace.zone"
            ),
            targetValueOne=3.33,
            targetValueTwo=2.78,
        )
        assert step.endConditionValue == 300
        assert step.targetValueOne == 3.33

    def test_repeat_group_default_step_type(self):
        rg = RepeatGroup(
            stepOrder=2,
            numberOfIterations=4,
            workoutSteps=[
                WorkoutStep(
                    stepOrder=1,
                    stepType=StepType(stepTypeId=3, stepTypeKey="interval"),
                    endCondition=EndCondition(conditionTypeId=3, conditionTypeKey="distance"),
                    endConditionValue=400,
                ),
            ],
        )
        assert rg.stepType.stepTypeId == 6
        assert rg.stepType.stepTypeKey == "repeat"

    def test_workout_data_full(self):
        wd = WorkoutData(
            workoutName="Test Workout",
            description="A test",
            sportType=SportType(sportTypeId=1, sportTypeKey="running"),
            workoutSegments=[
                WorkoutSegment(
                    segmentOrder=1,
                    sportType=SportType(sportTypeId=1, sportTypeKey="running"),
                    workoutSteps=[
                        WorkoutStep(
                            stepOrder=1,
                            stepType=StepType(stepTypeId=1, stepTypeKey="warmup"),
                            endCondition=EndCondition(
                                conditionTypeId=2, conditionTypeKey="time"
                            ),
                            endConditionValue=600,
                        ),
                    ],
                )
            ],
        )
        d = wd.model_dump(exclude_none=True)
        assert d["workoutName"] == "Test Workout"
        assert len(d["workoutSegments"]) == 1
        assert d["workoutSegments"][0]["workoutSteps"][0]["endConditionValue"] == 600

    def test_workout_data_missing_required_field_raises(self):
        with pytest.raises(Exception):
            WorkoutData(
                workoutName="Bad",
                sportType=SportType(sportTypeId=1, sportTypeKey="running"),
                # missing workoutSegments
            )


# =============================================================================
# _normalize_executable_step Tests
# =============================================================================


class TestNormalizeExecutableStep:
    """Test normalization of individual executable workout steps."""

    def test_sets_executable_step_dto_type(self):
        step = {
            "stepOrder": 1,
            "stepType": {"stepTypeId": 1, "stepTypeKey": "warmup"},
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
        }
        result = _normalize_executable_step(step)
        assert result["type"] == "ExecutableStepDTO"

    def test_assigns_step_id(self):
        step = {
            "stepOrder": 1,
            "stepType": {"stepTypeId": 1, "stepTypeKey": "warmup"},
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
        }
        result = _normalize_executable_step(step, [5])
        assert result["stepId"] == 5

    def test_preserves_existing_step_id(self):
        step = {
            "stepId": 42,
            "stepOrder": 1,
            "stepType": {"stepTypeId": 1, "stepTypeKey": "warmup"},
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
        }
        result = _normalize_executable_step(step, [1])
        assert result["stepId"] == 42

    def test_fixes_wrong_step_type_id(self):
        """AI might send stepTypeId=1 for 'interval' - should be corrected to 3"""
        step = {
            "stepOrder": 1,
            "stepType": {"stepTypeId": 1, "stepTypeKey": "interval"},
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
        }
        result = _normalize_executable_step(step)
        assert result["stepType"]["stepTypeId"] == 3

    def test_adds_display_order_to_step_type(self):
        step = {
            "stepOrder": 1,
            "stepType": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
            "endCondition": {"conditionTypeId": 1, "conditionTypeKey": "lap.button"},
        }
        result = _normalize_executable_step(step)
        assert result["stepType"]["displayOrder"] == 2

    def test_adds_display_order_to_end_condition(self):
        step = {
            "stepOrder": 1,
            "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
            "endCondition": {"conditionTypeId": 3, "conditionTypeKey": "distance"},
        }
        result = _normalize_executable_step(step)
        assert result["endCondition"]["displayOrder"] == 3
        assert result["endCondition"]["displayable"] is True

    def test_adds_display_order_to_target_type(self):
        step = {
            "stepOrder": 1,
            "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
            "targetType": {
                "workoutTargetTypeId": 6,
                "workoutTargetTypeKey": "pace.zone",
            },
        }
        result = _normalize_executable_step(step)
        assert result["targetType"]["displayOrder"] == 6

    def test_adds_stroke_and_equipment_type(self):
        step = {
            "stepOrder": 1,
            "stepType": {"stepTypeId": 1, "stepTypeKey": "warmup"},
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
        }
        result = _normalize_executable_step(step)
        assert "strokeType" in result
        assert "equipmentType" in result
        assert result["equipmentType"]["equipmentTypeId"] is None

    def test_hr_zone_number_extraction(self):
        """When targetValueOne == targetValueTwo for HR zone, extract zoneNumber"""
        step = {
            "stepOrder": 1,
            "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
            "targetType": {
                "workoutTargetTypeId": 4,
                "workoutTargetTypeKey": "heart.rate.zone",
            },
            "targetValueOne": 3,
            "targetValueTwo": 3,
        }
        result = _normalize_executable_step(step)
        assert result["zoneNumber"] == 3
        assert result["targetValueOne"] is None
        assert result["targetValueTwo"] is None

    def test_power_zone_number_extraction(self):
        """When targetValueOne == targetValueTwo for power zone, extract zoneNumber"""
        step = {
            "stepOrder": 1,
            "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
            "targetType": {
                "workoutTargetTypeId": 5,
                "workoutTargetTypeKey": "power.zone",
            },
            "targetValueOne": 5,
            "targetValueTwo": 5,
        }
        result = _normalize_executable_step(step)
        assert result["zoneNumber"] == 5

    def test_does_not_mutate_input(self):
        step = {
            "stepOrder": 1,
            "stepType": {"stepTypeId": 1, "stepTypeKey": "warmup"},
            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
        }
        _normalize_executable_step(step)
        assert "type" not in step  # original not mutated


# =============================================================================
# _normalize_repeat_group Tests
# =============================================================================


class TestNormalizeRepeatGroup:
    """Test normalization of repeat group steps."""

    def test_sets_repeat_group_dto_type(self):
        step = {
            "stepOrder": 2,
            "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat"},
            "numberOfIterations": 4,
            "workoutSteps": [
                {
                    "stepOrder": 1,
                    "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
                    "endCondition": {"conditionTypeId": 3, "conditionTypeKey": "distance"},
                    "endConditionValue": 400,
                },
            ],
        }
        result = _normalize_repeat_group(step)
        assert result["type"] == "RepeatGroupDTO"

    def test_adds_iterations_end_condition(self):
        step = {
            "stepOrder": 2,
            "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat"},
            "numberOfIterations": 6,
            "workoutSteps": [],
        }
        result = _normalize_repeat_group(step)
        assert result["endCondition"]["conditionTypeKey"] == "iterations"
        assert result["endCondition"]["conditionTypeId"] == 7
        assert result["endConditionValue"] == 6.0

    def test_sets_skip_last_rest_and_smart_repeat(self):
        step = {
            "stepOrder": 2,
            "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat"},
            "numberOfIterations": 3,
            "workoutSteps": [],
        }
        result = _normalize_repeat_group(step)
        assert result["skipLastRestStep"] is True
        assert result["smartRepeat"] is False

    def test_normalizes_inner_steps_recursively(self):
        step = {
            "stepOrder": 2,
            "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat"},
            "numberOfIterations": 3,
            "workoutSteps": [
                {
                    "stepOrder": 1,
                    "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
                    "endCondition": {"conditionTypeId": 3, "conditionTypeKey": "distance"},
                    "endConditionValue": 400,
                },
            ],
        }
        result = _normalize_repeat_group(step)
        inner = result["workoutSteps"][0]
        assert inner["type"] == "ExecutableStepDTO"
        assert "strokeType" in inner


# =============================================================================
# _restructure_flat_repeats Tests
# =============================================================================


class TestRestructureFlatRepeats:
    """Test conversion from flat childStepId chains to nested workoutSteps."""

    def test_noop_when_already_nested(self):
        steps = [
            {
                "stepId": 1,
                "stepType": {"stepTypeKey": "repeat"},
                "numberOfIterations": 3,
                "workoutSteps": [{"stepId": 2}],
            }
        ]
        result = _restructure_flat_repeats(steps)
        assert len(result) == 1
        assert result[0]["workoutSteps"] == [{"stepId": 2}]

    def test_restructures_flat_child_ids(self):
        """Garmin API sometimes returns flat steps with childStepId references"""
        steps = [
            {
                "stepId": 1,
                "stepType": {"stepTypeKey": "repeat"},
                "numberOfIterations": 2,
                "childStepId": 2,
            },
            {
                "stepId": 2,
                "stepType": {"stepTypeKey": "interval"},
                "childStepId": 3,
            },
            {
                "stepId": 3,
                "stepType": {"stepTypeKey": "recovery"},
            },
        ]
        result = _restructure_flat_repeats(steps)
        assert len(result) == 1
        assert len(result[0]["workoutSteps"]) == 2
        assert result[0]["workoutSteps"][0]["stepId"] == 2
        assert result[0]["workoutSteps"][1]["stepId"] == 3


# =============================================================================
# _normalize_workout_structure Tests (top-level)
# =============================================================================


class TestNormalizeWorkoutStructure:
    """Test the top-level normalization function."""

    def test_adds_top_level_defaults(self):
        data = {
            "workoutName": "Test",
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSegments": [],
        }
        result = _normalize_workout_structure(data)
        assert result["avgTrainingSpeed"] == 2.5
        assert result["estimatedDurationInSecs"] == 0
        assert result["estimatedDistanceInMeters"] == 0.0
        assert result["estimateType"] is None

    def test_adds_is_wheelchair_for_running(self):
        data = {
            "workoutName": "Test",
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSegments": [],
        }
        result = _normalize_workout_structure(data)
        assert result["isWheelchair"] is False

    def test_no_is_wheelchair_for_cycling(self):
        data = {
            "workoutName": "Test",
            "sportType": {"sportTypeId": 2, "sportTypeKey": "cycling"},
            "workoutSegments": [],
        }
        result = _normalize_workout_structure(data)
        assert "isWheelchair" not in result

    def test_adds_display_order_to_sport_types(self):
        data = {
            "workoutName": "Test",
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSegments": [
                {
                    "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
                    "workoutSteps": [],
                }
            ],
        }
        result = _normalize_workout_structure(data)
        assert result["sportType"]["displayOrder"] == 1
        assert result["workoutSegments"][0]["sportType"]["displayOrder"] == 1

    def test_preserves_existing_values(self):
        data = {
            "workoutName": "Test",
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "avgTrainingSpeed": 4.0,
            "workoutSegments": [],
        }
        result = _normalize_workout_structure(data)
        assert result["avgTrainingSpeed"] == 4.0  # not overwritten

    def test_does_not_mutate_input(self):
        data = {
            "workoutName": "Test",
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSegments": [],
        }
        _normalize_workout_structure(data)
        assert "avgTrainingSpeed" not in data

    def test_full_normalization_pipeline(self):
        """End-to-end: Pydantic model -> dict -> normalize -> Garmin-ready structure"""
        wd = WorkoutData(
            workoutName="Tempo Run",
            sportType=SportType(sportTypeId=1, sportTypeKey="running"),
            workoutSegments=[
                WorkoutSegment(
                    segmentOrder=1,
                    sportType=SportType(sportTypeId=1, sportTypeKey="running"),
                    workoutSteps=[
                        WorkoutStep(
                            stepOrder=1,
                            stepType=StepType(stepTypeId=1, stepTypeKey="warmup"),
                            endCondition=EndCondition(
                                conditionTypeId=2, conditionTypeKey="time"
                            ),
                            endConditionValue=600,
                        ),
                        WorkoutStep(
                            stepOrder=2,
                            stepType=StepType(stepTypeId=3, stepTypeKey="interval"),
                            endCondition=EndCondition(
                                conditionTypeId=2, conditionTypeKey="time"
                            ),
                            endConditionValue=1200,
                            targetType=TargetType(
                                workoutTargetTypeId=6,
                                workoutTargetTypeKey="pace.zone",
                            ),
                            targetValueOne=3.33,
                            targetValueTwo=2.78,
                        ),
                        WorkoutStep(
                            stepOrder=3,
                            stepType=StepType(stepTypeId=2, stepTypeKey="cooldown"),
                            endCondition=EndCondition(
                                conditionTypeId=1, conditionTypeKey="lap.button"
                            ),
                        ),
                    ],
                )
            ],
        )

        data = wd.model_dump(exclude_none=True)
        result = _normalize_workout_structure(data)

        # Top-level
        assert result["avgTrainingSpeed"] == 2.5
        assert result["isWheelchair"] is False
        assert result["sportType"]["displayOrder"] == 1

        # Steps
        steps = result["workoutSegments"][0]["workoutSteps"]
        assert len(steps) == 3

        # Warmup step
        assert steps[0]["type"] == "ExecutableStepDTO"
        assert steps[0]["stepType"]["displayOrder"] == 1
        assert steps[0]["endCondition"]["displayOrder"] == 2
        assert steps[0]["endCondition"]["displayable"] is True
        assert "strokeType" in steps[0]
        assert "equipmentType" in steps[0]

        # Interval step with pace target
        assert steps[1]["type"] == "ExecutableStepDTO"
        assert steps[1]["targetType"]["displayOrder"] == 6
        assert steps[1]["targetValueOne"] == 3.33
        assert steps[1]["targetValueTwo"] == 2.78

        # Cooldown step
        assert steps[2]["type"] == "ExecutableStepDTO"
        assert steps[2]["endCondition"]["conditionTypeKey"] == "lap.button"
        assert steps[2]["endCondition"]["displayOrder"] == 1


class TestStepIdAssignment:
    """Test that step IDs are assigned sequentially across all steps."""

    def test_sequential_step_ids(self):
        steps = [
            {
                "stepOrder": 1,
                "stepType": {"stepTypeId": 1, "stepTypeKey": "warmup"},
                "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
            },
            {
                "stepOrder": 2,
                "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
                "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
            },
            {
                "stepOrder": 3,
                "stepType": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
                "endCondition": {"conditionTypeId": 1, "conditionTypeKey": "lap.button"},
            },
        ]
        result = _normalize_steps(steps)
        assert result[0]["stepId"] == 1
        assert result[1]["stepId"] == 2
        assert result[2]["stepId"] == 3

    def test_step_ids_continue_into_repeat_groups(self):
        steps = [
            {
                "stepOrder": 1,
                "stepType": {"stepTypeId": 1, "stepTypeKey": "warmup"},
                "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
            },
            {
                "stepOrder": 2,
                "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat"},
                "numberOfIterations": 3,
                "workoutSteps": [
                    {
                        "stepOrder": 1,
                        "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
                        "endCondition": {"conditionTypeId": 3, "conditionTypeKey": "distance"},
                        "endConditionValue": 400,
                    },
                    {
                        "stepOrder": 2,
                        "stepType": {"stepTypeId": 4, "stepTypeKey": "recovery"},
                        "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
                        "endConditionValue": 90,
                    },
                ],
            },
            {
                "stepOrder": 3,
                "stepType": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
                "endCondition": {"conditionTypeId": 1, "conditionTypeKey": "lap.button"},
            },
        ]
        result = _normalize_steps(steps)
        # warmup=1, repeat_group=2, interval=3, recovery=4, cooldown=5
        assert result[0]["stepId"] == 1
        assert result[1]["stepId"] == 2
        assert result[1]["workoutSteps"][0]["stepId"] == 3
        assert result[1]["workoutSteps"][1]["stepId"] == 4
        assert result[2]["stepId"] == 5


# =============================================================================
# _preprocess_workout_input Tests
# =============================================================================


class TestPreprocessWorkoutInput:
    """Test conversion from simplified AI format to full Garmin format."""

    def test_simplified_sport_string(self):
        """AI sends sport: 'running' instead of sportType: {sportTypeId, sportTypeKey}"""
        data = {
            "workoutName": "Easy Run",
            "sport": "running",
            "steps": [
                {
                    "stepOrder": 1,
                    "stepType": "interval",
                    "endCondition": "time",
                    "endConditionValue": 1800,
                }
            ],
        }
        result = _preprocess_workout_input(data)
        assert result["sportType"] == {"sportTypeId": 1, "sportTypeKey": "running"}
        assert "workoutSegments" in result
        assert len(result["workoutSegments"]) == 1
        step = result["workoutSegments"][0]["workoutSteps"][0]
        assert step["stepType"] == {"stepTypeId": 3, "stepTypeKey": "interval"}
        assert step["endCondition"] == {"conditionTypeId": 2, "conditionTypeKey": "time"}

    def test_real_ai_output_format(self):
        """Exact format sent by Coach Apex that triggered the error."""
        data = {
            "workoutName": "[APEX] Dimanche - Discipline Longue",
            "sport": "running",
            "steps": [
                {
                    "stepOrder": 1,
                    "stepType": "interval",
                    "endCondition": "time",
                    "endConditionValue": 6300,
                    "targetType": "heart.rate.zone",
                    "targetValueHigh": 152,
                    "targetValueLow": 130,
                }
            ],
        }
        result = _preprocess_workout_input(data)

        # Validate via Pydantic
        validated = WorkoutData(**result)
        assert validated.workoutName == "[APEX] Dimanche - Discipline Longue"

        step = result["workoutSegments"][0]["workoutSteps"][0]
        assert step["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
        assert step["targetValueOne"] == 152  # targetValueHigh -> targetValueOne
        assert step["targetValueTwo"] == 130  # targetValueLow -> targetValueTwo

    def test_passthrough_full_format(self):
        """Already-valid full format should pass through unchanged."""
        data = {
            "workoutName": "Test",
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSegments": [
                {
                    "segmentOrder": 1,
                    "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
                    "workoutSteps": [
                        {
                            "stepOrder": 1,
                            "stepType": {"stepTypeId": 1, "stepTypeKey": "warmup"},
                            "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"},
                            "endConditionValue": 600,
                        }
                    ],
                }
            ],
        }
        result = _preprocess_workout_input(data)
        assert result == data  # unchanged

    def test_target_value_mapping(self):
        """targetValueHigh/Low should map to targetValueOne/Two."""
        data = {
            "workoutName": "HR Run",
            "sport": "running",
            "steps": [
                {
                    "stepOrder": 1,
                    "stepType": "interval",
                    "endCondition": "time",
                    "endConditionValue": 300,
                    "targetType": "pace.zone",
                    "targetValueHigh": 3.5,
                    "targetValueLow": 3.0,
                }
            ],
        }
        result = _preprocess_workout_input(data)
        step = result["workoutSegments"][0]["workoutSteps"][0]
        assert step["targetValueOne"] == 3.5
        assert step["targetValueTwo"] == 3.0

    def test_cycling_sport(self):
        data = {
            "workoutName": "Bike",
            "sport": "cycling",
            "steps": [{"stepOrder": 1, "stepType": "warmup", "endCondition": "time", "endConditionValue": 600}],
        }
        result = _preprocess_workout_input(data)
        assert result["sportType"]["sportTypeId"] == 2
        assert result["sportType"]["sportTypeKey"] == "cycling"

    def test_missing_end_condition_defaults_to_lap_button(self):
        data = {
            "workoutName": "Test",
            "sport": "running",
            "steps": [{"stepOrder": 1, "stepType": "cooldown"}],
        }
        result = _preprocess_workout_input(data)
        step = result["workoutSegments"][0]["workoutSteps"][0]
        assert step["endCondition"]["conditionTypeKey"] == "lap.button"

    def test_full_preprocess_normalize_pipeline(self):
        """End-to-end: simplified AI format -> preprocess -> validate -> normalize."""
        data = {
            "workoutName": "Intervals",
            "sport": "running",
            "steps": [
                {"stepOrder": 1, "stepType": "warmup", "endCondition": "time", "endConditionValue": 600},
                {"stepOrder": 2, "stepType": "interval", "endCondition": "distance", "endConditionValue": 1000,
                 "targetType": "pace.zone", "targetValueHigh": 3.5, "targetValueLow": 3.0},
                {"stepOrder": 3, "stepType": "cooldown", "endCondition": "lap.button"},
            ],
        }
        preprocessed = _preprocess_workout_input(data)
        validated = WorkoutData(**preprocessed)
        normalized = _normalize_workout_structure(validated.model_dump(exclude_none=True))

        assert normalized["avgTrainingSpeed"] == 2.5
        assert normalized["isWheelchair"] is False
        steps = normalized["workoutSegments"][0]["workoutSteps"]
        assert steps[0]["type"] == "ExecutableStepDTO"
        assert steps[1]["targetType"]["displayOrder"] == 6
        assert steps[2]["endCondition"]["displayOrder"] == 1
