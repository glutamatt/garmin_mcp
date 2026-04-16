"""
Shared MCP server factory — single source of truth for app creation.

Used by both __main__.py (module entry) and __init__.py (main()).
Registers all MCP tools + the /cli HTTP endpoint.
"""

import json
import os
import sys

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse


def create_app() -> FastMCP:
    """Create and configure the Garmin MCP server with all tools and endpoints."""

    print("Garmin MCP v2: 3-layer architecture, per-request token loading.", file=sys.stderr)

    # Ensure CLI sandbox directory exists
    os.makedirs("/tmp/garmin", exist_ok=True)

    # Create the MCP app
    app = FastMCP("Garmin Connect v2.0")

    # Register all MCP tools (3-layer architecture)
    from garmin_mcp import (
        health, activities, training,
        workouts, profile,
        gear, body_data,
        calendar, auth_tool,
    )
    app = auth_tool.register_tools(app)
    app = health.register_tools(app)
    app = activities.register_tools(app)
    app = training.register_tools(app)
    app = workouts.register_tools(app)
    app = profile.register_tools(app)
    app = gear.register_tools(app)
    app = body_data.register_tools(app)
    app = calendar.register_tools(app)

    # ── CLI endpoint ─────────────────────────────────────────────────────
    # Direct HTTP endpoint bypassing MCP JSON-RPC.
    # Accepts: { command: string, token: string, display_name?: string }
    # Returns: { stdout: string, stderr: string, exit_code: int }

    @app.custom_route("/cli", methods=["POST"])
    async def cli_endpoint(request: Request) -> JSONResponse:
        from garmin_mcp.cli import execute

        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return JSONResponse(
                {"stdout": "", "stderr": "Invalid JSON body", "exit_code": 2},
                status_code=400,
            )

        command = body.get("command", "")
        token = body.get("token", "")
        display_name = body.get("display_name")
        tmp_dir = body.get("tmp_dir")

        if not token:
            return JSONResponse(
                {"stdout": "", "stderr": "Missing token", "exit_code": 2},
                status_code=401,
            )

        result = execute(command, token, display_name, tmp_dir)
        refreshed_token = result.pop("refreshed_token", None)
        response = JSONResponse(result)
        if refreshed_token:
            response.headers["X-Refreshed-Token"] = refreshed_token
        return response

    return app
