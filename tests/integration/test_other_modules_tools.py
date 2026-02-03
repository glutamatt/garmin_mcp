"""
Integration tests for remaining module MCP tools

Tests tools from:
- devices (4 tools)
- weight_management (3 tools)
- user_profile (4 tools)
- data_management (3 tools)
- gear_management (3 tools)
- womens_health (3 tools)
"""
import pytest
from unittest.mock import patch
from mcp.server.fastmcp import FastMCP

from garmin_mcp import (
    devices,
    weight_management,
    user_profile,
    data_management,
    gear_management,
    womens_health
)
from tests.fixtures.garmin_responses import (
    MOCK_DEVICES,
    MOCK_DEVICE_SETTINGS,
    MOCK_DEVICE_LAST_USED,
    MOCK_WEIGH_INS,
    MOCK_USER_PROFILE,
    MOCK_UNIT_SYSTEM,
    MOCK_GEAR,
    MOCK_GEAR_STATS,
    MOCK_MENSTRUAL_DATA,
)


# Devices module tests
@pytest.fixture
def app_with_devices():
    """Create FastMCP app with devices tools registered"""
    app = FastMCP("Test Devices")
    app = devices.register_tools(app)
    return app


@pytest.mark.asyncio
async def test_get_devices_tool(app_with_devices, mock_garmin_client):
    """Test get_devices tool"""
    mock_garmin_client.get_devices.return_value = MOCK_DEVICES

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.devices.get_client", mock_get_client):
        result = await app_with_devices.call_tool("get_devices", {})

    assert result is not None
    mock_garmin_client.get_devices.assert_called_once()


@pytest.mark.asyncio
async def test_get_device_last_used_tool(app_with_devices, mock_garmin_client):
    """Test get_device_last_used tool"""
    last_used = {"deviceId": 123456789, "lastUsed": "2024-01-15"}
    mock_garmin_client.get_device_last_used.return_value = last_used

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.devices.get_client", mock_get_client):
        result = await app_with_devices.call_tool("get_device_last_used", {})

    assert result is not None
    mock_garmin_client.get_device_last_used.assert_called_once()


@pytest.mark.asyncio
async def test_get_device_settings_tool(app_with_devices, mock_garmin_client):
    """Test get_device_settings tool"""
    mock_garmin_client.get_device_settings.return_value = MOCK_DEVICE_SETTINGS

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.devices.get_client", mock_get_client):
        result = await app_with_devices.call_tool(
            "get_device_settings",
            {"device_id": "abc123456789"}
        )

    assert result is not None
    mock_garmin_client.get_device_settings.assert_called_once_with("abc123456789")


@pytest.mark.asyncio
async def test_get_device_alarms_tool(app_with_devices, mock_garmin_client):
    """Test get_device_alarms tool"""
    alarms = [{"alarmTime": 420, "alarmMode": "ON", "alarmDays": ["MONDAY", "FRIDAY"]}]
    mock_garmin_client.get_device_alarms.return_value = alarms

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.devices.get_client", mock_get_client):
        result = await app_with_devices.call_tool(
            "get_device_alarms",
            {}
        )

    assert result is not None
    mock_garmin_client.get_device_alarms.assert_called_once()


# Weight Management module tests
@pytest.fixture
def app_with_weight():
    """Create FastMCP app with weight_management tools registered"""
    app = FastMCP("Test Weight Management")
    app = weight_management.register_tools(app)
    return app


