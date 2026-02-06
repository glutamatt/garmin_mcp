"""
Integration tests for workouts module MCP tools

Tests all workout tools using FastMCP integration with mocked Garmin API responses.
"""
import json

import pytest
from unittest.mock import Mock
from mcp.server.fastmcp import FastMCP

from garmin_mcp import workouts
from tests.fixtures.garmin_responses import (
    MOCK_WORKOUTS,
    MOCK_WORKOUT_DETAILS,
)


def _get_text(result) -> str:
    """Extract text from call_tool result (handles tuple or list return)."""
    # call_tool returns (list[Content], metadata) tuple
    content = result[0] if isinstance(result, tuple) else result
    if isinstance(content, list):
        return content[0].text
    return content.text


# Valid workout data matching WorkoutData Pydantic schema
VALID_WORKOUT_INPUT = {
    "workoutName": "Easy 30min Run",
    "description": "Recovery run",
    "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
    "workoutSegments": [
        {
            "segmentOrder": 1,
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSteps": [
                {
                    "stepOrder": 1,
                    "stepType": {"stepTypeId": 1, "stepTypeKey": "warmup"},
                    "endCondition": {
                        "conditionTypeId": 2,
                        "conditionTypeKey": "time",
                    },
                    "endConditionValue": 600,
                },
                {
                    "stepOrder": 2,
                    "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
                    "endCondition": {
                        "conditionTypeId": 2,
                        "conditionTypeKey": "time",
                    },
                    "endConditionValue": 1200,
                    "targetType": {
                        "workoutTargetTypeId": 6,
                        "workoutTargetTypeKey": "pace.zone",
                    },
                    "targetValueOne": 3.33,
                    "targetValueTwo": 2.78,
                },
                {
                    "stepOrder": 3,
                    "stepType": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
                    "endCondition": {
                        "conditionTypeId": 1,
                        "conditionTypeKey": "lap.button",
                    },
                },
            ],
        }
    ],
}

# Workout with repeat group
VALID_WORKOUT_WITH_REPEATS = {
    "workoutName": "Interval Session",
    "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
    "workoutSegments": [
        {
            "segmentOrder": 1,
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSteps": [
                {
                    "stepOrder": 1,
                    "stepType": {"stepTypeId": 1, "stepTypeKey": "warmup"},
                    "endCondition": {
                        "conditionTypeId": 2,
                        "conditionTypeKey": "time",
                    },
                    "endConditionValue": 600,
                },
                {
                    "stepOrder": 2,
                    "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat"},
                    "numberOfIterations": 5,
                    "workoutSteps": [
                        {
                            "stepOrder": 1,
                            "stepType": {
                                "stepTypeId": 3,
                                "stepTypeKey": "interval",
                            },
                            "endCondition": {
                                "conditionTypeId": 3,
                                "conditionTypeKey": "distance",
                            },
                            "endConditionValue": 400,
                        },
                        {
                            "stepOrder": 2,
                            "stepType": {
                                "stepTypeId": 4,
                                "stepTypeKey": "recovery",
                            },
                            "endCondition": {
                                "conditionTypeId": 2,
                                "conditionTypeKey": "time",
                            },
                            "endConditionValue": 90,
                        },
                    ],
                },
                {
                    "stepOrder": 3,
                    "stepType": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
                    "endCondition": {
                        "conditionTypeId": 1,
                        "conditionTypeKey": "lap.button",
                    },
                },
            ],
        }
    ],
}


@pytest.fixture
def app_with_workouts(mock_garmin_client):
    """Create FastMCP app with workouts tools registered"""
    workouts.configure(mock_garmin_client)
    app = FastMCP("Test Workouts")
    app = workouts.register_tools(app)
    return app


# =========================================================================
# Read-only tool tests
# =========================================================================


@pytest.mark.asyncio
async def test_get_workouts_tool(app_with_workouts, mock_garmin_client):
    """Test get_workouts tool returns all workouts"""
    mock_garmin_client.get_workouts.return_value = MOCK_WORKOUTS

    result = await app_with_workouts.call_tool("get_workouts", {})

    assert result is not None
    mock_garmin_client.get_workouts.assert_called_once()


@pytest.mark.asyncio
async def test_get_workout_by_id_tool(app_with_workouts, mock_garmin_client):
    """Test get_workout_by_id tool returns specific workout"""
    mock_garmin_client.get_workout_by_id.return_value = MOCK_WORKOUT_DETAILS

    workout_id = 123456
    result = await app_with_workouts.call_tool(
        "get_workout_by_id", {"workout_id": workout_id}
    )

    assert result is not None
    mock_garmin_client.get_workout_by_id.assert_called_once_with(workout_id)


