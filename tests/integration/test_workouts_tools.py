"""
Integration tests for workouts module MCP tools (8 tools).

Tests the thin tool wrappers via FastMCP call_tool with mocked Garmin client.
"""
import json
import pytest
from mcp.server.fastmcp import FastMCP

from garmin_mcp import workouts


def _parse(result):
    """Extract JSON from call_tool result tuple: (content_list, is_error)."""
    return json.loads(result[0][0].text)


@pytest.fixture
def app(mock_garmin_client):
    """Create FastMCP app with workout tools registered."""
    a = FastMCP("Test Workouts")
    a = workouts.register_tools(a)
    return a


# ── get_workouts ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_workouts(app, mock_garmin_client):
    mock_garmin_client.get_workouts.return_value = [
        {"workoutId": 1, "workoutName": "Easy Run", "sportType": {"sportTypeKey": "running"}},
    ]

    result = await app.call_tool("get_workouts", {})
    data = _parse(result)

    assert data["count"] == 1
    assert data["workouts"][0]["id"] == 1


@pytest.mark.asyncio
async def test_get_workouts_no_data(app, mock_garmin_client):
    mock_garmin_client.get_workouts.return_value = None

    result = await app.call_tool("get_workouts", {})
    data = _parse(result)

    assert "error" in data


# ── get_workout_by_id ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_workout_by_id(app, mock_garmin_client):
    mock_garmin_client.get_workout_by_id.return_value = {
        "workoutId": 1,
        "workoutName": "Easy Run",
        "sportType": {"sportTypeKey": "running"},
    }

    result = await app.call_tool("get_workout_by_id", {"workout_id": 1})
    data = _parse(result)

    assert data["id"] == 1
    assert data["sport"] == "running"


# ── create_workout ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_workout_without_date(app, mock_garmin_client):
    mock_garmin_client.upload_workout.return_value = {"workoutId": 42, "workoutName": "Test"}

    result = await app.call_tool("create_workout", {
        "workout_data": {
            "workoutName": "Test",
            "sport": "running",
            "steps": [{"stepOrder": 1, "stepType": "warmup", "endCondition": "lap.button"}],
        },
    })
    data = _parse(result)

    assert data["status"] == "created"
    assert data["workout_id"] == 42
    mock_garmin_client.schedule_workout.assert_not_called()


@pytest.mark.asyncio
async def test_create_workout_with_date(app, mock_garmin_client):
    mock_garmin_client.upload_workout.return_value = {"workoutId": 42, "workoutName": "Test"}
    mock_garmin_client.schedule_workout.return_value = {"workoutScheduleId": 99}

    result = await app.call_tool("create_workout", {
        "workout_data": {
            "workoutName": "Test",
            "sport": "running",
            "steps": [{"stepOrder": 1, "stepType": "warmup", "endCondition": "lap.button"}],
        },
        "date": "2024-01-20",
    })
    data = _parse(result)

    assert data["status"] == "planned"
    assert data["schedule_id"] == 99


# ── delete_workout ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_workout(app, mock_garmin_client):
    mock_garmin_client.get_scheduled_workouts_for_range.return_value = []
    mock_garmin_client.delete_workout.return_value = True

    result = await app.call_tool("delete_workout", {"workout_id": 42})
    data = _parse(result)

    assert data["status"] == "deleted"


# ── unschedule_workout ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unschedule_workout(app, mock_garmin_client):
    mock_garmin_client.unschedule_workout.return_value = True

    result = await app.call_tool("unschedule_workout", {"schedule_id": 99})
    data = _parse(result)

    assert data["status"] == "unscheduled"


# ── reschedule_workout ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reschedule_workout(app, mock_garmin_client):
    mock_garmin_client.reschedule_workout.return_value = {
        "workout": {"workoutName": "Tempo"}
    }

    result = await app.call_tool("reschedule_workout", {"schedule_id": 99, "new_date": "2024-01-25"})
    data = _parse(result)

    assert data["status"] == "rescheduled"
    assert data["new_date"] == "2024-01-25"


# ── exception handling ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_exception_returns_json_error(app, mock_garmin_client):
    mock_garmin_client.get_workouts.side_effect = RuntimeError("Auth expired")

    result = await app.call_tool("get_workouts", {})
    data = _parse(result)

    assert "error" in data
    assert "Auth expired" in data["error"]
