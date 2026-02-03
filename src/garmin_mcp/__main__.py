"""
Entry point for running garmin_mcp as a module.

Usage:
    python -m garmin_mcp                    # Run with stdio transport
    python -m garmin_mcp --http             # Run with HTTP transport
    python -m garmin_mcp --http --port 9000 # Run HTTP on custom port
"""

import argparse
import os

from garmin_mcp import create_app


def main():
    parser = argparse.ArgumentParser(
        description="Garmin MCP Server - Multi-user session-based Garmin Connect API"
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Use streamable-http transport instead of stdio"
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

    # Set environment variables for the app
    if args.http:
        os.environ["MCP_TRANSPORT"] = "streamable-http"
        os.environ["MCP_HOST"] = args.host
        os.environ["MCP_PORT"] = str(args.port)
    else:
        os.environ["MCP_TRANSPORT"] = "stdio"

    app = create_app()

    if args.http:
        print(f"Starting Garmin MCP server on http://{args.host}:{args.port}/mcp")
        app.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        app.run()


if __name__ == "__main__":
    main()