@pytest.mark.asyncio
async def test_download_workout_tool(app_with_workouts, mock_garmin_client):
    """Test download_workout tool downloads workout data"""
    mock_garmin_client.download_workout.return_value = b"\x00\x01\x02FIT"

    workout_id = 123456
    result = await app_with_workouts.call_tool(
        "download_workout", {"workout_id": workout_id}
    )

    assert result is not None
    mock_garmin_client.download_workout.assert_called_once_with(workout_id)


@pytest.mark.asyncio
async def test_get_scheduled_workouts_tool(app_with_workouts, mock_garmin_client):
    """Test get_scheduled_workouts tool - uses GraphQL query"""
    graphql_response = {
        "data": {
            "workoutScheduleSummariesScalar": [
                {
                    "workoutId": 123456,
                    "workoutName": "5K Tempo Run",
                    "scheduledDate": "2024-01-15",
                    "completed": False,
                }
            ]
        }
    }
    mock_garmin_client.query_garmin_graphql.return_value = graphql_response

    result = await app_with_workouts.call_tool(
        "get_scheduled_workouts",
        {"start_date": "2024-01-08", "end_date": "2024-01-15"},
    )

    assert result is not None
    mock_garmin_client.query_garmin_graphql.assert_called_once()


@pytest.mark.asyncio
async def test_get_training_plan_workouts_tool(
    app_with_workouts, mock_garmin_client
):
    """Test get_training_plan_workouts tool - uses GraphQL query"""
    graphql_response = {
        "data": {
            "trainingPlanScalar": {
                "trainingPlanWorkoutScheduleDTOS": [
                    {
                        "workoutId": 123456,
                        "workoutName": "Week 1 - Day 1",
                        "planName": "5K Training Plan",
                        "calendarDate": "2024-01-15",
                    }
                ]
            }
        }
    }
    mock_garmin_client.query_garmin_graphql.return_value = graphql_response

    result = await app_with_workouts.call_tool(
        "get_training_plan_workouts", {"calendar_date": "2024-01-15"}
    )

    assert result is not None
    mock_garmin_client.query_garmin_graphql.assert_called_once()


# =========================================================================
# upload_workout tests (now with Pydantic WorkoutData + normalization)
# =========================================================================


@pytest.mark.asyncio
async def test_upload_workout_with_pydantic_validation(
    app_with_workouts, mock_garmin_client
):
    """Test upload_workout validates input via WorkoutData Pydantic model"""
    upload_response = {
        "workoutId": 999,
        "workoutName": "Easy 30min Run",
        "createdDate": "2024-01-15",
    }
    mock_garmin_client.upload_workout.return_value = upload_response

    result = await app_with_workouts.call_tool(
        "upload_workout", {"workout_data": VALID_WORKOUT_INPUT}
    )

    assert result is not None
    parsed = json.loads(_get_text(result))
    assert parsed["status"] == "created"
    assert parsed["workout_id"] == 999
    mock_garmin_client.upload_workout.assert_called_once()


@pytest.mark.asyncio
async def test_upload_workout_normalizes_steps(
    app_with_workouts, mock_garmin_client
):
    """Test that upload_workout normalizes steps with ExecutableStepDTO types"""
    mock_garmin_client.upload_workout.return_value = {"workoutId": 1000}

    await app_with_workouts.call_tool(
        "upload_workout", {"workout_data": VALID_WORKOUT_INPUT}
    )

    # Inspect the JSON string passed to garmin_client.upload_workout
    call_args = mock_garmin_client.upload_workout.call_args
    sent_json = json.loads(call_args[0][0])

    # Check normalization added top-level defaults
    assert sent_json["avgTrainingSpeed"] == 2.5
    assert sent_json["estimatedDurationInSecs"] == 0
    assert sent_json["estimatedDistanceInMeters"] == 0.0
    assert sent_json["isWheelchair"] is False  # running-specific

    # Check step types were set to ExecutableStepDTO
    steps = sent_json["workoutSegments"][0]["workoutSteps"]
    for step in steps:
        assert step["type"] == "ExecutableStepDTO"
        assert "stepId" in step
        assert "displayOrder" in step["stepType"]
        assert "strokeType" in step
        assert "equipmentType" in step

    # Check displayOrder in sportType
    assert sent_json["sportType"]["displayOrder"] == 1
    assert sent_json["workoutSegments"][0]["sportType"]["displayOrder"] == 1


