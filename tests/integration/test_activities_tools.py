"""
Integration tests for activities module MCP tools (v2 — 5 tools).

Tests the thin tool wrappers via FastMCP call_tool with mocked Garmin client.
"""
import json
import pytest
from mcp.server.fastmcp import FastMCP

from garmin_mcp import activities


def _parse(result):
    """Extract JSON from call_tool result tuple: (content_list, is_error)."""
    return json.loads(result[0][0].text)


SAMPLE_RAW = {
    "activityId": 12345,
    "activityName": "Morning Run",
    "activityType": {"typeKey": "running", "typeId": 1},
    "startTimeLocal": "2024-01-15 07:00:00",
    "distance": 10000.0,
    "duration": 3000.0,
    "movingDuration": 2900.0,
    "averageHR": 150,
    "maxHR": 175,
    "calories": 500,
}


@pytest.fixture
def app(mock_garmin_client):
    """Create FastMCP app with activities tools registered."""
    a = FastMCP("Test Activities")
    a = activities.register_tools(a)
    return a


# ── get_activities — date range mode ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_activities_by_date(app, mock_garmin_client):
    mock_garmin_client.get_activities_by_date.return_value = [SAMPLE_RAW]

    result = await app.call_tool(
        "get_activities",
        {"start_date": "2024-01-01", "end_date": "2024-01-15"},
    )
    data = _parse(result)

    assert data["count"] == 1
    assert data["activities"][0]["id"] == 12345
    assert data["activities"][0]["type"] == "running"
    # Raw keys must not leak
    assert "activityId" not in data["activities"][0]
    mock_garmin_client.get_activities_by_date.assert_called_once()


# ── get_activities — pagination mode ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_activities_pagination(app, mock_garmin_client):
    mock_garmin_client.get_activities.return_value = [SAMPLE_RAW] * 5

    result = await app.call_tool("get_activities", {"start": 0, "limit": 5})
    data = _parse(result)

    assert data["count"] == 5
    mock_garmin_client.get_activities.assert_called_once_with(0, 5)


@pytest.mark.asyncio
async def test_get_activities_no_data(app, mock_garmin_client):
    mock_garmin_client.get_activities.return_value = []

    result = await app.call_tool("get_activities", {})
    data = _parse(result)

    assert "error" in data


# ── get_activity ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_activity(app, mock_garmin_client):
    mock_garmin_client.get_activity.return_value = {
        "activityId": 12345,
        "activityName": "Morning Run",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "startTimeLocal": "2024-01-15 07:00:00",
            "duration": 3000.0,
            "distance": 10000.0,
            "averageSpeed": 3.33,
            "averageHR": 150,
            "maxHR": 175,
            "calories": 500,
            "trainingEffect": 3.5,
            "anaerobicTrainingEffect": 1.2,
            "activityTrainingLoad": 85,
        },
        "metadataDTO": {"lapCount": 5, "hasSplits": True},
    }
    mock_garmin_client.get_activity_weather.return_value = None

    result = await app.call_tool("get_activity", {"activity_id": 12345})
    data = _parse(result)

    assert data["id"] == 12345
    assert data["type"] == "running"
    assert data["training_effect"] == 3.5
    mock_garmin_client.get_activity.assert_called_once_with(12345)


@pytest.mark.asyncio
async def test_get_activity_no_data(app, mock_garmin_client):
    mock_garmin_client.get_activity.return_value = None

    result = await app.call_tool("get_activity", {"activity_id": 99999})
    data = _parse(result)

    assert "error" in data


# ── get_activity_splits ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_activity_splits(app, mock_garmin_client):
    mock_garmin_client.get_activity_splits.return_value = {
        "activityId": 12345,
        "lapDTOs": [
            {
                "lapIndex": 1,
                "distance": 1000.0,
                "duration": 300.0,
                "averageSpeed": 3.33,
                "averageHR": 145,
                "maxHR": 155,
            }
        ],
    }

    result = await app.call_tool("get_activity_splits", {"activity_id": 12345})
    data = _parse(result)

    assert data["lap_count"] == 1
    assert data["laps"][0]["lap_number"] == 1
    mock_garmin_client.get_activity_splits.assert_called_once_with(12345)


# ── get_activity_hr_in_timezones ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_activity_hr_in_timezones(app, mock_garmin_client):
    mock_garmin_client.get_activity_hr_in_timezones.return_value = [
        {"zoneNumber": 1, "secsInZone": 600, "zoneLowBoundary": 100},
        {"zoneNumber": 2, "secsInZone": 900, "zoneLowBoundary": 120},
    ]

    result = await app.call_tool("get_activity_hr_in_timezones", {"activity_id": 12345})
    data = _parse(result)

    assert result is not None
    mock_garmin_client.get_activity_hr_in_timezones.assert_called_once_with(12345)


# ── get_activity_types ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_activity_types(app, mock_garmin_client):
    mock_garmin_client.get_activity_types.return_value = [
        {"typeId": 1, "typeKey": "running", "displayName": "Running", "parentTypeId": 17},
        {"typeId": 2, "typeKey": "cycling", "displayName": "Cycling", "parentTypeId": 17},
    ]

    result = await app.call_tool("get_activity_types", {})
    data = _parse(result)

    assert data["count"] == 2
    assert data["activity_types"][0]["type_key"] == "running"


# ── exception handling ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_exception_returns_json_error(app, mock_garmin_client):
    mock_garmin_client.get_activities.side_effect = RuntimeError("Auth failed")

    result = await app.call_tool("get_activities", {})
    data = _parse(result)

    assert "error" in data
    assert "Auth failed" in data["error"]
