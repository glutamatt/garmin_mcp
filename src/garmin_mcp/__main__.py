"""
Entry point for running garmin_mcp as a module.

Usage:
    python -m garmin_mcp                    # Run with stdio transport
    python -m garmin_mcp --http             # Run with HTTP transport
    python -m garmin_mcp --http --port 8080 # Run HTTP on custom port
"""

import argparse
import os
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

    from garmin_mcp.server import create_app

    app = create_app()

    # Run the MCP server with appropriate transport
    if args.http:
        print(f"Starting Garmin MCP server on http://{args.host}:{args.port}/mcp", file=sys.stderr)
        app.run(transport="http", host=args.host, port=args.port)
    else:
        app.run()


if __name__ == "__main__":
    main()
