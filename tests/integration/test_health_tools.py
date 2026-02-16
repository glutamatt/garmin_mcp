"""
Integration tests for health module MCP tools (v2 — 9 tools).

Tests the thin tool wrappers via FastMCP call_tool with mocked Garmin client.
"""
import json
import pytest
from mcp.server.fastmcp import FastMCP

from garmin_mcp import health


def _parse(result):
    """Extract JSON from call_tool result tuple: (content_list, is_error)."""
    return json.loads(result[0][0].text)


@pytest.fixture
def app(mock_garmin_client):
    """Create FastMCP app with health tools registered."""
    a = FastMCP("Test Health")
    a = health.register_tools(a)
    return a


# ── get_coaching_snapshot ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_coaching_snapshot(app, mock_garmin_client):
    mock_garmin_client.get_coaching_snapshot.return_value = {
        "date": "2024-01-15",
        "stats": {"calendarDate": "2024-01-15", "totalSteps": 8000, "restingHeartRate": 55},
        "sleep": {
            "dailySleepDTO": {
                "sleepTimeSeconds": 28800,
                "sleepScores": {"overall": {"value": 85}},
                "deepSleepSeconds": 7200,
                "lightSleepSeconds": 14400,
                "remSleepSeconds": 7200,
                "awakeSleepSeconds": 0,
            }
        },
        "training_readiness": [{"calendarDate": "2024-01-15", "score": 65, "level": "MODERATE"}],
        "body_battery": [{"date": "2024-01-15", "charged": 40, "drained": 25}],
        "hrv": {"hrvSummary": {"lastNightAvg": 45, "weeklyAvg": 48, "status": "BALANCED"}},
    }

    result = await app.call_tool("get_coaching_snapshot", {"date": "2024-01-15"})
    data = _parse(result)

    assert data["date"] == "2024-01-15"
    assert data["stats"]["total_steps"] == 8000
    assert data["sleep"]["sleep_score"] == 85
    mock_garmin_client.get_coaching_snapshot.assert_called_once_with("2024-01-15")


# ── get_stats ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_stats(app, mock_garmin_client):
    mock_garmin_client.get_user_summary.return_value = {
        "calendarDate": "2024-01-15",
        "totalSteps": 10000,
        "totalKilocalories": 2500,
        "restingHeartRate": 55,
        "averageStressLevel": 30,
        "bodyBatteryMostRecentValue": 75,
    }

    result = await app.call_tool("get_stats", {"date": "2024-01-15"})
    data = _parse(result)

    assert data["total_steps"] == 10000
    assert data["resting_heart_rate_bpm"] == 55
    mock_garmin_client.get_user_summary.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_stats_no_data(app, mock_garmin_client):
    mock_garmin_client.get_user_summary.return_value = None

    result = await app.call_tool("get_stats", {"date": "2024-01-15"})
    data = _parse(result)

    assert "error" in data


# ── get_sleep ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_sleep(app, mock_garmin_client):
    mock_garmin_client.get_sleep_data.return_value = {
        "dailySleepDTO": {
            "sleepTimeSeconds": 28800,
            "deepSleepSeconds": 7200,
            "lightSleepSeconds": 14400,
            "remSleepSeconds": 7200,
            "awakeSleepSeconds": 0,
            "restingHeartRate": 55,
            "avgSleepStress": 15,
            "sleepScores": {"overall": {"value": 85, "qualifierKey": "GOOD"}},
        },
        "wellnessSpO2SleepSummaryDTO": {"averageSpo2": 96, "lowestSpo2": 93},
        "avgOvernightHrv": 45,
    }

    result = await app.call_tool("get_sleep", {"date": "2024-01-15"})
    data = _parse(result)

    assert data["sleep_score"] == 85
    assert data["total_sleep_hours"] == 8.0
    assert "dailySleepDTO" not in data
    mock_garmin_client.get_sleep_data.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_sleep_no_data(app, mock_garmin_client):
    mock_garmin_client.get_sleep_data.return_value = None

    result = await app.call_tool("get_sleep", {"date": "2024-01-15"})
    data = _parse(result)

    assert "error" in data


