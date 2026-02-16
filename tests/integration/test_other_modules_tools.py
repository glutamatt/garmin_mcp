"""
Integration tests for remaining module MCP tools

Tests tools from:
- body_data (3 tools: get_weigh_ins, add_weigh_in, delete_weigh_ins)
- gear (3 tools: get_gear, add_gear_to_activity, remove_gear_from_activity)
Total: 6 tools
"""
import json
import pytest
from mcp.server.fastmcp import FastMCP

from garmin_mcp import (
    body_data,
    gear,
)
from tests.fixtures.garmin_responses import (
    MOCK_WEIGH_INS,
    MOCK_GEAR,
)


def _parse(result):
    """Extract JSON from call_tool result."""
    return json.loads(result[0][0].text)


# ── Body Data ────────────────────────────────────────────────────────────────


@pytest.fixture
def app_with_body_data(mock_garmin_client):
    app = FastMCP("Test Body Data")
    app = body_data.register_tools(app)
    return app


@pytest.mark.asyncio
async def test_get_weigh_ins_tool(app_with_body_data, mock_garmin_client):
    mock_garmin_client.get_weigh_ins.return_value = MOCK_WEIGH_INS
    result = await app_with_body_data.call_tool(
        "get_weigh_ins", {"start_date": "2024-01-08", "end_date": "2024-01-15"}
    )
    data = _parse(result)
    assert data["count"] == 1
    mock_garmin_client.get_weigh_ins.assert_called_once_with("2024-01-08", "2024-01-15")


@pytest.mark.asyncio
async def test_get_weigh_ins_no_data(app_with_body_data, mock_garmin_client):
    mock_garmin_client.get_weigh_ins.return_value = None
    result = await app_with_body_data.call_tool(
        "get_weigh_ins", {"start_date": "2024-01-08", "end_date": "2024-01-15"}
    )
    data = _parse(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_add_weigh_in_tool(app_with_body_data, mock_garmin_client):
    mock_garmin_client.add_weigh_in.return_value = {}
    result = await app_with_body_data.call_tool(
        "add_weigh_in", {"weight": 70.5, "unit_key": "kg"}
    )
    data = _parse(result)
    assert data["status"] == "success"
    mock_garmin_client.add_weigh_in.assert_called_once_with(weight=70.5, unitKey="kg")


@pytest.mark.asyncio
async def test_add_weigh_in_with_timestamps(app_with_body_data, mock_garmin_client):
    mock_garmin_client.add_weigh_in_with_timestamps.return_value = {}
    result = await app_with_body_data.call_tool(
        "add_weigh_in",
        {"weight": 70.5, "unit_key": "kg",
         "date_timestamp": "2024-01-15T08:00:00", "gmt_timestamp": "2024-01-15T07:00:00"},
    )
    data = _parse(result)
    assert data["status"] == "success"
    assert data["timestamp_local"] == "2024-01-15T08:00:00"
    mock_garmin_client.add_weigh_in_with_timestamps.assert_called_once()


@pytest.mark.asyncio
async def test_delete_weigh_ins_tool(app_with_body_data, mock_garmin_client):
    mock_garmin_client.delete_weigh_ins.return_value = {}
    result = await app_with_body_data.call_tool(
        "delete_weigh_ins", {"date": "2024-01-15", "delete_all": True}
    )
    data = _parse(result)
    assert data["status"] == "success"
    mock_garmin_client.delete_weigh_ins.assert_called_once_with("2024-01-15", delete_all=True)


# ── Gear ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_with_gear(mock_garmin_client):
    app = FastMCP("Test Gear")
    app = gear.register_tools(app)
    return app


@pytest.mark.asyncio
async def test_get_gear_tool(app_with_gear, mock_garmin_client):
    mock_garmin_client.get_gear.return_value = MOCK_GEAR
    result = await app_with_gear.call_tool("get_gear", {"user_profile_id": "abc123456"})
    data = _parse(result)
    assert data["count"] == 1
    mock_garmin_client.get_gear.assert_called_once_with("abc123456")


@pytest.mark.asyncio
async def test_get_gear_no_data(app_with_gear, mock_garmin_client):
    mock_garmin_client.get_gear.return_value = None
    result = await app_with_gear.call_tool("get_gear", {"user_profile_id": "abc123456"})
    data = _parse(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_add_gear_to_activity_tool(app_with_gear, mock_garmin_client):
    mock_garmin_client.add_gear_to_activity.return_value = {}
    result = await app_with_gear.call_tool(
        "add_gear_to_activity", {"activity_id": 12345678901, "gear_uuid": "abc123"}
    )
    data = _parse(result)
    assert data["status"] == "success"
    mock_garmin_client.add_gear_to_activity.assert_called_once_with("abc123", 12345678901)


@pytest.mark.asyncio
async def test_remove_gear_from_activity_tool(app_with_gear, mock_garmin_client):
    mock_garmin_client.remove_gear_from_activity.return_value = {}
    result = await app_with_gear.call_tool(
        "remove_gear_from_activity", {"activity_id": 12345678901, "gear_uuid": "abc123"}
    )
    data = _parse(result)
    assert data["status"] == "success"
    mock_garmin_client.remove_gear_from_activity.assert_called_once_with("abc123", 12345678901)
