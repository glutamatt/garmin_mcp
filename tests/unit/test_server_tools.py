"""MCP tools of the production server (fastmcp, in-memory client).

The model reaches Garmin only through the /cli endpoint. The MCP layer keeps
the tools the frontend calls at login and logout: garmin_login, garmin_logout.
"""

import asyncio

from fastmcp import Client

from garmin_mcp.server import create_app


def _run(coro):
    return asyncio.run(coro)


async def _list_tool_names() -> set[str]:
    async with Client(create_app()) as client:
        return {tool.name for tool in await client.list_tools()}


def test_mcp_tools_are_login_only():
    """No MCP tool reads a Garmin token: the model goes through /cli (token in the body)."""
    assert _run(_list_tool_names()) == {"garmin_login", "garmin_logout"}