@pytest.mark.asyncio
async def test_upload_workout_normalizes_repeat_groups(
    app_with_workouts, mock_garmin_client
):
    """Test that repeat groups get RepeatGroupDTO type and nested steps normalized"""
    mock_garmin_client.upload_workout.return_value = {"workoutId": 1001}

    await app_with_workouts.call_tool(
        "upload_workout", {"workout_data": VALID_WORKOUT_WITH_REPEATS}
    )

    call_args = mock_garmin_client.upload_workout.call_args
    sent_json = json.loads(call_args[0][0])

    steps = sent_json["workoutSegments"][0]["workoutSteps"]
    # Step 0: warmup (ExecutableStepDTO)
    assert steps[0]["type"] == "ExecutableStepDTO"
    # Step 1: repeat group (RepeatGroupDTO)
    assert steps[1]["type"] == "RepeatGroupDTO"
    assert steps[1]["numberOfIterations"] == 5
    assert steps[1]["endCondition"]["conditionTypeKey"] == "iterations"
    assert steps[1]["endConditionValue"] == 5.0
    assert steps[1]["skipLastRestStep"] is True
    assert steps[1]["smartRepeat"] is False
    # Inner steps should be ExecutableStepDTO
    inner_steps = steps[1]["workoutSteps"]
    assert len(inner_steps) == 2
    for inner in inner_steps:
        assert inner["type"] == "ExecutableStepDTO"
    # Step 2: cooldown (ExecutableStepDTO)
    assert steps[2]["type"] == "ExecutableStepDTO"


