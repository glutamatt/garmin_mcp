"""
Integration tests for workouts module MCP tools

Tests workout tools using FastMCP integration with mocked Garmin API responses.
"""
import pytest
from unittest.mock import Mock, patch
from mcp.server.fastmcp import FastMCP

from garmin_mcp import workouts
from tests.fixtures.garmin_responses import (
    MOCK_WORKOUTS,
    MOCK_WORKOUT_DETAILS,
)


@pytest.fixture
def app_with_workouts():
    """Create FastMCP app with workouts tools registered"""
    app = FastMCP("Test Workouts")
    app = workouts.register_tools(app)
    return app


@pytest.mark.asyncio
async def test_get_workouts_tool(app_with_workouts, mock_garmin_client):
    """Test get_workouts tool returns all workouts"""
    # Setup mock
    mock_garmin_client.get_workouts.return_value = MOCK_WORKOUTS

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.workouts.get_client", mock_get_client):
        # Call tool
        result = await app_with_workouts.call_tool(
            "get_workouts",
            {}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_workouts.assert_called_once()


@pytest.mark.asyncio
async def test_get_workout_by_id_tool(app_with_workouts, mock_garmin_client):
    """Test get_workout_by_id tool returns specific workout (numeric ID)"""
    import json as json_module

    # Setup mock
    mock_garmin_client.get_workout_by_id.return_value = MOCK_WORKOUT_DETAILS

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.workouts.get_client", mock_get_client):
        # Call tool with numeric ID (FastMCP passes numeric strings as int)
        workout_id = 123456
        result = await app_with_workouts.call_tool(
            "get_workout_by_id",
            {"workout_id": workout_id}
        )

    # Verify - tool converts to int for numeric IDs
    assert result is not None
    mock_garmin_client.get_workout_by_id.assert_called_once_with(123456)

    # Parse the result and verify curation
    result_data = json_module.loads(result[0].text)
    assert result_data["id"] == 123456
    assert result_data["name"] == "5K Tempo Run"
    assert result_data["sport"] == "running"


@pytest.mark.asyncio
async def test_get_workout_by_uuid_tool(app_with_workouts, mock_garmin_client):
    """Test get_workout_by_id tool with UUID (training plan workout)"""
    import json as json_module

    # Setup mock for garth.get call (fbt-adaptive endpoint)
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "workoutId": None,
        "workoutUuid": "d7a5491b-42a5-4d2d-ba38-4e414fc03caf",
        "workoutName": "Base",
        "description": "6:20/km",
        "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
        "estimatedDurationInSecs": 2160,
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSteps": [{
                "type": "ExecutableStepDTO",
                "stepOrder": 1,
            }]
        }]
    }
    mock_garmin_client.garth.get.return_value = mock_response

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.workouts.get_client", mock_get_client):
        # Call tool with UUID (contains dashes)
        workout_uuid = "d7a5491b-42a5-4d2d-ba38-4e414fc03caf"
        result = await app_with_workouts.call_tool(
            "get_workout_by_id",
            {"workout_id": workout_uuid}
        )

    # Verify fbt-adaptive endpoint was called
    assert result is not None
    mock_garmin_client.garth.get.assert_called_once_with(
        "connectapi",
        f"workout-service/fbt-adaptive/{workout_uuid}"
    )

    # Parse the result and verify training plan workout fields
    result_data = json_module.loads(result[0].text)
    assert result_data["name"] == "Base"
    assert result_data["sport"] == "running"
    assert result_data["estimated_duration_sec"] == 2160


@pytest.mark.asyncio
async def test_upload_workout_tool(app_with_workouts, mock_garmin_client):
    """Test upload_workout tool uploads new workout"""
    # Setup mock
    upload_response = {
        "workoutId": 123457,
        "workoutName": "New Workout"
    }
    mock_garmin_client.upload_workout.return_value = upload_response

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.workouts.get_client", mock_get_client):
        # Call tool - pass dict which is passed directly to API
        workout_data = {"workoutName": "New Workout", "sportType": {"sportTypeId": 1}}
        result = await app_with_workouts.call_tool(
            "upload_workout",
            {"workout_data": workout_data}
        )

    # Verify - dict is passed directly to the API
    assert result is not None
    mock_garmin_client.upload_workout.assert_called_once_with(workout_data)


