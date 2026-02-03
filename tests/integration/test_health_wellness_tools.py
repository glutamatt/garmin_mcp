"""
Integration tests for health_wellness module MCP tools

Tests health and wellness tools using FastMCP integration with mocked Garmin API responses.
"""
import pytest
from unittest.mock import patch, AsyncMock
from mcp.server.fastmcp import FastMCP

from garmin_mcp import health_wellness
from tests.fixtures.garmin_responses import (
    MOCK_STATS,
    MOCK_USER_SUMMARY,
    MOCK_BODY_COMPOSITION,
    MOCK_STEPS_DATA,
    MOCK_DAILY_STEPS,
    MOCK_TRAINING_READINESS,
    MOCK_BODY_BATTERY,
    MOCK_BODY_BATTERY_EVENTS,
    MOCK_BLOOD_PRESSURE,
    MOCK_FLOORS,
    MOCK_RHR_DAY,
    MOCK_HEART_RATES,
    MOCK_HYDRATION_DATA,
    MOCK_SLEEP_DATA,
    MOCK_STRESS_DATA,
    MOCK_RESPIRATION_DATA,
    MOCK_SPO2_DATA,
    MOCK_WEEKLY_STEPS,
    MOCK_WEEKLY_STRESS,
    MOCK_WEEKLY_INTENSITY_MINUTES,
    MOCK_MORNING_TRAINING_READINESS,
)


@pytest.fixture
def app_with_health_wellness():
    """Create FastMCP app with health_wellness tools registered"""
    app = FastMCP("Test Health Wellness")
    app = health_wellness.register_tools(app)
    return app


@pytest.mark.asyncio
async def test_get_stats_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_stats tool returns daily activity stats"""
    mock_garmin_client.get_stats.return_value = MOCK_STATS

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_stats",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_stats.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_user_summary_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_user_summary tool returns user summary data"""
    mock_garmin_client.get_user_summary.return_value = MOCK_USER_SUMMARY

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_user_summary",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_user_summary.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_body_composition_single_date(app_with_health_wellness, mock_garmin_client):
    """Test get_body_composition tool with single date"""
    mock_garmin_client.get_body_composition.return_value = MOCK_BODY_COMPOSITION

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_body_composition",
            {"start_date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_body_composition.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_body_composition_date_range(app_with_health_wellness, mock_garmin_client):
    """Test get_body_composition tool with date range"""
    mock_garmin_client.get_body_composition.return_value = MOCK_BODY_COMPOSITION

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_body_composition",
            {"start_date": "2024-01-01", "end_date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_body_composition.assert_called_once_with("2024-01-01", "2024-01-15")


@pytest.mark.asyncio
async def test_get_stats_and_body_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_stats_and_body tool"""
    mock_garmin_client.get_stats_and_body.return_value = {"stats": {}, "body": {}}

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_stats_and_body",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_stats_and_body.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_steps_data_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_steps_data tool"""
    mock_garmin_client.get_steps_data.return_value = MOCK_STEPS_DATA

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_steps_data",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_steps_data.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_daily_steps_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_daily_steps tool"""
    mock_garmin_client.get_daily_steps.return_value = MOCK_DAILY_STEPS

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_daily_steps",
            {"start_date": "2024-01-01", "end_date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_daily_steps.assert_called_once_with("2024-01-01", "2024-01-15")


@pytest.mark.asyncio
async def test_get_training_readiness_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_training_readiness tool"""
    mock_garmin_client.get_training_readiness.return_value = MOCK_TRAINING_READINESS

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_training_readiness",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_training_readiness.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_body_battery_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_body_battery tool"""
    mock_garmin_client.get_body_battery.return_value = MOCK_BODY_BATTERY

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_body_battery",
            {"start_date": "2024-01-01", "end_date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_body_battery.assert_called_once_with("2024-01-01", "2024-01-15")


@pytest.mark.asyncio
async def test_get_sleep_data_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_sleep_data tool"""
    mock_garmin_client.get_sleep_data.return_value = MOCK_SLEEP_DATA

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_sleep_data",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_sleep_data.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_sleep_summary_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_sleep_summary tool"""
    mock_garmin_client.get_sleep_data.return_value = MOCK_SLEEP_DATA

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_sleep_summary",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_sleep_data.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_stress_data_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_stress_data tool"""
    mock_garmin_client.get_stress_data.return_value = MOCK_STRESS_DATA

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_stress_data",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_stress_data.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_stress_summary_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_stress_summary tool"""
    mock_garmin_client.get_stress_data.return_value = MOCK_STRESS_DATA

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_stress_summary",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_stress_data.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_heart_rates_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_heart_rates tool"""
    mock_garmin_client.get_heart_rates.return_value = MOCK_HEART_RATES

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_heart_rates",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_heart_rates.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_hrv_data_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_hrv_data tool"""
    mock_garmin_client.get_hrv_data.return_value = {
        "hrvSummary": {
            "calendarDate": "2024-01-15",
            "lastNightAvg": 45,
            "weeklyAvg": 50,
            "status": "BALANCED",
            "baseline": {"balancedLow": 35, "balancedUpper": 55}
        }
    }

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_hrv_data",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_hrv_data.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_respiration_data_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_respiration_data tool"""
    mock_garmin_client.get_respiration_data.return_value = MOCK_RESPIRATION_DATA

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_respiration_data",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_respiration_data.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_spo2_data_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_spo2_data tool"""
    mock_garmin_client.get_spo2_data.return_value = MOCK_SPO2_DATA

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_spo2_data",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_spo2_data.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_hydration_data_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_hydration_data tool"""
    mock_garmin_client.get_hydration_data.return_value = MOCK_HYDRATION_DATA

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_hydration_data",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_hydration_data.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_floors_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_floors tool"""
    mock_garmin_client.get_floors.return_value = MOCK_FLOORS

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_floors",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_floors.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_blood_pressure_tool(app_with_health_wellness, mock_garmin_client):
    """Test get_blood_pressure tool"""
    mock_garmin_client.get_blood_pressure.return_value = MOCK_BLOOD_PRESSURE

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_blood_pressure",
            {"start_date": "2024-01-01", "end_date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_blood_pressure.assert_called_once_with("2024-01-01", "2024-01-15")


@pytest.mark.asyncio
async def test_get_steps_data_no_data(app_with_health_wellness, mock_garmin_client):
    """Test get_steps_data returns proper message when no data"""
    mock_garmin_client.get_steps_data.return_value = None

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_steps_data",
            {"date": "2024-01-15"}
        )

    assert "No steps data found" in str(result)


@pytest.mark.asyncio
async def test_get_sleep_data_exception(app_with_health_wellness, mock_garmin_client):
    """Test get_sleep_data handles exceptions properly"""
    mock_garmin_client.get_sleep_data.side_effect = Exception("API error")

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.health_wellness.get_client", mock_get_client):
        result = await app_with_health_wellness.call_tool(
            "get_sleep_data",
            {"date": "2024-01-15"}
        )

    assert "Error" in str(result)
