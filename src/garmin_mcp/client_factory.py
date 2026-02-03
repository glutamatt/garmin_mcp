"""
Client Factory for Garmin MCP Server

Provides session-based client management using FastMCP Context.
Each MCP connection has isolated session state via mcp-session-id header.

Multi-user support:
- HTTP transport with mcp-session-id header provides session isolation
- Each user's tokens stored in their Context state
- No shared state between connections
"""

from fastmcp import Context
from garminconnect import Garmin

GARMIN_TOKENS_KEY = "garmin_tokens"


def create_client_from_tokens(tokens: str) -> Garmin:
    """
    Create a Garmin client from base64 tokens.

    Args:
        tokens: Base64 encoded Garmin OAuth tokens

    Returns:
        Authenticated Garmin client
    """
    client = Garmin()
    client.garth.loads(tokens)
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


async def get_client(ctx: Context) -> Garmin:
    """
    Get Garmin client from session Context.

    Usage in tools:
        @app.tool()
        async def get_stats(date: str, ctx: Context) -> str:
            client = await get_client(ctx)
            return json.dumps(client.get_stats(date))

    Args:
        ctx: FastMCP Context (automatically injected by framework)

    Returns:
        Authenticated Garmin client

    Raises:
        ValueError: If no Garmin session is active
    """
    tokens = await ctx.get_state(GARMIN_TOKENS_KEY)
    if not tokens:
        raise ValueError(
            "No Garmin session active. Call garmin_login_tool() or set_garmin_session() first."
        )
    return create_client_from_tokens(tokens)


async def set_session_tokens(ctx: Context, tokens: str) -> None:
    """Store Garmin tokens in session Context."""
    await ctx.set_state(GARMIN_TOKENS_KEY, tokens)


async def clear_session_tokens(ctx: Context) -> None:
    """Clear Garmin tokens from session Context."""
    await ctx.delete_state(GARMIN_TOKENS_KEY)


async def has_session(ctx: Context) -> bool:
    """Check if a session is active."""
    tokens = await ctx.get_state(GARMIN_TOKENS_KEY)
    return tokens is not None