@pytest.mark.asyncio
async def test_get_scheduled_workouts_tool(app_with_workouts, mock_garmin_client):
    """Test get_scheduled_workouts tool - uses GraphQL query"""
    import json as json_module

    # Setup mock for GraphQL query - matches actual API response structure
    graphql_response = {
        "data": {
            "workoutScheduleSummariesScalar": [
                {
                    "workoutUuid": "abc-123-def",
                    "workoutId": 123456,
                    "workoutName": "5K Tempo Run",
                    "workoutType": "running",
                    "scheduleDate": "2024-01-15",
                    "associatedActivityId": None,
                }
            ]
        }
    }
    mock_garmin_client.query_garmin_graphql.return_value = graphql_response

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.workouts.get_client", mock_get_client):
        # Call tool
        result = await app_with_workouts.call_tool(
            "get_scheduled_workouts",
            {"start_date": "2024-01-08", "end_date": "2024-01-15"}
        )

    # Verify curation extracts correct fields
    result_data = json_module.loads(result[0].text)
    assert result_data["count"] == 1
    workout = result_data["scheduled"][0]
    assert workout["name"] == "5K Tempo Run"
    assert workout["sport"] == "running"
    assert workout["completed"] is False

    # Verify
    assert result is not None
    mock_garmin_client.query_garmin_graphql.assert_called_once()


@pytest.mark.asyncio
async def test_get_training_plan_workouts_tool(app_with_workouts, mock_garmin_client):
    """Test get_training_plan_workouts tool - uses GraphQL query"""
    import json as json_module

    # Setup mock for GraphQL query - matches actual API response structure
    graphql_response = {
        "data": {
            "trainingPlanScalar": {
                "trainingPlanWorkoutScheduleDTOS": [
                    {
                        "planName": "5K Training Plan",
                        "trainingPlanDetailsDTO": {
                            "athletePlanId": 12345,
                            "workoutsPerWeek": 4
                        },
                        "workoutScheduleSummaries": [
                            {
                                "workoutUuid": "abc-123-def",
                                "workoutId": None,
                                "workoutName": "Base Run",
                                "workoutType": "running",
                                "scheduleDate": "2024-01-15",
                                "associatedActivityId": None,
                            },
                            {
                                "workoutUuid": "xyz-456-ghi",
                                "workoutId": None,
                                "workoutName": "Strength",
                                "workoutType": "strength_training",
                                "scheduleDate": "2024-01-15",
                                "associatedActivityId": 987654,
                            }
                        ]
                    }
                ]
            }
        }
    }
    mock_garmin_client.query_garmin_graphql.return_value = graphql_response

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.workouts.get_client", mock_get_client):
        # Call tool
        result = await app_with_workouts.call_tool(
            "get_training_plan_workouts",
            {"calendar_date": "2024-01-15"}
        )

    # Verify
    assert result is not None
    mock_garmin_client.query_garmin_graphql.assert_called_once()

    # Verify curation extracts correct fields
    result_data = json_module.loads(result[0].text)
    assert result_data["training_plans"] == ["5K Training Plan"]
    assert result_data["count"] == 2

    # Verify workouts are curated correctly
    workouts_list = result_data["workouts"]
    assert workouts_list[0]["name"] == "Base Run"
    assert workouts_list[0]["completed"] is False

    # Verify completed workout
    assert workouts_list[1]["name"] == "Strength"
    assert workouts_list[1]["completed"] is True


@pytest.mark.asyncio
async def test_schedule_workout_tool(app_with_workouts, mock_garmin_client):
    """Test schedule_workout tool"""
    # Setup mock for garth.post call
    mock_response = Mock()
    mock_response.status_code = 200
    mock_garmin_client.garth.post.return_value = mock_response

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.workouts.get_client", mock_get_client):
        # Call tool
        result = await app_with_workouts.call_tool(
            "schedule_workout",
            {"workout_id": 123456, "calendar_date": "2024-01-20"}
        )

    # Verify
    assert result is not None
    mock_garmin_client.garth.post.assert_called_once()


# Error handling tests
@pytest.mark.asyncio
async def test_get_workouts_no_data(app_with_workouts, mock_garmin_client):
    """Test get_workouts tool when no workouts found"""
    # Setup mock to return None
    mock_garmin_client.get_workouts.return_value = None

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.workouts.get_client", mock_get_client):
        # Call tool
        result = await app_with_workouts.call_tool(
            "get_workouts",
            {}
        )

    # Verify error message is returned
    assert result is not None


@pytest.mark.asyncio
async def test_upload_workout_exception(app_with_workouts, mock_garmin_client):
    """Test upload_workout tool when upload fails"""
    # Setup mock to raise exception
    mock_garmin_client.upload_workout.side_effect = Exception("Upload failed")

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.workouts.get_client", mock_get_client):
        # Call tool with valid workout data
        result = await app_with_workouts.call_tool(
            "upload_workout",
            {"workout_data": {}}
        )

    # Verify error is handled gracefully
    assert result is not None
