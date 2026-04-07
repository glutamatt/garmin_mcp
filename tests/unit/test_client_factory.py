"""
Unit tests for client_factory module.

Tests the display_name/full_name propagation from JWT context
to the Garmin client, ensuring zero extra API calls per request.
Also tests DI token detection and the IT refresh patch.
"""
import time

import pytest
from unittest.mock import Mock, patch, MagicMock

from garmin_mcp.client_factory import (
    _get_meta_context,
    _get_session_tokens,
    _is_di_token,
    _patch_di_refresh,
    create_client_from_tokens,
    get_client,
    IT_TOKEN_URL,
    IT_CLIENT_IDS,
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


# ---------------------------------------------------------------------------
# DI token detection
# ---------------------------------------------------------------------------


class TestIsDiToken:
    """_is_di_token detects DI-sourced tokens (empty OAuth1)."""

    def test_empty_oauth_token_is_di(self):
        garth = Mock()
        garth.oauth1_token = Mock(oauth_token="")
        assert _is_di_token(garth) is True

    def test_none_oauth1_token_is_di(self):
        garth = Mock()
        garth.oauth1_token = None
        assert _is_di_token(garth) is True

    def test_missing_oauth_token_attr_is_di(self):
        garth = Mock()
        garth.oauth1_token = Mock(spec=[])  # no oauth_token attribute
        assert _is_di_token(garth) is True

    def test_valid_oauth_token_is_not_di(self):
        garth = Mock()
        garth.oauth1_token = Mock(oauth_token="abc123")
        assert _is_di_token(garth) is False


# ---------------------------------------------------------------------------
# _patch_di_refresh — IT endpoint token refresh
# ---------------------------------------------------------------------------


def _make_oauth2_token(
    access_token="at_old",
    refresh_token="rt_old",
    scope="CONNECT_READ",
    jti="test-jti",
    token_type="Bearer",
):
    """Create a mock OAuth2Token-like object."""
    tok = Mock()
    tok.access_token = access_token
    tok.refresh_token = refresh_token
    tok.scope = scope
    tok.jti = jti
    tok.token_type = token_type
    return tok


class TestPatchDiRefresh:
    """Tests for the IT token refresh mechanism patched onto DI garth clients."""

    def test_replaces_refresh_oauth2_method(self):
        """_patch_di_refresh replaces garth's refresh_oauth2."""
        garth = Mock()
        garth.oauth2_token = _make_oauth2_token()
        original_method = garth.refresh_oauth2

        _patch_di_refresh(garth)

        assert garth.refresh_oauth2 != original_method
        assert callable(garth.refresh_oauth2)

    @patch("garmin_mcp.client_factory._requests.post")
    def test_calls_it_endpoint_with_refresh_token(self, mock_post):
        """Refresh calls IT endpoint with correct params."""
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "access_token": "at_new",
                "refresh_token": "rt_new",
                "expires_in": 3600,
                "refresh_token_expires_in": 7776000,
            }),
        )

        garth = Mock()
        garth.oauth2_token = _make_oauth2_token(refresh_token="rt_original")

        _patch_di_refresh(garth)
        garth.refresh_oauth2()

        # Should call IT endpoint
        call_args = mock_post.call_args
        assert IT_TOKEN_URL in call_args.args[0]
        assert call_args.kwargs["data"]["refresh_token"] == "rt_original"
        assert call_args.kwargs["data"]["client_id"] == IT_CLIENT_IDS[0]

    @patch("garmin_mcp.client_factory._requests.post")
    def test_updates_garth_oauth2_token(self, mock_post):
        """After refresh, garth.oauth2_token is replaced with new token."""
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "access_token": "at_fresh",
                "refresh_token": "rt_fresh",
                "expires_in": 3600,
                "refresh_token_expires_in": 7776000,
            }),
        )

        garth = Mock()
        garth.oauth2_token = _make_oauth2_token()

        _patch_di_refresh(garth)
        garth.refresh_oauth2()

        # oauth2_token should have been reassigned
        new_token = garth.oauth2_token
        assert new_token.access_token == "at_fresh"
        assert new_token.refresh_token == "rt_fresh"
        assert new_token.expires_at > int(time.time())
        assert new_token.refresh_token_expires_at > int(time.time())

    @patch("garmin_mcp.client_factory._requests.post")
    def test_preserves_old_refresh_token_when_not_returned(self, mock_post):
        """When IT response omits refresh_token, old one is preserved."""
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "access_token": "at_new",
                # No refresh_token in response!
                "expires_in": 3600,
                "refresh_token_expires_in": 7776000,
            }),
        )

        garth = Mock()
        garth.oauth2_token = _make_oauth2_token(refresh_token="rt_KEEP_ME")

        _patch_di_refresh(garth)
        garth.refresh_oauth2()

        new_token = garth.oauth2_token
        assert new_token.access_token == "at_new"
        assert new_token.refresh_token == "rt_KEEP_ME"  # preserved

    @patch("garmin_mcp.client_factory._requests.post")
    def test_uses_new_refresh_token_when_returned(self, mock_post):
        """When IT response includes refresh_token, new one is used (rotation)."""
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "access_token": "at_new",
                "refresh_token": "rt_ROTATED",
                "expires_in": 3600,
                "refresh_token_expires_in": 7776000,
            }),
        )

        garth = Mock()
        garth.oauth2_token = _make_oauth2_token(refresh_token="rt_old")

        _patch_di_refresh(garth)
        garth.refresh_oauth2()

        new_token = garth.oauth2_token
        assert new_token.refresh_token == "rt_ROTATED"

    @patch("garmin_mcp.client_factory._requests.post")
    def test_tries_all_client_ids_on_failure(self, mock_post):
        """Falls through to next client_id when one fails."""
        fail_response = Mock(status_code=401)
        ok_response = Mock(
            status_code=200,
            json=Mock(return_value={
                "access_token": "at_ok",
                "expires_in": 3600,
                "refresh_token_expires_in": 7776000,
            }),
        )
        # First two fail, third succeeds
        mock_post.side_effect = [fail_response, fail_response, ok_response]

        garth = Mock()
        garth.oauth2_token = _make_oauth2_token()

        _patch_di_refresh(garth)
        garth.refresh_oauth2()

        assert mock_post.call_count == 3
        # Each call should use a different client_id
        used_ids = [c.kwargs["data"]["client_id"] for c in mock_post.call_args_list]
        assert used_ids == list(IT_CLIENT_IDS)

    @patch("garmin_mcp.client_factory._requests.post")
    def test_raises_when_all_client_ids_fail(self, mock_post):
        """Raises Exception when all IT client IDs fail."""
        mock_post.return_value = Mock(status_code=401)

        garth = Mock()
        garth.oauth2_token = _make_oauth2_token()

        _patch_di_refresh(garth)

        with pytest.raises(Exception, match="IT token refresh failed with all client IDs"):
            garth.refresh_oauth2()

    @patch("garmin_mcp.client_factory._requests.post")
    def test_handles_network_exception_and_tries_next(self, mock_post):
        """Network errors on one client_id don't stop trying the next."""
        import requests
        mock_post.side_effect = [
            requests.ConnectionError("timeout"),
            Mock(
                status_code=200,
                json=Mock(return_value={
                    "access_token": "at_recovered",
                    "expires_in": 3600,
                    "refresh_token_expires_in": 7776000,
                }),
            ),
            # Third not reached
        ]

        garth = Mock()
        garth.oauth2_token = _make_oauth2_token()

        _patch_di_refresh(garth)
        garth.refresh_oauth2()

        new_token = garth.oauth2_token
        assert new_token.access_token == "at_recovered"

    @patch("garmin_mcp.client_factory._requests.post")
    def test_preserves_scope_and_jti_from_old_token(self, mock_post):
        """Fields not in refresh response are preserved from old token."""
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "access_token": "at_new",
                "expires_in": 3600,
                "refresh_token_expires_in": 7776000,
                # No scope, jti, token_type — should be preserved from old token
            }),
        )

        garth = Mock()
        garth.oauth2_token = _make_oauth2_token(
            scope="CONNECT_READ CONNECT_WRITE",
            jti="original-jti",
            token_type="Bearer",
        )

        _patch_di_refresh(garth)
        garth.refresh_oauth2()

        new_token = garth.oauth2_token
        assert new_token.scope == "CONNECT_READ CONNECT_WRITE"
        assert new_token.jti == "original-jti"
        assert new_token.token_type == "Bearer"
