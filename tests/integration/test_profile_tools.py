"""
Integration tests for profile module MCP tools (v2 — 4 tools).

Tests the thin tool wrappers via FastMCP call_tool with mocked Garmin client.
"""
import json
import pytest
from mcp.server.fastmcp import FastMCP

from garmin_mcp import profile


def _parse(result):
    """Extract JSON from call_tool result tuple: (content_list, is_error)."""
    return json.loads(result[0][0].text)


@pytest.fixture
def app(mock_garmin_client):
    """Create FastMCP app with profile tools registered."""
    a = FastMCP("Test Profile")
    a = profile.register_tools(a)
    return a


@pytest.mark.asyncio
async def test_get_full_name(app, mock_garmin_client):
    mock_garmin_client.get_full_name.return_value = "Jean Dupont"

    result = await app.call_tool("get_full_name", {})
    # get_full_name returns a plain string, not JSON
    text = result[0][0].text
    assert text == "Jean Dupont"


@pytest.mark.asyncio
async def test_get_user_profile(app, mock_garmin_client):
    mock_garmin_client.get_user_profile.return_value = {
        "displayName": "Jean Dupont",
        "location": "Paris",
    }
    mock_garmin_client.get_userprofile_settings.return_value = {
        "userData": {"weight": 75000}
    }
    mock_garmin_client.get_unit_system.return_value = "metric"

    result = await app.call_tool("get_user_profile", {})
    data = _parse(result)

    assert data["display_name"] == "Jean Dupont"
    assert data["unit_system"] == "metric"


@pytest.mark.asyncio
async def test_get_user_profile_no_data(app, mock_garmin_client):
    mock_garmin_client.get_user_profile.return_value = None

    result = await app.call_tool("get_user_profile", {})
    data = _parse(result)

    assert "error" in data


@pytest.mark.asyncio
async def test_get_devices(app, mock_garmin_client):
    mock_garmin_client.get_devices.return_value = [
        {"deviceId": 1, "displayName": "Forerunner 965", "deviceStatusName": "ACTIVE"},
    ]
    mock_garmin_client.get_device_last_used.return_value = {"deviceId": 1}
    mock_garmin_client.get_primary_training_device.return_value = {"deviceId": 1}

    result = await app.call_tool("get_devices", {})
    data = _parse(result)

    assert data["count"] == 1
    assert data["devices"][0]["is_last_used"] is True


@pytest.mark.asyncio
async def test_get_devices_no_data(app, mock_garmin_client):
    mock_garmin_client.get_devices.return_value = None

    result = await app.call_tool("get_devices", {})
    data = _parse(result)

    assert "error" in data


# ── get_device_capabilities ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_device_capabilities(app, mock_garmin_client):
    mock_garmin_client.get_usage_indicators.return_value = {
        "deviceBasedIndicators": {
            "hasHrvStatusCapableDevice": True,
            "hasBodyBatteryCapableDevice": False,
        }
    }

    result = await app.call_tool("get_device_capabilities", {})
    data = _parse(result)

    assert "capabilities" in data
    assert "disabled_tools" in data
    assert "get_body_battery" in data["disabled_tools"]
    assert data["capabilities"]["hasHrvStatusCapableDevice"] is True


@pytest.mark.asyncio
async def test_get_device_capabilities_api_failure(app, mock_garmin_client):
    mock_garmin_client.get_usage_indicators.side_effect = Exception("Network error")

    result = await app.call_tool("get_device_capabilities", {})
    data = _parse(result)

    # Fail-open: no disabled tools
    assert data["disabled_tools"] == []
    assert data["capabilities"] == {}
