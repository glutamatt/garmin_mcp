"""
Client Factory for Garmin MCP Server

Provides stateless session-based client management using FastMCP Context.
Each MCP connection has isolated session state via mcp-session-id header.

Multi-user support:
- HTTP transport with mcp-session-id header provides session isolation
- Tokens stored in memory (per-request context) only
- Frontend manages token persistence via cookies
- No file storage required

Session Management:
- Tokens passed from frontend on each request via setSession()
- Stored in FastMCP Context state (memory-only, per-request)
- Ephemeral clients created from tokens in request context
"""

from fastmcp import Context
from garminconnect import Garmin

GARMIN_TOKENS_KEY = "garmin_tokens"


def create_client_from_tokens(tokens: str) -> Garmin:
    """
    Create a Garmin client from base64 tokens.

    Populates display_name from garth profile after loading tokens.
    This is required for API calls that use display_name in the URL.

    Args:
        tokens: Base64 encoded Garmin OAuth tokens

    Returns:
        Authenticated Garmin client with display_name populated
    """
    client = Garmin()
    client.garth.loads(tokens)

    # Populate display_name from garth profile after loading tokens
    # This mimics the behavior in the login flow
    try:
        profile = client.garth.profile
        if profile and isinstance(profile, dict):
            client.display_name = profile.get("displayName")
            client.full_name = profile.get("fullName")
        elif not client.display_name:
            # Fallback: fetch profile via API if not available in garth.profile
            prof = client.garth.connectapi("/userprofile-service/userprofile/profile")
            if prof and isinstance(prof, dict):
                client.display_name = prof.get("displayName")
                client.full_name = prof.get("fullName")
    except Exception as e:
        # Log but don't fail - some operations might not need display_name
        print(f"Warning: Failed to populate display_name: {e}")

    return client


def serialize_tokens(client: Garmin) -> str:
    """
    Serialize Garmin client tokens to base64 string.

    Args:
        client: Authenticated Garmin client

    Returns:
        Base64 encoded tokens (~2KB)
    """
    return client.garth.dumps()


def _get_session_tokens(ctx: Context) -> str | None:
    """
    Get Garmin tokens from request context (memory-only).

    Tokens are passed from frontend on each request via setSession().
    No file-based persistence - frontend manages token lifecycle via cookies.

    Args:
        ctx: FastMCP Context (automatically injected by framework)

    Returns:
        Base64 encoded tokens or None if not set
    """
    return ctx.get_state(GARMIN_TOKENS_KEY)


def _set_session_tokens(ctx: Context, tokens: str) -> None:
    """
    Store Garmin tokens in request context (memory-only).

    Tokens are stored for the duration of the request only.
    Frontend is responsible for persisting tokens across requests.

    Args:
        ctx: FastMCP Context
        tokens: Base64 encoded Garmin OAuth tokens
    """
    ctx.set_state(GARMIN_TOKENS_KEY, tokens)


def _clear_session_tokens(ctx: Context) -> None:
    """
    Clear Garmin tokens from request context (memory-only).

    This only clears the in-memory state. Frontend must also clear
    its stored tokens (cookies) for complete logout.

    Args:
        ctx: FastMCP Context
    """
    ctx.set_state(GARMIN_TOKENS_KEY, None)


def get_client(ctx: Context) -> Garmin:
    """
    Get Garmin client from session Context (memory-only).

    Tokens must be set via set_garmin_session() before calling tools.
    Frontend passes tokens on each request - no file-based persistence.

    Usage in tools:
        @app.tool()
        async def get_stats(date: str, ctx: Context) -> str:
            client = get_client(ctx)
            return json.dumps(client.get_stats(date))

    Args:
        ctx: FastMCP Context (automatically injected by framework)

    Returns:
        Authenticated Garmin client

    Raises:
        ValueError: If no Garmin session is active
    """
    tokens = _get_session_tokens(ctx)
    if not tokens:
        raise ValueError(
            "No Garmin session active. Call garmin_login_tool() or set_garmin_session() first."
        )
    return create_client_from_tokens(tokens)


def set_session_tokens(ctx: Context, tokens: str) -> None:
    """
    Store Garmin tokens in request context (memory-only).

    This only stores tokens for the current request. Frontend is responsible
    for persisting tokens across requests (typically via cookies).

    Args:
        ctx: FastMCP Context
        tokens: Base64 encoded Garmin OAuth tokens
    """
    _set_session_tokens(ctx, tokens)


def clear_session_tokens(ctx: Context) -> None:
    """
    Clear Garmin tokens from request context (memory-only).

    Frontend must also clear its stored tokens for complete logout.

    Args:
        ctx: FastMCP Context
    """
    _clear_session_tokens(ctx)


def has_session(ctx: Context) -> bool:
    """
    Check if a session is active (memory-only).

    Returns True if tokens are set in the current request context.

    Args:
        ctx: FastMCP Context

    Returns:
        True if session has tokens, False otherwise
    """
    tokens = _get_session_tokens(ctx)
    return tokens is not None
