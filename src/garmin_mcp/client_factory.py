"""
Client factory for Garmin: one ephemeral client per request, from a garth token.

The token comes with each `/cli` request (from the user's JWT). Nothing is stored
on the server. No MCP tool reads a token: the MCP layer is login / logout only.

Token types:
- garth OAuth1+OAuth2: traditional flow (garth SSO → OAuth1 → OAuth2). Refresh via OAuth1 exchange.
- DI/IT OAuth2: garmin-connector flow (web SSO → DI → IT). OAuth1 fields are empty.
  Refresh via IT endpoint (services.garmin.com/api/oauth/token?grant_type=refresh_token).
  Detected by empty oauth_token in OAuth1.
"""

import base64
import logging
import time

import requests as _requests
from garminconnect import Garmin
from garth.auth_tokens import OAuth2Token
from garth.http import Client as GarthClient

logger = logging.getLogger(__name__)

UNREADABLE_TOKEN_MESSAGE = (
    "Garmin is not available in this session: the Garmin login token is unreadable "
    "(missing, expired or corrupted). Every Garmin command will fail the same way until "
    "the athlete reconnects Garmin — do not retry, answer without Garmin data."
)


class GarminTokenError(ValueError):
    """The sport_platform_token cannot be decoded into garth tokens."""


DI_TOKEN_URL = "https://diauth.garmin.com/di-oauth2-service/oauth/token"
DI_CLIENT_IDS = (
    "GARMIN_CONNECT_MOBILE_ANDROID_DI_2025Q2",
    "GARMIN_CONNECT_MOBILE_ANDROID_DI_2024Q4",
    "GARMIN_CONNECT_MOBILE_ANDROID_DI",
)
DI_HEADERS = {
    "User-Agent": "GCM-Android-5.23",
    "X-Garmin-Client-Platform": "Android",
    "X-App-Ver": "10861",
    "X-Lang": "en",
    "Content-Type": "application/x-www-form-urlencoded",
}


def _basic_auth(client_id: str) -> str:
    """Garmin DI endpoint requires Basic auth with client_id and empty secret."""
    return "Basic " + base64.b64encode(f"{client_id}:".encode()).decode()


def _is_di_token(garth_client: GarthClient) -> bool:
    """Check if tokens are from the DI flow (empty OAuth1)."""
    oauth1 = garth_client.oauth1_token
    return not oauth1 or not getattr(oauth1, "oauth_token", None)


def _patch_di_refresh(garth_client: GarthClient):
    """
    Replace garth's OAuth1-based refresh with DI token refresh.

    DI-sourced tokens have empty OAuth1 fields, so garth's default
    refresh_oauth2() would fail with AssertionError. This patches it
    to use the DI refresh endpoint (diauth.garmin.com) instead.

    Note: Garmin rotates the refresh token on every use — the caller
    MUST propagate the updated garth.dumps() back to the client.
    """

    def _refresh():
        old_token = garth_client.oauth2_token
        for client_id in DI_CLIENT_IDS:
            try:
                r = _requests.post(
                    DI_TOKEN_URL,
                    headers={
                        **DI_HEADERS,
                        "Authorization": _basic_auth(client_id),
                    },
                    data={
                        "grant_type": "refresh_token",
                        "client_id": client_id,
                        "refresh_token": old_token.refresh_token,
                    },
                    timeout=15,
                )
                if r.status_code == 200:
                    token = r.json()
                    # Preserve fields that might not be in refresh response
                    token.setdefault("scope", old_token.scope)
                    token.setdefault("jti", old_token.jti)
                    token.setdefault("token_type", old_token.token_type)
                    token.setdefault("refresh_token", old_token.refresh_token)
                    now = int(time.time())
                    token["expires_at"] = now + int(token.get("expires_in", 3600))
                    token["refresh_token_expires_at"] = now + int(
                        token.get("refresh_token_expires_in", 7776000)
                    )
                    garth_client.oauth2_token = OAuth2Token(**token)
                    logger.info("DI token refreshed via %s", client_id)
                    return
                else:
                    body = r.text[:200] if r.text else ""
                    logger.warning(
                        "DI refresh %s returned %d: %s", client_id, r.status_code, body
                    )
            except Exception as e:
                logger.warning("DI refresh failed with %s: %s", client_id, e)
        raise Exception("DI token refresh failed with all client IDs")

    garth_client.refresh_oauth2 = _refresh


def create_client_from_tokens(
    tokens_b64: str,
    display_name: str | None = None,
    full_name: str | None = None,
) -> Garmin:
    """
    Create Garmin client from base64-encoded garth tokens.

    Supports both traditional garth tokens (OAuth1+OAuth2) and
    DI/IT tokens from garmin-connector (empty OAuth1, IT OAuth2).

    Args:
        tokens_b64: Base64-encoded garth token string from client.garth.dumps()
        display_name: Garmin displayName from JWT (used in API URLs)
        full_name: Full name from JWT profile

    Returns:
        Authenticated Garmin client instance

    Raises:
        GarminTokenError: If the token cannot be decoded (clear message for the model)
    """
    client = Garmin()
    try:
        client.garth.loads(tokens_b64)
    except (ValueError, TypeError, KeyError, IndexError) as e:
        # Bad base64 / not UTF-8 / not JSON / wrong shape. The raw error
        # ("'utf-8' codec can't decode byte 0xeb…") tells the model nothing useful,
        # and CLI logs reach the model through stderr: the cause stays on __cause__ only.
        raise GarminTokenError(UNREADABLE_TOKEN_MESSAGE) from e

    # DI-sourced tokens: patch refresh to use IT endpoint instead of OAuth1
    if _is_di_token(client.garth):
        _patch_di_refresh(client.garth)

    if display_name:
        client.display_name = display_name
    if full_name:
        client.full_name = full_name

    # If display_name is missing, resolve from garth profile (no API call).
    # Many SDK endpoints use display_name in URL paths — without it they 403.
    if not getattr(client, "display_name", None):
        profile = getattr(client.garth, "profile", None)
        if profile and isinstance(profile, dict):
            client.display_name = profile.get("displayName")
            client.full_name = client.full_name or profile.get("fullName")

    return client