@pytest.mark.asyncio
async def test_upload_workout_simplified_ai_format(
    app_with_workouts, mock_garmin_client
):
    """Test upload_workout accepts simplified AI format (sport string, flat steps)"""
    mock_garmin_client.upload_workout.return_value = {"workoutId": 1002}

    simplified_input = {
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

    result = await app_with_workouts.call_tool(
        "upload_workout", {"workout_data": simplified_input}
    )

    # Should succeed - preprocessing converts simplified to full format
    mock_garmin_client.upload_workout.assert_called_once()
    call_args = mock_garmin_client.upload_workout.call_args
    sent_json = json.loads(call_args[0][0])

    # Verify preprocessing + normalization happened
    assert sent_json["sportType"]["sportTypeId"] == 1
    assert sent_json["avgTrainingSpeed"] == 2.5
    step = sent_json["workoutSegments"][0]["workoutSteps"][0]
    assert step["type"] == "ExecutableStepDTO"
    assert step["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"


@pytest.mark.asyncio
async def test_plan_workout_simplified_format(
    app_with_workouts, mock_garmin_client
):
    """Test plan_workout with simplified AI format"""
    mock_garmin_client.upload_workout.return_value = {
        "workoutId": 3000,
        "workoutName": "Easy Run",
    }
    mock_garmin_client.garth = Mock()
    mock_garmin_client.garth.post.return_value = Mock(status_code=200)

    result = await app_with_workouts.call_tool(
        "plan_workout",
        {
            "workout_data": {
                "workoutName": "Easy Run",
                "sport": "running",
                "steps": [
                    {"stepOrder": 1, "stepType": "interval", "endCondition": "time", "endConditionValue": 1800}
                ],
            },
            "date": "2026-02-08",
        },
    )

    parsed = json.loads(_get_text(result))
    assert parsed["status"] == "planned"
    assert parsed["workout_id"] == 3000


@pytest.mark.asyncio
async def test_upload_workout_rejects_completely_empty(
    app_with_workouts, mock_garmin_client
):
    """Test upload_workout handles empty dict gracefully"""
    result = await app_with_workouts.call_tool(
        "upload_workout",
        {"workout_data": {}},
    )

    # Should create a default workout with empty steps (preprocessing adds defaults)
    # or return an error - either way should not crash
    assert result is not None


# =========================================================================
# plan_workout tests (create + schedule in one step)
# =========================================================================


@pytest.mark.asyncio
async def test_plan_workout_creates_and_schedules(
    app_with_workouts, mock_garmin_client
):
    """Test plan_workout creates a workout then schedules it"""
    upload_response = {"workoutId": 2000, "workoutName": "Easy 30min Run"}
    mock_garmin_client.upload_workout.return_value = upload_response

    # Mock garth.post for scheduling
    mock_garmin_client.garth = Mock()
    schedule_response = Mock()
    schedule_response.status_code = 200
    mock_garmin_client.garth.post.return_value = schedule_response

    result = await app_with_workouts.call_tool(
        "plan_workout",
        {"workout_data": VALID_WORKOUT_INPUT, "date": "2024-02-01"},
    )

    parsed = json.loads(_get_text(result))
    assert parsed["status"] == "planned"
    assert parsed["workout_id"] == 2000
    assert parsed["scheduled_date"] == "2024-02-01"

    # Verify upload was called with normalized JSON
    mock_garmin_client.upload_workout.assert_called_once()
    # Verify schedule was called
    mock_garmin_client.garth.post.assert_called_once_with(
        "connectapi",
        "workout-service/schedule/2000",
        json={"date": "2024-02-01"},
    )


@pytest.mark.asyncio
async def test_plan_workout_fails_if_no_workout_id(
    app_with_workouts, mock_garmin_client
):
    """Test plan_workout returns error if upload doesn't return a workout ID"""
    mock_garmin_client.upload_workout.return_value = {"status": "ok"}

    result = await app_with_workouts.call_tool(
        "plan_workout",
        {"workout_data": VALID_WORKOUT_INPUT, "date": "2024-02-01"},
    )

    parsed = json.loads(_get_text(result))
    assert parsed["status"] == "error"
    assert "no workout ID" in parsed["message"]


# =========================================================================
# update_workout tests
# =========================================================================


@pytest.mark.asyncio
async def test_update_workout_fetches_existing_then_puts(
    app_with_workouts, mock_garmin_client
):
    """Test update_workout fetches existing workout, normalizes input, and PUTs"""
    mock_garmin_client.get_workout_by_id.return_value = MOCK_WORKOUT_DETAILS

    mock_garmin_client.garth = Mock()
    put_response = Mock()
    put_response.text = json.dumps(
        {"workoutId": 123456, "workoutName": "Easy 30min Run", "updatedDate": "2024-01-16"}
    )
    put_response.json.return_value = json.loads(put_response.text)
    mock_garmin_client.garth.put.return_value = put_response

    result = await app_with_workouts.call_tool(
        "update_workout",
        {"workout_id": 123456, "workout_data": VALID_WORKOUT_INPUT},
    )

    parsed = json.loads(_get_text(result))
    assert parsed["status"] == "updated"
    assert parsed["workout_id"] == 123456

    mock_garmin_client.get_workout_by_id.assert_called_once_with(123456)
    mock_garmin_client.garth.put.assert_called_once()
    # Verify the PUT payload has workoutId preserved
    put_call = mock_garmin_client.garth.put.call_args
    assert put_call[1]["json"]["workoutId"] == 123456


@pytest.mark.asyncio
async def test_update_workout_not_found(app_with_workouts, mock_garmin_client):
    """Test update_workout returns error when workout doesn't exist"""
    mock_garmin_client.get_workout_by_id.return_value = None

    result = await app_with_workouts.call_tool(
        "update_workout",
        {"workout_id": 99999, "workout_data": VALID_WORKOUT_INPUT},
    )

    parsed = json.loads(_get_text(result))
    assert parsed["status"] == "error"
    assert "not found" in parsed["message"]


# =========================================================================
# delete_workout tests
# =========================================================================


@pytest.mark.asyncio
async def test_delete_workout_success(app_with_workouts, mock_garmin_client):
    """Test delete_workout returns success when workout is deleted"""
    mock_garmin_client.delete_workout.return_value = True

    result = await app_with_workouts.call_tool(
        "delete_workout", {"workout_id": 123456}
    )

    parsed = json.loads(_get_text(result))
    assert parsed["status"] == "deleted"
    assert parsed["workout_id"] == 123456
    mock_garmin_client.delete_workout.assert_called_once_with(123456)


@pytest.mark.asyncio
async def test_delete_workout_failure(app_with_workouts, mock_garmin_client):
    """Test delete_workout returns failure status"""
    mock_garmin_client.delete_workout.return_value = False

    result = await app_with_workouts.call_tool(
        "delete_workout", {"workout_id": 123456}
    )

    parsed = json.loads(_get_text(result))
    assert parsed["status"] == "failed"


# =========================================================================
# schedule_workout tests
# =========================================================================


@pytest.mark.asyncio
async def test_schedule_workout_tool(app_with_workouts, mock_garmin_client):
    """Test schedule_workout schedules an existing workout"""
    mock_garmin_client.garth = Mock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_garmin_client.garth.post.return_value = mock_response

    result = await app_with_workouts.call_tool(
        "schedule_workout",
        {"workout_id": 123456, "calendar_date": "2024-02-01"},
    )

    parsed = json.loads(_get_text(result))
    assert parsed["status"] == "success"
    assert parsed["scheduled_date"] == "2024-02-01"


# =========================================================================
# Error handling tests
# =========================================================================


@pytest.mark.asyncio
async def test_get_workouts_no_data(app_with_workouts, mock_garmin_client):
    """Test get_workouts tool when no workouts found"""
    mock_garmin_client.get_workouts.return_value = None

    result = await app_with_workouts.call_tool("get_workouts", {})

    assert result is not None


@pytest.mark.asyncio
async def test_upload_workout_exception(app_with_workouts, mock_garmin_client):
    """Test upload_workout tool when upload fails"""
    mock_garmin_client.upload_workout.side_effect = Exception("Upload failed")

    result = await app_with_workouts.call_tool(
        "upload_workout", {"workout_data": VALID_WORKOUT_INPUT}
    )

    assert result is not None
    assert "Error" in str(result) or "error" in str(result).lower()
