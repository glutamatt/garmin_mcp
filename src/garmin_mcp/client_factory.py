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
"""

from garminconnect import Garmin
from fastmcp import Context

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


def create_client_from_tokens(
    tokens_b64: str,
    display_name: str | None = None,
    full_name: str | None = None,
) -> Garmin:
    """
    Create Garmin client from base64-encoded garth tokens.

    Args:
        tokens_b64: Base64-encoded garth token string from client.garth.dumps()
        display_name: Garmin displayName from JWT (used in API URLs)
        full_name: Full name from JWT profile

    Returns:
        Authenticated Garmin client instance
    """
    client = Garmin()
    client.garth.loads(tokens_b64)
    if display_name:
        client.display_name = display_name
    if full_name:
        client.full_name = full_name
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
