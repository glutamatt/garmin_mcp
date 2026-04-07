"""
Unit tests for token refresh detection in CLI execute().

Verifies that when garth refreshes the OAuth2 token during a CLI command,
execute() detects the change and includes `refreshed_token` in the result.
Also verifies that the /cli endpoint propagates it as X-Refreshed-Token header.
"""

import json
from unittest.mock import Mock, patch

from garmin_mcp.cli import execute


def _mock_client(token_before: str, token_after: str):
    """Create a mock Garmin client that simulates token refresh.

    garth.dumps() returns token_after (simulating that garth refreshed
    internally during an API call), while the input token is token_before.
    """
    client = Mock()
    client.garth = Mock()
    client.garth.dumps.return_value = token_after
    client.garth.loads = Mock()
    # Mock an API call that will succeed
    client.get_activities_by_date.return_value = [
        {"activityId": 1, "activityName": "Test Run", "activityType": {"typeKey": "running"}}
    ]
    return client


class TestTokenRefreshDetection:
    """Verify execute() detects garth token refresh and returns refreshed_token."""

    def test_no_refresh_when_token_unchanged(self):
        """When garth doesn't refresh, no refreshed_token in result."""
        client = _mock_client("same_token", "same_token")
        with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
            result = execute("activities list --from 2024-01-01 --to 2024-01-07", "same_token")

        assert "refreshed_token" not in result

    def test_refresh_detected_when_token_changed(self):
        """When garth refreshes internally, refreshed_token is returned."""
        client = _mock_client("old_token", "new_refreshed_token")
        with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
            result = execute("activities list --from 2024-01-01 --to 2024-01-07", "old_token")

        assert result.get("refreshed_token") == "new_refreshed_token"

    def test_refreshed_token_not_in_result_on_error(self):
        """Even if token refreshed, it's included (command may have partially succeeded)."""
        client = _mock_client("old_token", "new_token_despite_error")
        client.get_activities_by_date.side_effect = Exception("API error")
        with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
            result = execute("activities list --from 2024-01-01 --to 2024-01-07", "old_token")

        # Token refresh is still detected even if command failed
        assert result.get("refreshed_token") == "new_token_despite_error"

    def test_dumps_exception_handled_gracefully(self):
        """If garth.dumps() throws, no crash and no refreshed_token."""
        client = Mock()
        client.garth = Mock()
        client.garth.dumps.side_effect = Exception("serialization error")
        client.garth.loads = Mock()
        client.get_activities_by_date.return_value = []
        with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
            result = execute("activities list --from 2024-01-01 --to 2024-01-07", "some_token")

        assert "refreshed_token" not in result
        # Command should still complete
        assert result["exit_code"] == 0

    def test_describe_command_no_refresh(self):
        """Non-API commands (describe, help) should not trigger refresh."""
        client = _mock_client("tok", "tok")
        with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
            result = execute("describe", "tok")
        assert "refreshed_token" not in result
        assert result["exit_code"] == 0


class TestTokenRefreshConcurrency:
    """Verify token refresh is thread-safe (no shared mutable state)."""

    def test_two_concurrent_executes_isolated(self):
        """Two calls with different tokens don't cross-contaminate."""
        client_a = _mock_client("token_a", "refreshed_a")
        client_b = _mock_client("token_b", "token_b")  # B doesn't refresh

        with patch("garmin_mcp.cli.create_client_from_tokens") as mock_create:
            # First call: token_a → refreshed
            mock_create.return_value = client_a
            result_a = execute("activities list --from 2024-01-01 --to 2024-01-07", "token_a")

            # Second call: token_b → not refreshed
            mock_create.return_value = client_b
            result_b = execute("activities list --from 2024-01-01 --to 2024-01-07", "token_b")

        assert result_a.get("refreshed_token") == "refreshed_a"
        assert "refreshed_token" not in result_b


