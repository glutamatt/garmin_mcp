"""
Unit tests for client_factory module.

Tests the display_name/full_name propagation from JWT context
to the Garmin client, ensuring zero extra API calls per request.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from garmin_mcp.client_factory import (
    _get_meta_context,
    _get_session_tokens,
    create_client_from_tokens,
    get_client,
)


def _make_ctx(meta_context: dict | None = None, state: dict | None = None):
    """Create a mock FastMCP Context with optional meta context and state."""
    ctx = Mock()
    if meta_context is not None:
        ctx.request_context = Mock()
        ctx.request_context.meta = Mock()
        ctx.request_context.meta.context = meta_context
    else:
        ctx.request_context = None

    state = state or {}
    ctx.get_state = Mock(side_effect=lambda key: state.get(key))
    return ctx


class TestGetMetaContext:
    def test_returns_context_dict(self):
        meta = {"sport_platform_token": "tok", "display_name": "user1"}
        ctx = _make_ctx(meta_context=meta)
        assert _get_meta_context(ctx) == meta

    def test_returns_none_when_no_request_context(self):
        ctx = _make_ctx(meta_context=None)
        assert _get_meta_context(ctx) is None

    def test_returns_none_when_meta_context_is_not_dict(self):
        ctx = Mock()
        ctx.request_context = Mock()
        ctx.request_context.meta = Mock()
        ctx.request_context.meta.context = "not a dict"
        assert _get_meta_context(ctx) is None

    def test_returns_none_when_meta_context_is_empty(self):
        ctx = _make_ctx(meta_context={})
        assert _get_meta_context(ctx) is None


class TestGetSessionTokens:
    def test_prefers_meta_context_token(self):
        ctx = _make_ctx(
            meta_context={"sport_platform_token": "jwt_token"},
            state={"garmin_tokens": "state_token"},
        )
        assert _get_session_tokens(ctx) == "jwt_token"

    def test_falls_back_to_state(self):
        ctx = _make_ctx(
            meta_context=None,
            state={"garmin_tokens": "state_token"},
        )
        assert _get_session_tokens(ctx) == "state_token"

    def test_returns_none_when_no_tokens(self):
        ctx = _make_ctx(meta_context=None, state={})
        assert _get_session_tokens(ctx) is None


class TestCreateClientFromTokens:
    @patch("garmin_mcp.client_factory.Garmin")
    def test_sets_display_name_and_full_name(self, MockGarmin):
        client = Mock()
        client.display_name = None
        client.full_name = None
        MockGarmin.return_value = client

        result = create_client_from_tokens("fake_b64", "TestUser", "Test Full Name")

        assert result.display_name == "TestUser"
        assert result.full_name == "Test Full Name"

    @patch("garmin_mcp.client_factory.Garmin")
    def test_no_display_name_leaves_none(self, MockGarmin):
        client = Mock()
        client.display_name = None
        client.full_name = None
        MockGarmin.return_value = client

        result = create_client_from_tokens("fake_b64")

        # display_name/full_name not set when not provided
        assert result.display_name is None
        assert result.full_name is None

    @patch("garmin_mcp.client_factory.Garmin")
    def test_loads_garth_tokens(self, MockGarmin):
        client = Mock()
        MockGarmin.return_value = client

        create_client_from_tokens("fake_b64_tokens", "user", "name")

        client.garth.loads.assert_called_once_with("fake_b64_tokens")


class TestGetClient:
    @patch("garmin_mcp.client_factory.create_client_from_tokens")
    def test_passes_display_name_from_context(self, mock_create):
        mock_create.return_value = Mock()
        ctx = _make_ctx(meta_context={
            "sport_platform_token": "tok123",
            "display_name": "GarminUser",
            "full_name": "Jean Dupont",
        })

        get_client(ctx)

        mock_create.assert_called_once_with("tok123", "GarminUser", "Jean Dupont")

    @patch("garmin_mcp.client_factory.create_client_from_tokens")
    def test_passes_none_when_no_profile_in_context(self, mock_create):
        mock_create.return_value = Mock()
        ctx = _make_ctx(meta_context={
            "sport_platform_token": "tok123",
        })

        get_client(ctx)

        mock_create.assert_called_once_with("tok123", None, None)

    def test_raises_when_no_tokens(self):
        ctx = _make_ctx(meta_context=None, state={})

        with pytest.raises(ValueError, match="Not authenticated"):
            get_client(ctx)

    @patch("garmin_mcp.client_factory.create_client_from_tokens")
    def test_fallback_session_state_no_profile(self, mock_create):
        """When using session state (login flow), no display_name in context."""
        mock_create.return_value = Mock()
        ctx = _make_ctx(
            meta_context=None,
            state={"garmin_tokens": "state_tok"},
        )

        get_client(ctx)

        mock_create.assert_called_once_with("state_tok", None, None)
