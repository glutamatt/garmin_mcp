"""
Authentication tool for Garmin MCP server.
Allows login via MCP tool call instead of environment variables.
Stateless: tokens are returned in response for JWT storage, not persisted to disk.

Login flow:
1. Try garmin-connector (residential proxy with Playwright + token caching)
2. Fall back to direct garth login (works with cached tokens, fails for new logins from datacenter IPs)
"""

import logging
import os

import requests
from fastmcp import Context
from garminconnect import Garmin, GarminConnectAuthenticationError
from garth.exc import GarthHTTPError

from garmin_mcp.client_factory import create_client_from_tokens, set_session_tokens

logger = logging.getLogger(__name__)

GARMIN_CONNECTOR_URL = os.environ.get("GARMIN_CONNECTOR_URL", "http://garmin-connector:7860")
# SOCKS5 proxy for Tailscale userspace networking (HF Space → homelab tunnel)
TS_SOCKS_PROXY = os.environ.get("TS_SOCKS_PROXY", "")
_CONNECTOR_PROXIES = (
    {"http": TS_SOCKS_PROXY, "https": TS_SOCKS_PROXY} if TS_SOCKS_PROXY else None
)


def _login_via_connector(email: str, password: str) -> dict | None:
    """
    Try authenticating via garmin-connector (residential proxy).

    Returns login result dict or None if connector is unavailable.
    """
    try:
        r = requests.post(
            f"{GARMIN_CONNECTOR_URL}/auth",
            json={"email": email, "password": password},
            proxies=_CONNECTOR_PROXIES,
            timeout=90,  # Playwright login can take time
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("success") and data.get("tokens"):
                # Resolve display_name from the token
                try:
                    client = create_client_from_tokens(data["tokens"])
                    profile = client.garth.connectapi(
                        "/userprofile-service/socialProfile"
                    )
                    if profile:
                        # displayName is used in Garmin API URL paths — MUST be the raw value,
                        # even when it's a UUID. fullName ("Mathieu Morlon") causes 403.
                        display_name = profile.get("displayName", "")
                        full_name = (
                            profile.get("userProfileFullName")
                            or profile.get("fullName")
                        )
                    else:
                        display_name = None
                        full_name = None
                except Exception:
                    display_name = None
                    full_name = None

                return {
                    "success": True,
                    "message": "Login successful (via garmin-connector)",
                    "display_name": display_name,
                    "full_name": full_name,
                    "tokens": data["tokens"],
                }
        # Connector returned an error — pass it through
        if r.status_code in (401, 400):
            data = r.json()
            return {
                "success": False,
                "error": data.get("error", "Authentication failed"),
                "error_category": data.get("error_category", "unknown_error"),
            }
    except requests.ConnectionError:
        logger.info("garmin-connector not available at %s", GARMIN_CONNECTOR_URL)
        return None
    except Exception as e:
        logger.warning("garmin-connector error: %s", e)
        return None


def login(email: str, password: str, user_id: str = None) -> dict:
    """
    Authenticate with Garmin Connect.

    Tries garmin-connector first (Playwright on residential IP),
    falls back to direct garth login.
    """
    user_id = user_id or email.replace("@", "_at_").replace(".", "_")

    # 1. Try garmin-connector
    connector_result = _login_via_connector(email, password)
    if connector_result is not None:
        if connector_result.get("success"):
            connector_result["user_id"] = user_id
        return connector_result

    # 2. Fall back to direct garth login
    try:
        client = Garmin(email=email, password=password, is_cn=False)
        client.login()

        full_name = client.get_full_name()
        display_name = client.display_name

        return {
            "success": True,
            "message": "Login successful",
            "user_id": user_id,
            "display_name": display_name,
            "full_name": full_name,
            "tokens": client.garth.dumps(),
        }

    except GarminConnectAuthenticationError as e:
        error_msg = str(e)
        if "MFA" in error_msg or "code" in error_msg.lower():
            return {
                "success": False,
                "error": "MFA required",
                "error_category": "mfa_required",
                "mfa_required": True,
                "details": {
                    "message": "Your Garmin account has two-factor authentication (MFA) enabled",
                    "context": "MFA requires interactive authentication which cannot be done through the API",
                    "solution": "Disable MFA on your Garmin account or use an app password if available.",
                },
            }
        return {
            "success": False,
            "error": "Invalid email or password",
            "error_category": "invalid_credentials",
            "details": {
                "message": "The email or password you entered is incorrect",
                "context": "Garmin rejected the login credentials",
                "solution": "Double-check your email and password.",
            },
        }

    except GarthHTTPError as e:
        error_msg = str(e)
        if "429" in error_msg:
            return {
                "success": False,
                "error": "Rate limited",
                "error_category": "rate_limited",
                "details": {
                    "message": "Too many login attempts detected by Garmin",
                    "solution": "Wait 10-15 minutes before trying again",
                },
            }
        elif "403" in error_msg:
            return {
                "success": False,
                "error": "Authentication blocked from this location",
                "error_category": "location_blocked",
                "details": {
                    "message": "Garmin blocks logins from datacenter IPs",
                    "solution": "A garmin-connector on a residential IP is required for new logins.",
                },
            }
        return {
            "success": False,
            "error": f"Authentication error: {error_msg.split(':')[0]}",
            "error_category": "connection_error",
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "error_category": "unknown_error",
        }


def register_tools(app):
    """Register authentication tools with the MCP app."""

    @app.tool()
    def garmin_login(email: str, password: str, ctx: Context = None, user_id: str = None) -> dict:
        """
        Login to Garmin Connect. Validates credentials and returns tokens.

        Args:
            email: Your Garmin Connect email address
            password: Your Garmin Connect password
            ctx: FastMCP Context (automatically injected)
            user_id: Optional custom user ID (defaults to email-based ID)

        Returns:
            Login result with user info or error message
        """
        result = login(email, password, user_id)
        if result.get("success") and ctx and result.get("tokens"):
            set_session_tokens(ctx, result["tokens"])
        return result

    @app.tool()
    def garmin_logout(ctx: Context = None) -> dict:
        """
        Logout from the current Garmin session.

        Returns:
            Logout confirmation
        """
        return {
            "success": True,
            "message": "Logged out",
        }

    return app
