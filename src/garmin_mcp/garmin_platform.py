"""
Garmin Connect login functionality.

Provides stateless login that returns tokens to the caller.
"""

from dataclasses import dataclass
from typing import Optional

from garminconnect import Garmin, GarminConnectAuthenticationError
from garth.exc import GarthHTTPError

from garmin_mcp.client_factory import serialize_tokens


@dataclass
class LoginResult:
    """Result of a login attempt."""
    success: bool
    tokens: Optional[str] = None
    display_name: Optional[str] = None
    full_name: Optional[str] = None
    error: Optional[str] = None
    mfa_required: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON response."""
        result = {"success": self.success}
        if self.success:
            result["tokens"] = self.tokens
            result["display_name"] = self.display_name
            result["full_name"] = self.full_name
        else:
            result["error"] = self.error
            if self.mfa_required:
                result["mfa_required"] = True
        return result


def garmin_login(email: str, password: str) -> LoginResult:
    """
    Login to Garmin Connect and return tokens.

    This is a stateless login - tokens are returned to the caller,
    not persisted on the server.

    Args:
        email: Garmin Connect email
        password: Garmin Connect password

    Returns:
        LoginResult with tokens or error
    """
    try:
        client = Garmin(email=email, password=password, is_cn=False)
        client.login()

        tokens = serialize_tokens(client)
        display_name = client.display_name
        full_name = client.get_full_name()

        return LoginResult(
            success=True,
            tokens=tokens,
            display_name=display_name,
            full_name=full_name,
        )

    except GarminConnectAuthenticationError as e:
        error_msg = str(e)
        if "MFA" in error_msg or "code" in error_msg.lower():
            return LoginResult(
                success=False,
                error="MFA required. Please use garmin-mcp-auth CLI first.",
                mfa_required=True,
            )
        return LoginResult(
            success=False,
            error="Invalid email or password",
        )

    except GarthHTTPError as e:
        error_msg = str(e)
        if "429" in error_msg:
            return LoginResult(
                success=False,
                error="Rate limited. Please wait and try again.",
            )
        elif "401" in error_msg or "403" in error_msg:
            return LoginResult(
                success=False,
                error="Invalid credentials",
            )
        return LoginResult(
            success=False,
            error=f"Authentication error: {error_msg.split(':')[0]}",
        )

    except Exception as e:
        return LoginResult(
            success=False,
            error=f"Unexpected error: {str(e)}",
        )
