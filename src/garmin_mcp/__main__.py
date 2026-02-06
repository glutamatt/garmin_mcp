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

    from fastmcp import FastMCP
    from garmin_mcp import (
        activity_management, health_wellness, user_profile, devices,
        gear_management, weight_management, challenges, training,
        workouts, data_management, womens_health, auth_tool,
    )

    # All tools use per-request token loading via client_factory.get_client(ctx)
    print("Garmin MCP: stateless mode - per-request token loading from JWT.", file=sys.stderr)

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
