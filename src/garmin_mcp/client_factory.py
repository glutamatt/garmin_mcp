"""
Client factory for Garmin MCP server.
Stateless per-request client creation from JWT tokens.

Provides stateless session-based client management using FastMCP Context.
Each MCP request has isolated state via request context.

Multi-user support:
- HTTP transport with stateless JWT provides session isolation
- Tokens passed from frontend on each request via _meta.context
- Ephemeral clients created from base64-encoded garth tokens
- No file storage required

Session Management:
- Tokens passed from frontend on each request via _meta.context.sport_platform_token
- Fallback to FastMCP Context state (for garmin_login tool flow)
- Ephemeral Garmin clients created from tokens per-request

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
from fastmcp import Context
from garth.auth_tokens import OAuth2Token
from garth.http import Client as GarthClient

logger = logging.getLogger(__name__)

GARMIN_TOKENS_KEY = "garmin_tokens"


def _get_meta_context(ctx: Context) -> dict | None:
    """Extract _meta.context dict from request context, or None."""
    try:
        if ctx.request_context and ctx.request_context.meta:
            meta_context = ctx.request_context.meta.context
            if meta_context and isinstance(meta_context, dict):
                return meta_context
    except (AttributeError, TypeError):
        pass
    return None


def _get_session_tokens(ctx: Context) -> str | None:
    """
    Get Garmin tokens from request context or session state.

    Tokens can come from two sources (in order of priority):
    1. Request meta (_meta.context.sport_platform_token) - stateless JWT mode
    2. Session state (ctx.get_state) - login tool flow

    Args:
        ctx: FastMCP Context (automatically injected by framework)

    Returns:
        Base64-encoded garth tokens string or None if not set
    """
    meta_context = _get_meta_context(ctx)
    if meta_context:
        token = meta_context.get('sport_platform_token')
        if token:
            return token

    # Fallback: read from session state (set by garmin_login tool)
    return ctx.get_state(GARMIN_TOKENS_KEY)


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
    """
    client = Garmin()
    client.garth.loads(tokens_b64)

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


def get_client(ctx: Context) -> Garmin:
    """
    Get authenticated Garmin client from request context.

    Creates an ephemeral client from tokens found in the request context
    or session state. No server-side persistence.

    Usage in tools:
        @app.tool()
        async def get_activities(ctx: Context) -> str:
            client = get_client(ctx)
            return json.dumps(client.get_activities_by_date(...))

    Args:
        ctx: FastMCP Context (automatically injected by framework)

    Returns:
        Authenticated Garmin client instance

    Raises:
        ValueError: If no tokens are available
    """
    tokens = _get_session_tokens(ctx)
    if not tokens:
        raise ValueError("Not authenticated. Please login via Garmin Connect first.")

    # Extract profile data from JWT context (avoids extra API call per request)
    meta_context = _get_meta_context(ctx)
    display_name = meta_context.get('display_name') if meta_context else None
    full_name = meta_context.get('full_name') if meta_context else None

    return create_client_from_tokens(tokens, display_name, full_name)


def set_session_tokens(ctx: Context, tokens: str):
    """
    Store tokens in session state (used by garmin_login tool).

    This only stores tokens for the current session. Frontend is responsible
    for persisting tokens across requests (typically via JWT).

    Args:
        ctx: FastMCP Context
        tokens: Base64-encoded garth token string from client.garth.dumps()
    """
    ctx.set_state(GARMIN_TOKENS_KEY, tokens)