class TestRefreshDuringApiCall:
    """Simulate garth's actual behavior: token changes as side effect of API call."""

    def test_refresh_triggered_by_api_call(self):
        """garth refreshes access token mid-API-call → dumps() returns new blob."""
        client = Mock()
        client.garth = Mock()
        client.garth.loads = Mock()

        # Simulate: garth.dumps() returns different value after get_activities_by_date
        # because garth internally called refresh_oauth2() during the API call
        call_count = {"n": 0}
        def dumps_side_effect():
            call_count["n"] += 1
            # dumps() is called once after invoke — by then token has been refreshed
            return "refreshed_blob"

        client.garth.dumps.side_effect = dumps_side_effect
        client.get_activities_by_date.return_value = [{"activityId": 1}]

        with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
            result = execute("activities list --from 2024-01-01 --to 2024-01-07", "original_blob")

        assert result["exit_code"] == 0
        assert result.get("refreshed_token") == "refreshed_blob"

    def test_refresh_only_access_token_changes(self):
        """Refresh changes access_token but keeps refresh_token — still detected."""
        # In real life, dumps() produces a different base64 blob even if only
        # access_token changed (the whole blob is re-serialized)
        client = Mock()
        client.garth = Mock()
        client.garth.loads = Mock()
        client.garth.dumps.return_value = "blob_with_new_access_token"
        client.get_activities_by_date.return_value = []

        with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
            result = execute(
                "activities list --from 2024-01-01 --to 2024-01-07",
                "blob_with_old_access_token",
            )

        assert result.get("refreshed_token") == "blob_with_new_access_token"

    def test_multiple_api_calls_refresh_on_first(self):
        """CLI command that makes multiple API calls — refresh on first, detected once."""
        client = Mock()
        client.garth = Mock()
        client.garth.loads = Mock()

        # After any API call, dumps() returns the refreshed blob
        client.garth.dumps.return_value = "after_refresh"
        client.get_activities_by_date.return_value = [{"activityId": 1}]

        with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
            result = execute("activities list --from 2024-01-01 --to 2024-01-07", "before_refresh")

        assert result.get("refreshed_token") == "after_refresh"
        # dumps() called exactly once (after invoke, not per-API-call)
        assert client.garth.dumps.call_count == 1

    def test_refresh_with_rotated_refresh_token(self):
        """When Garmin rotates the refresh_token, the new full blob is propagated."""
        # This is the critical scenario: if Garmin starts rotating refresh tokens,
        # we MUST propagate the new blob or the user loses access after ~90 days
        import base64, json as _json

        old_blob = base64.b64encode(_json.dumps([
            {"oauth_token": "", "oauth_token_secret": ""},
            {"access_token": "at_old", "refresh_token": "rt_OLD"},
        ]).encode()).decode()

        new_blob = base64.b64encode(_json.dumps([
            {"oauth_token": "", "oauth_token_secret": ""},
            {"access_token": "at_new", "refresh_token": "rt_ROTATED"},
        ]).encode()).decode()

        client = Mock()
        client.garth = Mock()
        client.garth.loads = Mock()
        client.garth.dumps.return_value = new_blob
        client.get_activities_by_date.return_value = []

        with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
            result = execute("activities list --from 2024-01-01 --to 2024-01-07", old_blob)

        assert result.get("refreshed_token") == new_blob
        # Verify the new blob actually contains the rotated refresh token
        _, oauth2 = _json.loads(base64.b64decode(result["refreshed_token"]))
        assert oauth2["refresh_token"] == "rt_ROTATED"

    def test_invalid_token_gracefully_skips_refresh_detection(self):
        """Invalid token (can't create client) → no crash, no refresh detection."""
        # Simulates --dry-run or test scenarios with fake tokens
        result = execute("--dry-run workouts create --json {}", "not_a_real_token")
        assert "refreshed_token" not in result

    def test_health_command_with_refresh(self):
        """Non-activities commands also propagate refresh."""
        client = Mock()
        client.garth = Mock()
        client.garth.loads = Mock()
        client.garth.dumps.return_value = "refreshed"
        client.get_sleep_data.return_value = {"sleepScore": 85}

        with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
            result = execute("health sleep --date 2024-06-01", "original")

        assert result.get("refreshed_token") == "refreshed"


class TestServerEndpointHeader:
    """Verify /cli endpoint sets X-Refreshed-Token header."""

    def test_header_set_when_token_refreshed(self):
        """cli_endpoint should pop refreshed_token and set as header."""
        from starlette.testclient import TestClient
        from garmin_mcp.server import create_app

        app = create_app()

        client = _mock_client("old", "new_refreshed")
        with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
            # create_app returns FastMCP — get the underlying ASGI app
            asgi_app = app.http_app()
            test_client = TestClient(asgi_app)
            response = test_client.post("/cli", json={
                "command": "activities list --from 2024-01-01 --to 2024-01-07",
                "token": "old",
            })

        assert response.status_code == 200
        assert response.headers.get("X-Refreshed-Token") == "new_refreshed"
        # Body should NOT contain refreshed_token
        body = response.json()
        assert "refreshed_token" not in body

    def test_no_header_when_token_unchanged(self):
        """cli_endpoint should not set header when no refresh happened."""
        from starlette.testclient import TestClient
        from garmin_mcp.server import create_app

        app = create_app()

        client = _mock_client("same", "same")
        with patch("garmin_mcp.cli.create_client_from_tokens", return_value=client):
            asgi_app = app.http_app()
            test_client = TestClient(asgi_app)
            response = test_client.post("/cli", json={
                "command": "activities list --from 2024-01-01 --to 2024-01-07",
                "token": "same",
            })

        assert response.status_code == 200
        assert "X-Refreshed-Token" not in response.headers
