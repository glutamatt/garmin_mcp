"""
Client Factory for Garmin MCP Server

Provides session-based client management using FastMCP Context.
Each MCP connection has isolated session state via mcp-session-id header.

Multi-user support:
- HTTP transport with mcp-session-id header provides session isolation
- Each user's tokens stored in filesystem-backed session store
- No shared state between connections

Session Persistence:
- FastMCP Context state (ctx._state) doesn't persist across HTTP requests
- Solution: File-based session store using ctx.session_id as key
- Sessions stored in /data/garmin_sessions/{session_id}.json
"""

import os
import json
from pathlib import Path
from fastmcp import Context
from garminconnect import Garmin

GARMIN_TOKENS_KEY = "garmin_tokens"
SESSION_STORE_DIR = Path(os.environ.get("GARMIN_SESSION_DIR", "/data/garmin_sessions"))


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


def _get_session_file_path(session_id: str) -> Path:
    """Get the file path for a session's data."""
    # Ensure session store directory exists
    SESSION_STORE_DIR.mkdir(parents=True, exist_ok=True)
    # Sanitize session_id to prevent path traversal
    safe_session_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return SESSION_STORE_DIR / f"{safe_session_id}.json"


def _load_session_data(session_id: str) -> dict:
    """Load session data from file system."""
    session_file = _get_session_file_path(session_id)
    if not session_file.exists():
        return {}
    try:
        with open(session_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_session_data(session_id: str, data: dict) -> None:
    """Save session data to file system."""
    session_file = _get_session_file_path(session_id)
    try:
        with open(session_file, "w") as f:
            json.dump(data, f)
    except IOError as e:
        # Log error but don't fail - session won't persist but tool will still work
        print(f"Warning: Failed to save session data: {e}")


def _get_session_tokens(ctx: Context) -> str | None:
    """
    Get Garmin tokens from persistent session store.

    First checks in-memory Context state (for performance within same request),
    then falls back to file-based session store for cross-request persistence.
    """
    # First try in-memory state (fast path for same-request calls)
    tokens = ctx.get_state(GARMIN_TOKENS_KEY)
    if tokens:
        return tokens

    # Fall back to persistent session store
    try:
        session_id = ctx.session_id
        session_data = _load_session_data(session_id)
        tokens = session_data.get(GARMIN_TOKENS_KEY)

        # Cache in context state for this request
        if tokens:
            ctx.set_state(GARMIN_TOKENS_KEY, tokens)

        return tokens
    except RuntimeError:
        # session_id not available (not in request context)
        return None


def _set_session_tokens_persistent(ctx: Context, tokens: str) -> None:
    """
    Store Garmin tokens in both in-memory Context and persistent session store.
    """
    # Store in context state (for current request)
    ctx.set_state(GARMIN_TOKENS_KEY, tokens)

    # Store in persistent session store (for future requests)
    try:
        session_id = ctx.session_id
        session_data = _load_session_data(session_id)
        session_data[GARMIN_TOKENS_KEY] = tokens
        _save_session_data(session_id, session_data)
    except RuntimeError:
        # session_id not available (not in request context)
        # Fall back to context state only (non-persistent)
        pass


def _clear_session_tokens_persistent(ctx: Context) -> None:
    """
    Clear Garmin tokens from both in-memory Context and persistent session store.
    """
    # Clear from context state
    ctx.set_state(GARMIN_TOKENS_KEY, None)

    # Clear from persistent session store
    try:
        session_id = ctx.session_id
        session_file = _get_session_file_path(session_id)
        if session_file.exists():
            session_file.unlink()
    except RuntimeError:
        # session_id not available (not in request context)
        pass


def get_client(ctx: Context) -> Garmin:
    """
    Get Garmin client from session Context.

    Automatically loads tokens from persistent session store if not in memory.

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
    Store Garmin tokens in persistent session store.

    Tokens are stored both in-memory (for current request) and on disk
    (for future requests with same session_id).
    """
    _set_session_tokens_persistent(ctx, tokens)


def clear_session_tokens(ctx: Context) -> None:
    """
    Clear Garmin tokens from persistent session store.

    Removes tokens from both in-memory context and disk storage.
    """
    _clear_session_tokens_persistent(ctx)


def has_session(ctx: Context) -> bool:
    """
    Check if a session is active.

    Checks both in-memory context and persistent session store.
    """
    tokens = _get_session_tokens(ctx)
    return tokens is not None
