"""
Integration tests for training module MCP tools

Tests training tools using FastMCP integration with mocked Garmin API responses.
"""
import pytest
from unittest.mock import patch
from mcp.server.fastmcp import FastMCP

import json

from garmin_mcp import training
from tests.fixtures.garmin_responses import (
    MOCK_PROGRESS_SUMMARY,
    MOCK_HRV_DATA,
    MOCK_TRAINING_STATUS,
)


@pytest.fixture
def app_with_training():
    """Create FastMCP app with training tools registered"""
    app = FastMCP("Test Training")
    app = training.register_tools(app)
    return app


@pytest.mark.asyncio
async def test_get_progress_summary_tool(app_with_training, mock_garmin_client):
    """Test get_progress_summary tool"""
    # Setup mock
    mock_garmin_client.get_progress_summary_between_dates.return_value = MOCK_PROGRESS_SUMMARY

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.training.get_client", mock_get_client):
        # Call tool
        result = await app_with_training.call_tool(
            "get_progress_summary",
            {
                "start_date": "2024-01-08",
                "end_date": "2024-01-15",
                "metric": "duration"
            }
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_progress_summary_between_dates.assert_called_once_with(
        "2024-01-08", "2024-01-15", "duration"
    )


@pytest.mark.asyncio
async def test_get_hill_score_tool(app_with_training, mock_garmin_client):
    """Test get_hill_score tool"""
    # Setup mock
    hill_score = {
        "hillScoreDTOList": [{"calendarDate": "2024-01-15", "overallScore": 75, "strengthScore": 70, "enduranceScore": 80}],
        "periodAvgScore": {"running": 75},
        "maxScore": 80,
    }
    mock_garmin_client.get_hill_score.return_value = hill_score

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.training.get_client", mock_get_client):
        # Call tool
        result = await app_with_training.call_tool(
            "get_hill_score",
            {"start_date": "2024-01-08", "end_date": "2024-01-15"}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_hill_score.assert_called_once_with("2024-01-08", "2024-01-15")


@pytest.mark.asyncio
async def test_get_endurance_score_tool(app_with_training, mock_garmin_client):
    """Test get_endurance_score tool"""
    # Setup mocks
    endurance_score = {
        "avg": 5631,
        "max": 5740,
        "enduranceScoreDTO": {
            "calendarDate": "2024-01-15",
            "overallScore": 5712,
            "classification": "intermediate",
        }
    }
    mock_garmin_client.get_endurance_score.return_value = endurance_score

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.training.get_client", mock_get_client):
        # Call tool
        result = await app_with_training.call_tool(
            "get_endurance_score",
            {"start_date": "2024-01-08", "end_date": "2024-01-15"}
        )

    # Verify API was called correctly
    assert result is not None
    mock_garmin_client.get_endurance_score.assert_called_once_with("2024-01-08", "2024-01-15")

    # Parse the result and verify content
    data = json.loads(result[0].text)

    # Check values
    assert data["period_avg"] == 5631
    assert data["period_max"] == 5740
    assert data["current_score"] == 5712
    assert data["current_date"] == "2024-01-15"
    assert data["classification"] == "intermediate"


@pytest.mark.asyncio
async def test_get_training_effect_tool(app_with_training, mock_garmin_client):
    """Test get_training_effect tool"""
    # Setup mock - get_training_effect uses get_activity internally
    activity_data = {
        "summaryDTO": {
            "trainingEffect": 3.5,
            "anaerobicTrainingEffect": 2.0,
            "trainingEffectLabel": "Highly Improving",
            "activityTrainingLoad": 150,
            "recoveryTime": 720,  # 12 hours in minutes
            "performanceCondition": 95,
        }
    }
    mock_garmin_client.get_activity.return_value = activity_data

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.training.get_client", mock_get_client):
        # Call tool
        result = await app_with_training.call_tool(
            "get_training_effect",
            {"activity_id": 12345678901}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_activity.assert_called_once_with(12345678901)


@pytest.mark.asyncio
async def test_get_hrv_data_tool(app_with_training, mock_garmin_client):
    """Test get_hrv_data tool"""
    # Setup mock
    mock_garmin_client.get_hrv_data.return_value = MOCK_HRV_DATA

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.training.get_client", mock_get_client):
        # Call tool
        result = await app_with_training.call_tool(
            "get_hrv_data",
            {"date": "2024-01-15"}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_hrv_data.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_fitnessage_data_tool(app_with_training, mock_garmin_client):
    """Test get_fitnessage_data tool"""
    # Setup mock
    fitness_age = {
        "fitnessAge": 25.5,
        "chronologicalAge": 30,
        "achievableFitnessAge": 22,
    }
    mock_garmin_client.get_fitnessage_data.return_value = fitness_age

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.training.get_client", mock_get_client):
        # Call tool
        result = await app_with_training.call_tool(
            "get_fitnessage_data",
            {"date": "2024-01-15"}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_fitnessage_data.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_training_status_tool(app_with_training, mock_garmin_client):
    """Test get_training_status tool returns training status"""
    # Setup mock
    mock_garmin_client.get_training_status.return_value = MOCK_TRAINING_STATUS

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.training.get_client", mock_get_client):
        # Call tool
        result = await app_with_training.call_tool(
            "get_training_status",
            {"date": "2024-01-15"}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_training_status.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_lactate_threshold_tool_latest(app_with_training, mock_garmin_client):
    """Test get_lactate_threshold tool returns latest lactate threshold data"""
    # Setup mock with latest=True response format
    lactate_data = {
        "speed_and_heart_rate": {
            "speed": 0.32222132,
            "heartRate": 169,
        },
        "power": {
            "functionalThresholdPower": 334,
            "powerToWeight": 4.575,
        }
    }
    mock_garmin_client.get_lactate_threshold.return_value = lactate_data

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.training.get_client", mock_get_client):
        # Call tool with no dates (gets latest)
        result = await app_with_training.call_tool(
            "get_lactate_threshold",
            {}
        )

    # Verify API call
    assert result is not None
    mock_garmin_client.get_lactate_threshold.assert_called_once_with(latest=True)

    # Verify output structure
    data = json.loads(result[0].text)
    assert data["lactate_threshold_speed_mps"] == 0.32222132
    assert data["lactate_threshold_hr_bpm"] == 169
    assert data["functional_threshold_power_watts"] == 334
    assert data["power_to_weight"] == 4.575


@pytest.mark.asyncio
async def test_get_lactate_threshold_tool_range(app_with_training, mock_garmin_client):
    """Test get_lactate_threshold tool returns lactate threshold data for date range"""
    # Setup mock with date range response format
    lactate_range_data = {
        "start_date": "2024-01-08",
        "end_date": "2024-01-15",
        "measurements": []
    }
    mock_garmin_client.get_lactate_threshold.return_value = lactate_range_data

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.training.get_client", mock_get_client):
        # Call tool with date range
        result = await app_with_training.call_tool(
            "get_lactate_threshold",
            {"start_date": "2024-01-08", "end_date": "2024-01-15"}
        )

    # Verify API call
    assert result is not None
    mock_garmin_client.get_lactate_threshold.assert_called_once_with(
        latest=False,
        start_date="2024-01-08",
        end_date="2024-01-15",
    )


# Error handling tests
@pytest.mark.asyncio
async def test_get_hrv_data_no_data(app_with_training, mock_garmin_client):
    """Test get_hrv_data tool when no data available"""
    # Setup mock to return None
    mock_garmin_client.get_hrv_data.return_value = None

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.training.get_client", mock_get_client):
        # Call tool
        result = await app_with_training.call_tool(
            "get_hrv_data",
            {"date": "2024-01-15"}
        )

    # Verify error message is returned
    assert result is not None


@pytest.mark.asyncio
async def test_get_training_effect_exception(app_with_training, mock_garmin_client):
    """Test get_training_effect tool when API raises exception"""
    # Setup mock to raise exception - get_training_effect uses get_activity internally
    mock_garmin_client.get_activity.side_effect = Exception("API Error")

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.training.get_client", mock_get_client):
        # Call tool
        result = await app_with_training.call_tool(
            "get_training_effect",
            {"activity_id": 12345678901}
        )

    # Verify error is handled gracefully
    assert result is not None
