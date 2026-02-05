"""
Modular MCP Server for Garmin Connect Data

Supports two modes:
1. Pre-authenticated: Set GARMIN_EMAIL/GARMIN_PASSWORD env vars
2. Dynamic auth: Use garmin_login tool to authenticate at runtime
"""

import os
import sys

import requests
from fastmcp import FastMCP

from garth.exc import GarthHTTPError
from garminconnect import Garmin, GarminConnectAuthenticationError

# Import all modules
from garmin_mcp import activity_management
from garmin_mcp import health_wellness
from garmin_mcp import user_profile
from garmin_mcp import devices
from garmin_mcp import gear_management
from garmin_mcp import weight_management
from garmin_mcp import challenges
from garmin_mcp import training
from garmin_mcp import workouts
from garmin_mcp import data_management
from garmin_mcp import womens_health
from garmin_mcp import auth_tool


def is_interactive_terminal() -> bool:
    """Detect if running in interactive terminal vs MCP subprocess."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def get_mfa() -> str:
    """Get MFA code from user input."""
    if not is_interactive_terminal():
        print(
            "\nERROR: MFA code required but no interactive terminal available.\n"
            "Please run 'garmin-mcp-auth' in your terminal first.\n",
            file=sys.stderr,
        )
        raise RuntimeError("MFA required but non-interactive environment")

    print(
        "\nGarmin Connect MFA required. Please check your email/phone for the code.",
        file=sys.stderr,
    )
    return input("Enter MFA code: ")


def get_credentials_from_env():
    """Get credentials from environment variables if available."""
    email = os.environ.get("GARMIN_EMAIL")
    email_file = os.environ.get("GARMIN_EMAIL_FILE")
    if email and email_file:
        raise ValueError(
            "Must only provide one of GARMIN_EMAIL and GARMIN_EMAIL_FILE, got both"
        )
    elif email_file:
        with open(email_file, "r") as f:
            email = f.read().rstrip()

    password = os.environ.get("GARMIN_PASSWORD")
    password_file = os.environ.get("GARMIN_PASSWORD_FILE")
    if password and password_file:
        raise ValueError(
            "Must only provide one of GARMIN_PASSWORD and GARMIN_PASSWORD_FILE, got both"
        )
    elif password_file:
        with open(password_file, "r") as f:
            password = f.read().rstrip()

    return email, password


def init_api_from_env():
    """Initialize Garmin API from environment variables (legacy mode)."""
    import io

    email, password = get_credentials_from_env()
    tokenstore = os.getenv("GARMINTOKENS") or "~/.garminconnect"

    try:
        print(
            f"Trying to login using token data from '{tokenstore}'...\n",
            file=sys.stderr,
        )

        old_stderr = sys.stderr
        sys.stderr = io.StringIO()

        try:
            garmin = Garmin()
            garmin.login(tokenstore)
        finally:
            sys.stderr = old_stderr

        return garmin

    except (FileNotFoundError, GarthHTTPError, GarminConnectAuthenticationError):
        if not is_interactive_terminal() and (not email or not password):
            # No credentials and non-interactive - that's OK in dynamic mode
            return None

        if not email or not password:
            return None

        print(
            "Login tokens not present, logging in with credentials...\n",
            file=sys.stderr,
        )
        try:
            garmin = Garmin(
                email=email, password=password, is_cn=False, prompt_mfa=get_mfa
            )
            garmin.login()
            garmin.garth.dump(tokenstore)
            print(f"Tokens stored in '{tokenstore}'.\n", file=sys.stderr)
            return garmin
        except Exception as err:
            print(f"Authentication failed: {err}", file=sys.stderr)
            return None


class DynamicGarminClient:
    """Proxy that delegates to the authenticated client from auth_tool."""

    def __getattr__(self, name):
        client = auth_tool.get_client()
        if client is None:
            raise RuntimeError(
                "Not authenticated. Please call garmin_login tool first."
            )
        return getattr(client, name)


def main():
    """Initialize the MCP server and register all tools"""

    # Try to initialize from environment (legacy mode)
    garmin_client = init_api_from_env()

    if garmin_client:
        print("Garmin Connect client initialized from environment.", file=sys.stderr)
        # Set the client in auth_tool for consistency
        auth_tool.set_client(garmin_client, "env_user")

        # Configure all modules with the static client
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

    # Register auth tools (always available)
    app = auth_tool.register_tools(app)

    # Register data tools
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

    # Run the MCP server
    app.run()


if __name__ == "__main__":
    main()
