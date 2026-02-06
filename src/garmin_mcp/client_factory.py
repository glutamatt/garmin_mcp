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
from mcp.server.fastmcp import Context

GARMIN_TOKENS_KEY = "garmin_tokens"


def _get_session_tokens(ctx: Context) -> str | None:
    """
    Get Garmin tokens from request context or session state.

    Tokens can come from two sources (in order of priority):
    1. Request meta (_meta.context.sport_platform_token) - stateless JWT mode
    2. Session state (ctx.get_state) - login tool flow

    Stateless mode:
    - Frontend sends tokens with each request via _meta.context
    - MCP server extracts from ctx.request_context.meta.context
    - No server-side session storage needed

    Login tool mode:
    - Tokens are set via set_session_tokens() after garmin_login
    - Stored in FastMCP Context state (memory-only)

    Args:
        ctx: FastMCP Context (automatically injected by framework)

    Returns:
        Base64-encoded garth tokens string or None if not set
    """
    # Try stateless mode first: extract from request meta
    try:
        if ctx.request_context and ctx.request_context.meta:
            meta_context = ctx.request_context.meta.context
            if meta_context and isinstance(meta_context, dict):
                token = meta_context.get('sport_platform_token')
                if token:
                    return token
    except (AttributeError, TypeError):
        # request_context not available or malformed - fall through to session state
        pass

    # Fallback: read from session state (set by garmin_login tool)
    return ctx.get_state(GARMIN_TOKENS_KEY)


def create_client_from_tokens(tokens_b64: str) -> Garmin:
    """
    Create Garmin client from base64-encoded garth tokens.

    Args:
        tokens_b64: Base64-encoded garth token string from client.garth.dumps()

    Returns:
        Authenticated Garmin client instance
    """
    client = Garmin()
    client.garth.loads(tokens_b64)
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
    return create_client_from_tokens(tokens)


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