@pytest.mark.asyncio
async def test_get_weigh_ins_tool(app_with_weight, mock_garmin_client):
    """Test get_weigh_ins tool"""
    mock_garmin_client.get_weigh_ins.return_value = MOCK_WEIGH_INS

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.weight_management.get_client", mock_get_client):
        result = await app_with_weight.call_tool(
            "get_weigh_ins",
            {"start_date": "2024-01-08", "end_date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_weigh_ins.assert_called_once_with("2024-01-08", "2024-01-15")


@pytest.mark.asyncio
async def test_delete_weigh_ins_tool(app_with_weight, mock_garmin_client):
    """Test delete_weigh_ins tool"""
    # API returns count of deleted entries
    mock_garmin_client.delete_weigh_ins.return_value = 1

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.weight_management.get_client", mock_get_client):
        result = await app_with_weight.call_tool(
            "delete_weigh_ins",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.delete_weigh_ins.assert_called_once_with("2024-01-15", delete_all=True)


@pytest.mark.asyncio
async def test_add_weigh_in_tool(app_with_weight, mock_garmin_client):
    """Test add_weigh_in tool"""
    add_response = {"status": "success", "weightPk": 12346}
    mock_garmin_client.add_weigh_in.return_value = add_response

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.weight_management.get_client", mock_get_client):
        result = await app_with_weight.call_tool(
            "add_weigh_in",
            {"weight": 70.5, "unit_key": "kg"}
        )

    assert result is not None
    mock_garmin_client.add_weigh_in.assert_called_once_with(weight=70.5, unitKey="kg")


# User Profile module tests
@pytest.fixture
def app_with_user_profile():
    """Create FastMCP app with user_profile tools registered"""
    app = FastMCP("Test User Profile")
    app = user_profile.register_tools(app)
    return app


@pytest.mark.asyncio
async def test_get_full_name_tool(app_with_user_profile, mock_garmin_client):
    """Test get_full_name tool"""
    mock_garmin_client.get_full_name.return_value = "Test User Full Name"

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.user_profile.get_client", mock_get_client):
        result = await app_with_user_profile.call_tool("get_full_name", {})

    assert result is not None
    mock_garmin_client.get_full_name.assert_called_once()


@pytest.mark.asyncio
async def test_get_unit_system_tool(app_with_user_profile, mock_garmin_client):
    """Test get_unit_system tool"""
    mock_garmin_client.get_unit_system.return_value = MOCK_UNIT_SYSTEM

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.user_profile.get_client", mock_get_client):
        result = await app_with_user_profile.call_tool("get_unit_system", {})

    assert result is not None
    mock_garmin_client.get_unit_system.assert_called_once()


@pytest.mark.asyncio
async def test_get_user_profile_tool(app_with_user_profile, mock_garmin_client):
    """Test get_user_profile tool"""
    mock_garmin_client.get_user_profile.return_value = MOCK_USER_PROFILE

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.user_profile.get_client", mock_get_client):
        result = await app_with_user_profile.call_tool("get_user_profile", {})

    assert result is not None
    mock_garmin_client.get_user_profile.assert_called_once()


@pytest.mark.asyncio
async def test_get_userprofile_settings_tool(app_with_user_profile, mock_garmin_client):
    """Test get_userprofile_settings tool"""
    settings = {"emailNotifications": True, "privacySettings": "PUBLIC"}
    mock_garmin_client.get_userprofile_settings.return_value = settings

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.user_profile.get_client", mock_get_client):
        result = await app_with_user_profile.call_tool("get_userprofile_settings", {})

    assert result is not None
    mock_garmin_client.get_userprofile_settings.assert_called_once()


# Data Management module tests
@pytest.fixture
def app_with_data_management():
    """Create FastMCP app with data_management tools registered"""
    app = FastMCP("Test Data Management")
    app = data_management.register_tools(app)
    return app


@pytest.mark.asyncio
async def test_add_body_composition_tool(app_with_data_management, mock_garmin_client):
    """Test add_body_composition tool"""
    add_response = {"status": "success", "message": "Body composition added"}
    mock_garmin_client.add_body_composition.return_value = add_response

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.data_management.get_client", mock_get_client):
        result = await app_with_data_management.call_tool(
            "add_body_composition",
            {"date": "2024-01-15", "weight": 70.0, "percent_fat": 15.0}
        )

    assert result is not None
    mock_garmin_client.add_body_composition.assert_called_once_with(
        "2024-01-15",
        weight=70.0,
        percent_fat=15.0,
        muscle_mass=None,
        bone_mass=None,
        bmi=None
    )


@pytest.mark.asyncio
async def test_set_blood_pressure_tool(app_with_data_management, mock_garmin_client):
    """Test set_blood_pressure tool"""
    add_response = {"status": "success", "message": "Blood pressure added"}
    mock_garmin_client.set_blood_pressure.return_value = add_response

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.data_management.get_client", mock_get_client):
        result = await app_with_data_management.call_tool(
            "set_blood_pressure",
            {"systolic": 120, "diastolic": 80, "pulse": 65}
        )

    assert result is not None
    mock_garmin_client.set_blood_pressure.assert_called_once_with(120, 80, 65, notes=None)


@pytest.mark.asyncio
async def test_add_hydration_data_tool(app_with_data_management, mock_garmin_client):
    """Test add_hydration_data tool"""
    add_response = {"status": "success", "message": "Hydration data added"}
    mock_garmin_client.add_hydration_data.return_value = add_response

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.data_management.get_client", mock_get_client):
        result = await app_with_data_management.call_tool(
            "add_hydration_data",
            {"value_in_ml": 500, "cdate": "2024-01-15", "timestamp": "2024-01-15T10:00:00"}
        )

    assert result is not None
    mock_garmin_client.add_hydration_data.assert_called_once_with(
        value_in_ml=500,
        cdate="2024-01-15",
        timestamp="2024-01-15T10:00:00"
    )


# Gear Management module tests
@pytest.fixture
def app_with_gear():
    """Create FastMCP app with gear_management tools registered"""
    app = FastMCP("Test Gear Management")
    app = gear_management.register_tools(app)
    return app


@pytest.mark.asyncio
async def test_get_gear_tool(app_with_gear, mock_garmin_client):
    """Test get_gear tool - fetches user_profile_id automatically"""
    # Setup mocks for all internal API calls
    mock_garmin_client.get_device_last_used.return_value = MOCK_DEVICE_LAST_USED
    mock_garmin_client.get_gear.return_value = MOCK_GEAR
    mock_garmin_client.get_gear_stats.return_value = MOCK_GEAR_STATS

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.gear_management.get_client", mock_get_client):
        # Call tool without user_profile_id (it's fetched automatically)
        result = await app_with_gear.call_tool("get_gear", {})

    assert result is not None
    # Verify the chain of API calls
    mock_garmin_client.get_device_last_used.assert_called_once()
    mock_garmin_client.get_gear.assert_called_once_with(80653452)  # from MOCK_DEVICE_LAST_USED


@pytest.mark.asyncio
async def test_get_gear_tool_without_stats(app_with_gear, mock_garmin_client):
    """Test get_gear tool with include_stats=False"""
    mock_garmin_client.get_device_last_used.return_value = MOCK_DEVICE_LAST_USED
    mock_garmin_client.get_gear.return_value = MOCK_GEAR

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.gear_management.get_client", mock_get_client):
        # Call with include_stats=False
        result = await app_with_gear.call_tool("get_gear", {"include_stats": False})

    assert result is not None
    # Stats should not be fetched
    mock_garmin_client.get_gear_stats.assert_not_called()


@pytest.mark.asyncio
async def test_add_gear_to_activity_tool(app_with_gear, mock_garmin_client):
    """Test add_gear_to_activity tool"""
    mock_garmin_client.add_gear_to_activity.return_value = {}

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.gear_management.get_client", mock_get_client):
        result = await app_with_gear.call_tool(
            "add_gear_to_activity",
            {"activity_id": 12345678901, "gear_uuid": "abc123"}
        )

    assert result is not None
    mock_garmin_client.add_gear_to_activity.assert_called_once_with(12345678901, "abc123")


@pytest.mark.asyncio
async def test_remove_gear_from_activity_tool(app_with_gear, mock_garmin_client):
    """Test remove_gear_from_activity tool"""
    mock_garmin_client.remove_gear_from_activity.return_value = {}

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.gear_management.get_client", mock_get_client):
        result = await app_with_gear.call_tool(
            "remove_gear_from_activity",
            {"activity_id": 12345678901, "gear_uuid": "abc123"}
        )

    assert result is not None
    mock_garmin_client.remove_gear_from_activity.assert_called_once_with(12345678901, "abc123")


# Women's Health module tests
@pytest.fixture
def app_with_womens_health():
    """Create FastMCP app with womens_health tools registered"""
    app = FastMCP("Test Womens Health")
    app = womens_health.register_tools(app)
    return app


@pytest.mark.asyncio
async def test_get_pregnancy_summary_tool(app_with_womens_health, mock_garmin_client):
    """Test get_pregnancy_summary tool"""
    pregnancy_summary = {"isPregnant": False}
    mock_garmin_client.get_pregnancy_summary.return_value = pregnancy_summary

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.womens_health.get_client", mock_get_client):
        result = await app_with_womens_health.call_tool("get_pregnancy_summary", {})

    assert result is not None
    mock_garmin_client.get_pregnancy_summary.assert_called_once()


@pytest.mark.asyncio
async def test_get_menstrual_data_for_date_tool(app_with_womens_health, mock_garmin_client):
    """Test get_menstrual_data_for_date tool"""
    mock_garmin_client.get_menstrual_data_for_date.return_value = MOCK_MENSTRUAL_DATA

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.womens_health.get_client", mock_get_client):
        result = await app_with_womens_health.call_tool(
            "get_menstrual_data_for_date",
            {"date": "2024-01-15"}
        )

    assert result is not None
    mock_garmin_client.get_menstrual_data_for_date.assert_called_once_with("2024-01-15")


@pytest.mark.asyncio
async def test_get_menstrual_calendar_data_tool(app_with_womens_health, mock_garmin_client):
    """Test get_menstrual_calendar_data tool"""
    calendar_data = [MOCK_MENSTRUAL_DATA]
    mock_garmin_client.get_menstrual_calendar_data.return_value = calendar_data

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.womens_health.get_client", mock_get_client):
        result = await app_with_womens_health.call_tool(
            "get_menstrual_calendar_data",
            {"start_date": "2024-01-01", "end_date": "2024-01-31"}
        )

    assert result is not None
    mock_garmin_client.get_menstrual_calendar_data.assert_called_once_with("2024-01-01", "2024-01-31")
