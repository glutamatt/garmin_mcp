"""
Authentication tool for Garmin MCP server.
Allows login via MCP tool call instead of environment variables.
Stateless: tokens are returned in response for JWT storage, not persisted to disk.
"""

from fastmcp import Context
from garminconnect import Garmin, GarminConnectAuthenticationError
from garth.exc import GarthHTTPError

from garmin_mcp.client_factory import set_session_tokens


def login(email: str, password: str, user_id: str = None) -> dict:
    """
    Authenticate with Garmin Connect.

    Args:
        email: Garmin Connect email
        password: Garmin Connect password
        user_id: Optional user ID (defaults to email)

    Returns:
        dict with success status and user info or error
    """
    user_id = user_id or email.replace("@", "_at_").replace(".", "_")

    try:
        client = Garmin(email=email, password=password, is_cn=False)
        client.login()

        # Get user info
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
                    "solution": "MFA requires interactive authentication which cannot be done through the API. Disable MFA on your Garmin account or use an app password if available.",
                },
            }
        return {
            "success": False,
            "error": "Invalid email or password",
            "error_category": "invalid_credentials",
            "details": {
                "message": "The email or password you entered is incorrect",
                "context": "Garmin rejected the login credentials",
                "solution": "Double-check your email and password:\n  • Verify you're using your Garmin Connect email\n  • Check for typos in your password\n  • Try logging in at garmin.com to verify credentials",
                "common_issues": [
                    "Using wrong email (must be Garmin Connect account email)",
                    "Copy-paste adding extra spaces",
                    "Password recently changed but using old password",
                ],
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
                    "context": "Garmin's security system has temporarily blocked login attempts from this location",
                    "solution": "Wait 10-15 minutes before trying again",
                    "prevention": "Avoid rapid repeated login attempts",
                },
            }
        elif "401" in error_msg or "403" in error_msg:
            is_likely_location_block = "403" in error_msg
            if is_likely_location_block:
                return {
                    "success": False,
                    "error": "Authentication blocked: Suspicious location detected",
                    "error_category": "location_blocked",
                    "details": {
                        "message": "Garmin detected login from an unfamiliar or suspicious location and blocked it for security",
                        "context": "HuggingFace Spaces and datacenter IPs are often flagged as suspicious by Garmin's security systems",
                        "solution": "Try logging in from a different network. Datacenter IPs are often blocked by Garmin's security systems.",
                        "why_this_happens": "Garmin blocks logins from datacenter IPs to prevent unauthorized access. This is expected when running on HuggingFace Spaces.",
                    },
                }
            return {
                "success": False,
                "error": "Invalid credentials",
                "error_category": "invalid_credentials",
                "details": {
                    "message": "Authentication failed with HTTP 401/403 error",
                    "context": f"Garmin server returned: {error_msg.split(':')[0]}",
                    "solution": "Verify your credentials at garmin.com and try again",
                },
            }
        return {
            "success": False,
            "error": f"Authentication error: {error_msg.split(':')[0]}",
            "error_category": "connection_error",
            "details": {
                "message": "Network or API communication error",
                "context": f"HTTP error from Garmin: {error_msg.split(':')[0]}",
                "solution": "Check your internet connection and try again. If the problem persists:\n  • Verify Garmin Connect is online at garmin.com\n  • Try again in a few minutes\n  • Check if Garmin is experiencing outages",
            },
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "error_category": "unknown_error",
            "details": {
                "message": "An unexpected error occurred during authentication",
                "context": str(e),
                "solution": "Please try again. If the problem persists, check the error message above for clues.",
            },
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
