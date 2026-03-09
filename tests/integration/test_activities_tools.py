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

SAMPLE_RAW_FULL = {
    **SAMPLE_RAW,
    # Training effect (list endpoint key names)
    "aerobicTrainingEffect": 3.1,
    "anaerobicTrainingEffect": 0.5,
    "trainingEffectLabel": "AEROBIC_BASE",
    # Power (list endpoint key names)
    "avgPower": 238,
    "normPower": 246,
    # HR zones inline (list endpoint)
    "hrTimeInZone_1": 149.0,
    "hrTimeInZone_2": 2049.7,
    "hrTimeInZone_3": 232.0,
    "hrTimeInZone_4": 0.0,
    "hrTimeInZone_5": 0.0,
    # VO2max & body battery
    "vO2MaxValue": 51.0,
    "differenceBodyBattery": -8,
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


# ── get_activities — enriched fields (training effect, power, HR zones) ──────


@pytest.mark.asyncio
async def test_get_activities_training_fields(app, mock_garmin_client):
    """Training effect, power, HR zones, VO2max from list endpoint."""
    mock_garmin_client.get_activities_by_date.return_value = [SAMPLE_RAW_FULL]

    result = await app.call_tool(
        "get_activities",
        {"start_date": "2024-01-01", "end_date": "2024-01-15"},
    )
    data = _parse(result)
    act = data["activities"][0]

    # Training effect (list uses aerobicTrainingEffect key)
    assert act["training_effect"] == 3.1
    assert act["anaerobic_training_effect"] == 0.5
    assert act["training_effect_label"] == "AEROBIC_BASE"
    # Power (list uses avgPower/normPower keys)
    assert act["avg_power_watts"] == 238
    assert act["normalized_power_watts"] == 246
    # HR zones inline
    assert act["hr_zones_seconds"] == {"z1": 149, "z2": 2050, "z3": 232}
    # Zero zones should not appear (clean_nones strips them after rounding)
    assert "z4" not in act["hr_zones_seconds"]
    assert "z5" not in act["hr_zones_seconds"]
    # VO2max & body battery
    assert act["vo2max"] == 51.0
    assert act["body_battery_impact"] == -8


@pytest.mark.asyncio
async def test_get_activities_hr_zones_zero_excluded(app, mock_garmin_client):
    """HR zones with value 0.0 should not appear in output."""
    raw = {**SAMPLE_RAW, "hrTimeInZone_1": 600.0, "hrTimeInZone_2": 0.0}
    mock_garmin_client.get_activities.return_value = [raw]

    result = await app.call_tool("get_activities", {"start": 0, "limit": 1})
    data = _parse(result)
    zones = data["activities"][0]["hr_zones_seconds"]

    assert zones == {"z1": 600}


@pytest.mark.asyncio
async def test_get_activities_no_hr_zones(app, mock_garmin_client):
    """Activities without HR zone data should not have hr_zones_seconds key."""
    mock_garmin_client.get_activities.return_value = [SAMPLE_RAW]

    result = await app.call_tool("get_activities", {"start": 0, "limit": 1})
    data = _parse(result)

    assert "hr_zones_seconds" not in data["activities"][0]


# ── get_activity — detail with RPE ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_activity_with_rpe(app, mock_garmin_client):
    """Detail endpoint includes perceived_effort and workout_feel."""
    mock_garmin_client.get_activity.return_value = {
        "activityId": 12345,
        "activityName": "Morning Run",
        "activityTypeDTO": {"typeKey": "running"},
        "summaryDTO": {
            "duration": 3000.0,
            "distance": 10000.0,
            "averageHR": 150,
            "trainingEffect": 3.5,
            "activityTrainingLoad": 85,
            "directWorkoutRpe": 7,
            "directWorkoutFeel": 75,
        },
        "metadataDTO": {},
    }
    mock_garmin_client.get_activity_weather.return_value = None

    result = await app.call_tool("get_activity", {"activity_id": 12345})
    data = _parse(result)

    assert data["perceived_effort"] == 7
    assert data["workout_feel"] == 75
    assert data["training_load"] == 85


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
