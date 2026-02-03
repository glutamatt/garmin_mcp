"""
Authentication tool for Garmin MCP server.
Allows login via MCP tool call instead of environment variables.
"""

import os
import sys
from pathlib import Path

from garminconnect import Garmin, GarminConnectAuthenticationError
from garth.exc import GarthHTTPError


# Global state for the authenticated client
_garmin_client = None
_current_user_id = None


def get_token_dir(user_id: str) -> Path:
    """Get token directory for a specific user."""
    base_dir = Path(os.environ.get("GARMIN_TOKENS_BASE", "/data/garmin_tokens"))
    return base_dir / user_id


def get_client():
    """Get the current authenticated Garmin client."""
    return _garmin_client


def set_client(client, user_id: str):
    """Set the authenticated Garmin client."""
    global _garmin_client, _current_user_id
    _garmin_client = client
    _current_user_id = user_id


def login(email: str, password: str, user_id: str = None) -> dict:
    """
    Authenticate with Garmin Connect and save tokens.

    Args:
        email: Garmin Connect email
        password: Garmin Connect password
        user_id: Optional user ID for token storage (defaults to email)

    Returns:
        dict with success status and user info or error
    """
    global _garmin_client, _current_user_id

    user_id = user_id or email.replace("@", "_at_").replace(".", "_")
    token_dir = get_token_dir(user_id)

    try:
        # First try to load existing tokens
        if token_dir.exists():
            try:
                client = Garmin()
                client.garth.load(str(token_dir))

                # Verify tokens work by getting user info
                full_name = client.get_full_name()
                display_name = client.display_name

                _garmin_client = client
                _current_user_id = user_id

                return {
                    "success": True,
                    "message": "Logged in with existing tokens",
                    "user_id": user_id,
                    "display_name": display_name,
                    "full_name": full_name,
                }
            except Exception:
                # Tokens invalid, continue to fresh login
                pass

        # Fresh login with credentials
        client = Garmin(email=email, password=password, is_cn=False)
        client.login()

        # Save tokens
        token_dir.mkdir(parents=True, exist_ok=True)
        client.garth.dump(str(token_dir))

        # Get user info
        full_name = client.get_full_name()
        display_name = client.display_name

        _garmin_client = client
        _current_user_id = user_id

        return {
            "success": True,
            "message": "Login successful, tokens saved",
            "user_id": user_id,
            "display_name": display_name,
            "full_name": full_name,
        }

    except GarminConnectAuthenticationError as e:
        error_msg = str(e)
        if "MFA" in error_msg or "code" in error_msg.lower():
            return {
                "success": False,
                "error": "MFA required. Please use garmin-mcp-auth CLI first.",
                "mfa_required": True,
            }
        return {
            "success": False,
            "error": "Invalid email or password",
        }

    except GarthHTTPError as e:
        error_msg = str(e)
        if "429" in error_msg:
            return {
                "success": False,
                "error": "Rate limited. Please wait and try again.",
            }
        elif "401" in error_msg or "403" in error_msg:
            return {
                "success": False,
                "error": "Invalid credentials",
            }
        return {
            "success": False,
            "error": f"Authentication error: {error_msg.split(':')[0]}",
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
        }


def load_user_session(user_id: str) -> dict:
    """
    Load an existing user session from saved tokens.

    Args:
        user_id: User ID to load session for

    Returns:
        dict with success status and user info or error
    """
    global _garmin_client, _current_user_id

    token_dir = get_token_dir(user_id)

    if not token_dir.exists():
        return {
            "success": False,
            "error": "No saved session found. Please login first.",
        }

    try:
        client = Garmin()
        client.garth.load(str(token_dir))

        # Verify tokens work
        full_name = client.get_full_name()
        display_name = client.display_name

        _garmin_client = client
        _current_user_id = user_id

        return {
            "success": True,
            "message": "Session loaded",
            "user_id": user_id,
            "display_name": display_name,
            "full_name": full_name,
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Session expired or invalid: {str(e)}",
        }


def logout() -> dict:
    """Clear the current session."""
    global _garmin_client, _current_user_id

    _garmin_client = None
    _current_user_id = None

    return {
        "success": True,
        "message": "Logged out",
    }


def register_tools(app):
    """Register authentication tools with the MCP app."""

    @app.tool()
    def garmin_login(email: str, password: str, user_id: str = None) -> dict:
        """
        Login to Garmin Connect. Validates credentials and saves tokens for future use.

        Args:
            email: Your Garmin Connect email address
            password: Your Garmin Connect password
            user_id: Optional custom user ID (defaults to email-based ID)

        Returns:
            Login result with user info or error message
        """
        return login(email, password, user_id)

    @app.tool()
    def garmin_load_session(user_id: str) -> dict:
        """
        Load an existing Garmin session from saved tokens.
        Use this to restore a previous login without re-entering credentials.

        Args:
            user_id: The user ID from a previous login

        Returns:
            Session info or error if session expired
        """
        return load_user_session(user_id)

    @app.tool()
    def garmin_logout() -> dict:
        """
        Logout from the current Garmin session.

        Returns:
            Logout confirmation
        """
        return logout()

    return app
