"""
Entry point for running garmin_mcp as a module.

Usage:
    python -m garmin_mcp                    # Run with stdio transport
    python -m garmin_mcp --http             # Run with HTTP transport
    python -m garmin_mcp --http --port 8080 # Run HTTP on custom port
"""

import argparse
import sys

def main():
    parser = argparse.ArgumentParser(
        description="Garmin Connect MCP Server - Multi-user session-based Garmin Connect API"
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Use http transport instead of stdio"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for HTTP transport (default: 8080)"
    )

    args = parser.parse_args()

    # Import the module's main function and create the app
    import os
    from garminconnect import Garmin, GarminConnectAuthenticationError
    from garth.exc import GarthHTTPError
    from fastmcp import FastMCP
    from garmin_mcp import (
        activity_management, health_wellness, user_profile, devices,
        gear_management, weight_management, challenges, training,
        workouts, data_management, womens_health, auth_tool,
        init_api_from_env, DynamicGarminClient
    )

    # Initialize garmin client (from init_api_from_env in __init__.py)
    garmin_client = init_api_from_env()

    if garmin_client:
        print("Garmin Connect client initialized from environment.", file=sys.stderr)
        auth_tool.set_client(garmin_client, "env_user")

        # Configure modules with static client
        activity_management.configure(garmin_client)
        health_wellness.configure(garmin_client)
        user_profile.configure(garmin_client)
        devices.configure(garmin_client)
        gear_management.configure(garmin_client)
        weight_management.configure(garmin_client)
        challenges.configure(garmin_client)
        training.configure(garmin_client)
        workouts.configure(garmin_client)
        data_management.configure(garmin_client)
        womens_health.configure(garmin_client)
    else:
        print(
            "No pre-configured credentials. Use garmin_login tool to authenticate.",
            file=sys.stderr,
        )

        # Configure modules with dynamic proxy client
        dynamic_client = DynamicGarminClient()
        activity_management.configure(dynamic_client)
        health_wellness.configure(dynamic_client)
        user_profile.configure(dynamic_client)
        devices.configure(dynamic_client)
        gear_management.configure(dynamic_client)
        weight_management.configure(dynamic_client)
        challenges.configure(dynamic_client)
        training.configure(dynamic_client)
        workouts.configure(dynamic_client)
        data_management.configure(dynamic_client)
        womens_health.configure(dynamic_client)

    # Create the MCP app
    app = FastMCP("Garmin Connect v1.0")

    # Register all tools
    app = auth_tool.register_tools(app)
    app = activity_management.register_tools(app)
    app = health_wellness.register_tools(app)
    app = user_profile.register_tools(app)
    app = devices.register_tools(app)
    app = gear_management.register_tools(app)
    app = weight_management.register_tools(app)
    app = challenges.register_tools(app)
    app = training.register_tools(app)
    app = workouts.register_tools(app)
    app = data_management.register_tools(app)
    app = womens_health.register_tools(app)

    # Run the MCP server with appropriate transport
    if args.http:
        print(f"Starting Garmin MCP server on http://{args.host}:{args.port}/mcp", file=sys.stderr)
        app.run(transport="http", host=args.host, port=args.port)
    else:
        app.run()


if __name__ == "__main__":
    main()
