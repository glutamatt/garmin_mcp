"""
End-to-end test for MCP server functionality

This test connects to the actual MCP server and makes real API calls.
It requires valid Garmin credentials in the .env file.

WARNING: These tests may hang if:
- Garmin credentials are invalid
- MFA is required and tokens are expired
- Network connection is unavailable

Run with: pytest tests/e2e/ -m e2e
Or skip with: pytest -m "not e2e"
"""

import pytest
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Import MCP client for testing
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Load environment variables
load_dotenv()


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(30)  # Pytest timeout
async def test_mcp_server_connection():
    """Test MCP server connection and initialization

    WARNING: This test requires:
    - Valid GARMIN_EMAIL and GARMIN_PASSWORD in .env file
    - Active internet connection
    - May require MFA code input if tokens are expired
    """
    # Use python module execution instead of direct script path
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "garmin_mcp"],
        env=None,  # Uses current environment which includes .env variables
    )

    # Connect to server with timeout
    try:
        async with asyncio.timeout(20):  # AsyncIO timeout
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    # Initialize the connection
                    await session.initialize()

                    # List available tools
                    tools = await session.list_tools()

                    # Verify we have tools
                    assert len(tools.tools) > 0, "No tools found in MCP server"

                    # Print available tools for debugging
                    print(f"\nFound {len(tools.tools)} tools:")
                    for tool in tools.tools:
                        print(f"  - {tool.name}: {tool.description}")
    except asyncio.TimeoutError:
        pytest.fail(
            "Server connection timed out after 20 seconds. "
            "Check your Garmin credentials in .env file and network connection. "
            "If MFA is required, run the server manually first to authenticate."
        )