# ── get_stress ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_stress(app, mock_garmin_client):
    mock_garmin_client.get_stress_data.return_value = {
        "calendarDate": "2024-01-15",
        "maxStressLevel": 80,
        "avgStressLevel": 35,
        "stressValuesArray": [[1, 10], [2, 50], [3, 80]],
    }

    result = await app.call_tool("get_stress", {"date": "2024-01-15"})
    data = _parse(result)

    assert data["max_stress_level"] == 80
    mock_garmin_client.get_stress_data.assert_called_once_with("2024-01-15")


# ── get_heart_rate ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_heart_rate(app, mock_garmin_client):
    mock_garmin_client.get_heart_rates.return_value = {
        "calendarDate": "2024-01-15",
        "maxHeartRate": 180,
        "minHeartRate": 45,
        "restingHeartRate": 55,
        "lastSevenDaysAvgRestingHeartRate": 57,
        "heartRateValues": [[1, 60], [2, 70]],
    }

    result = await app.call_tool("get_heart_rate", {"date": "2024-01-15"})
    data = _parse(result)

    assert data["resting_heart_rate_bpm"] == 55
    mock_garmin_client.get_heart_rates.assert_called_once_with("2024-01-15")


# ── get_respiration ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_respiration(app, mock_garmin_client):
    mock_garmin_client.get_respiration_data.return_value = {
        "calendarDate": "2024-01-15",
        "lowestRespirationValue": 12,
        "highestRespirationValue": 22,
        "avgWakingRespirationValue": 16,
        "avgSleepRespirationValue": 14,
    }

    result = await app.call_tool("get_respiration", {"date": "2024-01-15"})
    data = _parse(result)

    assert data["lowest_breaths_per_min"] == 12
    mock_garmin_client.get_respiration_data.assert_called_once_with("2024-01-15")


# ── get_body_battery ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_body_battery(app, mock_garmin_client):
    mock_garmin_client.get_body_battery.return_value = [
        {"date": "2024-01-15", "charged": 50, "drained": 30}
    ]

    result = await app.call_tool(
        "get_body_battery", {"start_date": "2024-01-15", "end_date": "2024-01-15"}
    )
    data = _parse(result)

    assert "days" in data
    mock_garmin_client.get_body_battery.assert_called_once()


# ── get_spo2_data ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_spo2_data(app, mock_garmin_client):
    mock_garmin_client.get_spo2_data.return_value = {
        "calendarDate": "2024-01-15",
        "averageSpO2": 96,
        "lowestSpO2": 93,
        "latestSpO2": 97,
    }

    result = await app.call_tool("get_spo2_data", {"date": "2024-01-15"})
    data = _parse(result)

    assert data["avg_spo2_percent"] == 96
    mock_garmin_client.get_spo2_data.assert_called_once_with("2024-01-15")


# ── get_training_readiness ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_training_readiness(app, mock_garmin_client):
    mock_garmin_client.get_training_readiness.return_value = [
        {
            "calendarDate": "2024-01-15",
            "score": 72,
            "level": "MODERATE",
            "feedbackShort": "Moderate readiness",
            "sleepScore": 80,
            "recoveryTime": 120,
        }
    ]

    result = await app.call_tool("get_training_readiness", {"date": "2024-01-15"})
    data = _parse(result)

    assert data["score"] == 72
    assert data["level"] == "MODERATE"


# ── exception handling ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_exception_returns_json_error(app, mock_garmin_client):
    mock_garmin_client.get_user_summary.side_effect = RuntimeError("Connection failed")

    result = await app.call_tool("get_stats", {"date": "2024-01-15"})
    data = _parse(result)

    assert "error" in data
    assert "Connection failed" in data["error"]
