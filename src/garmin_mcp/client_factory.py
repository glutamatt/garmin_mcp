"""
Client Factory for Garmin MCP Server

Provides session-based client management.
Uses module-level state for token storage (single MCP process per server).

For multi-user support in the future, consider:
- Spawning one MCP process per user
- Passing tokens with each tool call
- Using a proper session store
"""

from garminconnect import Garmin

# Module-level token storage
# Key: some session identifier (for now just "default" since single-user)
_session_tokens: dict[str, str] = {}

DEFAULT_SESSION = "default"


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


def get_client() -> Garmin:
    """
    Get Garmin client from stored session tokens.

    Usage in tools:
        @app.tool()
        def get_stats(date: str) -> str:
            client = get_client()
            return json.dumps(client.get_stats(date))

    Returns:
        Authenticated Garmin client

    Raises:
        ValueError: If no Garmin session is active
    """
    tokens = _session_tokens.get(DEFAULT_SESSION)
    if not tokens:
        raise ValueError(
            "No Garmin session active. Call garmin_login_tool() or set_garmin_session() first."
        )
    return create_client_from_tokens(tokens)


def set_session_tokens(tokens: str) -> None:
    """Store Garmin tokens in session state."""
    _session_tokens[DEFAULT_SESSION] = tokens


def clear_session_tokens() -> None:
    """Clear Garmin tokens from session state."""
    _session_tokens.pop(DEFAULT_SESSION, None)


def has_session() -> bool:
    """Check if a session is active."""
    return DEFAULT_SESSION in _session_tokens
