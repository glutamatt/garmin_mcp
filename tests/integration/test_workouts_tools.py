"""
Integration tests for workouts module MCP tools

Tests all 7 workout tools using FastMCP integration with mocked Garmin API responses.
"""
import pytest
from unittest.mock import Mock
from mcp.server.fastmcp import FastMCP

from garmin_mcp import workouts
from tests.fixtures.garmin_responses import (
    MOCK_WORKOUTS,
    MOCK_WORKOUT_DETAILS,
)


@pytest.fixture
def app_with_workouts(mock_garmin_client):
    """Create FastMCP app with workouts tools registered"""
    workouts.configure(mock_garmin_client)
    app = FastMCP("Test Workouts")
    app = workouts.register_tools(app)
    return app


@pytest.mark.asyncio
async def test_get_workouts_tool(app_with_workouts, mock_garmin_client):
    """Test get_workouts tool returns all workouts"""
    # Setup mock
    mock_garmin_client.get_workouts.return_value = MOCK_WORKOUTS

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
    """Test get_workout_by_id tool returns specific workout"""
    # Setup mock
    mock_garmin_client.get_workout_by_id.return_value = MOCK_WORKOUT_DETAILS

    # Call tool
    workout_id = 123456
    result = await app_with_workouts.call_tool(
        "get_workout_by_id",
        {"workout_id": workout_id}
    )

    # Verify
    assert result is not None
    mock_garmin_client.get_workout_by_id.assert_called_once_with(workout_id)


@pytest.mark.asyncio
async def test_download_workout_tool(app_with_workouts, mock_garmin_client):
    """Test download_workout tool downloads workout data"""
    # Setup mock
    workout_data = {
        "workoutId": 123456,
        "workoutName": "5K Tempo Run",
        "data": "...workout file content..."
    }
    mock_garmin_client.download_workout.return_value = workout_data

    # Call tool
    workout_id = 123456
    result = await app_with_workouts.call_tool(
        "download_workout",
        {"workout_id": workout_id}
    )

    # Verify
    assert result is not None
    mock_garmin_client.download_workout.assert_called_once_with(workout_id)


@pytest.mark.asyncio
async def test_upload_workout_tool(app_with_workouts, mock_garmin_client):
    """Test upload_workout tool uploads new workout"""
    # Setup mock
    upload_response = {
        "status": "success",
        "workoutId": 123457,
        "message": "Workout uploaded successfully"
    }
    mock_garmin_client.upload_workout.return_value = upload_response

    # Call tool - pass dict which will be converted to JSON
    workout_data = {"workoutName": "New Workout", "sportType": {"sportTypeId": 1}}
    result = await app_with_workouts.call_tool(
        "upload_workout",
        {"workout_data": workout_data}
    )

    # Verify - the function normalizes and converts dict to JSON string before calling API
    assert result is not None
    import json
    mock_garmin_client.upload_workout.assert_called_once()

    # Verify the normalized payload contains the original data plus defaults
    call_args = mock_garmin_client.upload_workout.call_args[0][0]
    normalized_data = json.loads(call_args)
    assert normalized_data["workoutName"] == "New Workout"
    assert normalized_data["sportType"]["sportTypeId"] == 1
    # Check normalization added required defaults
    assert "avgTrainingSpeed" in normalized_data
    assert "estimatedDurationInSecs" in normalized_data


@pytest.mark.asyncio
async def test_upload_activity_tool(app_with_workouts, mock_garmin_client):
    """Test upload_activity tool - returns placeholder message"""
    # Call tool - this is a placeholder implementation that doesn't call the client
    file_path = "/path/to/activity.fit"
    result = await app_with_workouts.call_tool(
        "upload_activity",
        {"file_path": file_path}
    )

    # Verify - should return placeholder message
    assert result is not None
    assert "not supported" in str(result).lower()


@pytest.mark.asyncio
async def test_schedule_workout_directly_tool(app_with_workouts, mock_garmin_client):
    """Test schedule_workout_directly tool - schedules workout without saving to library"""
    # Setup mock
    mock_garmin_client.schedule_workout_directly.return_value = {
        "workoutScheduleId": 98765,
        "workout": {"workoutName": "Quick Run"},
        "calendarDate": "2024-01-20",
        "createdDate": "2024-01-15T10:00:00.000"
    }

    # Call tool
    workout_data = {
        "workoutName": "Quick Run",
        "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
        "workoutSegments": []
    }
    result = await app_with_workouts.call_tool(
        "schedule_workout_directly",
        {"workout_data": workout_data, "date": "2024-01-20"}
    )

    # Verify
    assert result is not None
    mock_garmin_client.schedule_workout_directly.assert_called_once()

    # Verify the call included the normalized workout and date
    call_args = mock_garmin_client.schedule_workout_directly.call_args
    normalized_workout = call_args[0][0]
    date = call_args[0][1]
    assert normalized_workout["workoutName"] == "Quick Run"
    assert "avgTrainingSpeed" in normalized_workout  # Normalization applied
    assert date == "2024-01-20"

    # Verify response
    import json
    response = json.loads(result[0].text)
    assert response["status"] == "scheduled"
    assert response["workout_schedule_id"] == 98765


@pytest.mark.asyncio
async def test_get_scheduled_workouts_tool(app_with_workouts, mock_garmin_client):
    """Test get_scheduled_workouts tool - uses GraphQL query"""
    # Setup mock for GraphQL query
    graphql_response = {
        "data": {
            "workoutScheduleSummariesScalar": [
                {
                    "workoutId": 123456,
                    "workoutName": "5K Tempo Run",
                    "scheduledDate": "2024-01-15",
                    "completed": False
                }
            ]
        }
    }
    mock_garmin_client.query_garmin_graphql.return_value = graphql_response

    # Call tool
    result = await app_with_workouts.call_tool(
        "get_scheduled_workouts",
        {"start_date": "2024-01-08", "end_date": "2024-01-15"}
    )

    # Verify
    assert result is not None
    mock_garmin_client.query_garmin_graphql.assert_called_once()


@pytest.mark.asyncio
async def test_get_training_plan_workouts_tool(app_with_workouts, mock_garmin_client):
    """Test get_training_plan_workouts tool - uses GraphQL query"""
    # Setup mock for GraphQL query
    graphql_response = {
        "data": {
            "trainingPlanScalar": {
                "trainingPlanWorkoutScheduleDTOS": [
                    {
                        "workoutId": 123456,
                        "workoutName": "Week 1 - Day 1",
                        "planName": "5K Training Plan",
                        "calendarDate": "2024-01-15"
                    }
                ]
            }
        }
    }
    mock_garmin_client.query_garmin_graphql.return_value = graphql_response

    # Call tool
    result = await app_with_workouts.call_tool(
        "get_training_plan_workouts",
        {"calendar_date": "2024-01-15"}
    )

    # Verify
    assert result is not None
    mock_garmin_client.query_garmin_graphql.assert_called_once()


# Error handling tests
@pytest.mark.asyncio
async def test_get_workouts_no_data(app_with_workouts, mock_garmin_client):
    """Test get_workouts tool when no workouts found"""
    # Setup mock to return None
    mock_garmin_client.get_workouts.return_value = None

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

    # Call tool with valid workout data
    result = await app_with_workouts.call_tool(
        "upload_workout",
        {"workout_data": {}}
    )

    # Verify error is handled gracefully
    assert result is not None
