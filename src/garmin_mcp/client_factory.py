"""
Client Factory

Provides factory functions to create Garmin clients from tokens.
Uses FastMCP Context for session state.
"""

from garminconnect import Garmin
from mcp.server.fastmcp import Context

# Session state key for Garmin tokens
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
        Base64 encoded tokens
    """
    return client.garth.dumps()


async def get_client(ctx: Context) -> Garmin:
    """
    Get Garmin client from MCP Context session state.

    Usage in tools:
        @app.tool()
        async def get_stats(date: str, ctx: Context) -> str:
            client = await get_client(ctx)
            return client.get_stats(date)

    Args:
        ctx: FastMCP Context (automatically injected when declared as parameter)

    Returns:
        Authenticated Garmin client

    Raises:
        ValueError: If no Garmin session is active
    """
    tokens = await ctx.get_state(GARMIN_TOKENS_KEY)
    if not tokens:
        raise ValueError(
            "No Garmin session active. Call garmin_login() or set_garmin_session() first."
        )
    return create_client_from_tokens(tokens)


async def set_session_tokens(ctx: Context, tokens: str) -> None:
    """
    Store Garmin tokens in session state.

    Args:
        ctx: FastMCP Context
        tokens: Base64 encoded Garmin OAuth tokens
    """
    await ctx.set_state(GARMIN_TOKENS_KEY, tokens)


async def clear_session_tokens(ctx: Context) -> None:
    """Clear Garmin tokens from session state."""
    await ctx.delete_state(GARMIN_TOKENS_KEY)
