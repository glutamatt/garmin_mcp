"""MCP tools of the production server (fastmcp, in-memory client).

The model reaches Garmin only through the /cli endpoint. The MCP layer keeps
the tools the frontend calls at login: garmin_login, garmin_logout and
get_device_capabilities.
"""

import asyncio
import json
from unittest.mock import Mock, patch

from fastmcp import Client

from garmin_mcp.server import create_app


def _run(coro):
    return asyncio.run(coro)


async def _list_tool_names() -> set[str]:
    async with Client(create_app()) as client:
        return {tool.name for tool in await client.list_tools()}


async def _call(name: str, args: dict) -> str:
    async with Client(create_app()) as client:
        result = await client.call_tool(name, args)
        return result.content[0].text


def test_mcp_tools_are_login_only():
    assert _run(_list_tool_names()) == {
        "garmin_login",
        "garmin_logout",
        "get_device_capabilities",
    }


def test_get_device_capabilities_through_mcp():
    garmin = Mock()
    garmin.get_usage_indicators.return_value = {
        "deviceBasedIndicators": {"hasHrvStatusCapableDevice": False},
    }
    with patch("garmin_mcp.capabilities_tool.get_client", return_value=garmin):
        out = json.loads(_run(_call("get_device_capabilities", {})))

    assert out["capabilities"]["hasHrvStatusCapableDevice"] is False
    assert out["disabled_tools"] == ["get_hrv_data"]
