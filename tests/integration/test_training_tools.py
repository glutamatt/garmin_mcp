"""
Integration tests for training module MCP tools (7 tools).

Tests the thin tool wrappers via FastMCP call_tool with mocked Garmin client.
"""
import json
import pytest
from mcp.server.fastmcp import FastMCP

from garmin_mcp import training


def _parse(result):
    """Extract JSON from call_tool result tuple: (content_list, is_error)."""
    return json.loads(result[0][0].text)


@pytest.fixture
def app(mock_garmin_client):
    """Create FastMCP app with training tools registered."""
    a = FastMCP("Test Training")
    a = training.register_tools(a)
    return a


# ── get_max_metrics ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_max_metrics(app, mock_garmin_client):
    mock_garmin_client.get_max_metrics.return_value = {
        "metricType": "RUNNING",
        "vo2MaxValue": 52.5,
        "fitnessAge": 25,
        "lactateThresholdHeartRate": 170,
        "lactateThresholdSpeed": 3.5,
    }

    result = await app.call_tool("get_max_metrics", {"date": "2024-01-15"})
    data = _parse(result)

    assert data["vo2_max"] == 52.5
    assert data["fitness_age_years"] == 25
    mock_garmin_client.get_max_metrics.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_max_metrics_no_data(app, mock_garmin_client):
    mock_garmin_client.get_max_metrics.return_value = None

    result = await app.call_tool("get_max_metrics", {"date": "2024-01-15"})
    data = _parse(result)

    assert "error" in data


# ── get_hrv_data ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_hrv_data(app, mock_garmin_client):
    mock_garmin_client.get_hrv_data.return_value = {
        "hrvSummary": {
            "calendarDate": "2024-01-15",
            "lastNightAvg": 45,
            "lastNight5MinHigh": 65,
            "weeklyAvg": 48,
            "baseline": {"balancedLow": 35, "balancedUpper": 55},
            "status": "BALANCED",
        }
    }

    result = await app.call_tool("get_hrv_data", {"date": "2024-01-15"})
    data = _parse(result)

    assert data["last_night_avg_hrv_ms"] == 45
    assert data["status"] == "BALANCED"
    mock_garmin_client.get_hrv_data.assert_called_once_with("2024-01-15")


# ── get_training_status ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_training_status(app, mock_garmin_client):
    mock_garmin_client.get_training_status.return_value = {
        "mostRecentTrainingStatus": {
            "latestTrainingStatusData": {
                "device123": {
                    "calendarDate": "2024-01-15",
                    "trainingStatus": "PRODUCTIVE",
                    "sport": "RUNNING",
                    "fitnessTrend": "UP",
                    "acuteTrainingLoadDTO": {
                        "dailyTrainingLoadAcute": 500,
                        "dailyTrainingLoadChronic": 400,
                        "dailyAcuteChronicWorkloadRatio": 1.25,
                        "acwrStatus": "OPTIMAL",
                    },
                }
            }
        },
        "mostRecentVO2Max": {"generic": {"vo2MaxValue": 52.5}},
        "mostRecentTrainingLoadBalance": {
            "metricsTrainingLoadBalanceDTOMap": {
                "device123": {
                    "monthlyLoadAerobicLow": 200,
                    "monthlyLoadAerobicHigh": 150,
                    "monthlyLoadAnaerobic": 50,
                }
            }
        },
    }

    result = await app.call_tool("get_training_status", {"date": "2024-01-15"})
    data = _parse(result)

    assert data["training_status"] == "PRODUCTIVE"
    assert data["vo2_max"] == 52.5
    mock_garmin_client.get_training_status.assert_called_once_with("2024-01-15")


# ── get_progress_summary ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_progress_summary(app, mock_garmin_client):
    mock_garmin_client.get_progress_summary_between_dates.return_value = [
        {
            "date": "2024-01-15",
            "countOfActivities": 10,
            "stats": {
                "running": {
                    "distance": {
                        "count": 10,
                        "sum": 5000000,
                        "avg": 500000,
                        "min": 300000,
                        "max": 1000000,
                    }
                }
            },
        }
    ]

    result = await app.call_tool(
        "get_progress_summary",
        {"start_date": "2024-01-01", "end_date": "2024-01-15", "metric": "distance"},
    )
    data = _parse(result)

    assert data["entries"][0]["total_distance_meters"] == 50000.0
    assert data["entries"][0]["activity_count"] == 10
    mock_garmin_client.get_progress_summary_between_dates.assert_called_once_with(
        "2024-01-01", "2024-01-15", "distance"
    )


# ── get_race_predictions ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_race_predictions(app, mock_garmin_client):
    mock_garmin_client.get_race_predictions.return_value = {"5K": "22:00", "10K": "46:00"}

    result = await app.call_tool("get_race_predictions", {})
    data = _parse(result)

    assert "5K" in data
    mock_garmin_client.get_race_predictions.assert_called_once()


@pytest.mark.asyncio
async def test_get_race_predictions_no_data(app, mock_garmin_client):
    mock_garmin_client.get_race_predictions.return_value = None

    result = await app.call_tool("get_race_predictions", {})
    data = _parse(result)

    assert "error" in data


# ── get_goals ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_goals(app, mock_garmin_client):
    mock_garmin_client.get_goals.return_value = [{"goalType": "steps", "target": 10000}]

    result = await app.call_tool("get_goals", {"goal_type": "active"})
    data = _parse(result)

    assert isinstance(data, list)
    mock_garmin_client.get_goals.assert_called_once_with("active")


@pytest.mark.asyncio
async def test_get_goals_no_data(app, mock_garmin_client):
    mock_garmin_client.get_goals.return_value = None

    result = await app.call_tool("get_goals", {})
    data = _parse(result)

    assert "error" in data


# ── get_personal_record ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_personal_record(app, mock_garmin_client):
    mock_garmin_client.get_personal_record.return_value = [{"recordType": "FASTEST_5K"}]

    result = await app.call_tool("get_personal_record", {})
    data = _parse(result)

    assert isinstance(data, list)
    mock_garmin_client.get_personal_record.assert_called_once()


# ── exception handling ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_exception_returns_json_error(app, mock_garmin_client):
    mock_garmin_client.get_max_metrics.side_effect = RuntimeError("Timeout")

    result = await app.call_tool("get_max_metrics", {"date": "2024-01-15"})
    data = _parse(result)

    assert "error" in data
    assert "Timeout" in data["error"]
