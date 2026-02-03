"""
Integration tests for challenges module MCP tools

Tests all challenges and badges tools using FastMCP integration with mocked Garmin API responses.
"""
import pytest
from unittest.mock import patch
from mcp.server.fastmcp import FastMCP

from garmin_mcp import challenges
from tests.fixtures.garmin_responses import (
    MOCK_GOALS,
    MOCK_PERSONAL_RECORD,
    MOCK_BADGES,
)


@pytest.fixture
def app_with_challenges():
    """Create FastMCP app with challenges tools registered"""
    app = FastMCP("Test Challenges")
    app = challenges.register_tools(app)
    return app


@pytest.mark.asyncio
async def test_get_goals_active(app_with_challenges, mock_garmin_client):
    """Test get_goals tool returns active goals"""
    # Setup mock
    mock_garmin_client.get_goals.return_value = MOCK_GOALS

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.challenges.get_client", mock_get_client):
        # Call tool
        result = await app_with_challenges.call_tool(
            "get_goals",
            {"goal_type": "active"}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_goals.assert_called_once_with("active")


@pytest.mark.asyncio
async def test_get_goals_default(app_with_challenges, mock_garmin_client):
    """Test get_goals tool with default parameter (active)"""
    # Setup mock
    mock_garmin_client.get_goals.return_value = MOCK_GOALS

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.challenges.get_client", mock_get_client):
        # Call tool without goal_type (should default to "active")
        result = await app_with_challenges.call_tool(
            "get_goals",
            {}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_goals.assert_called_once_with("active")


@pytest.mark.asyncio
async def test_get_goals_future(app_with_challenges, mock_garmin_client):
    """Test get_goals tool returns future goals"""
    # Setup mock
    future_goals = {"goals": [{"goalType": "STEPS", "goalValue": 10000, "startDate": "2024-02-01"}]}
    mock_garmin_client.get_goals.return_value = future_goals

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.challenges.get_client", mock_get_client):
        # Call tool
        result = await app_with_challenges.call_tool(
            "get_goals",
            {"goal_type": "future"}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_goals.assert_called_once_with("future")


@pytest.mark.asyncio
async def test_get_personal_record_tool(app_with_challenges, mock_garmin_client):
    """Test get_personal_record tool returns personal records"""
    # Setup mock
    mock_garmin_client.get_personal_record.return_value = MOCK_PERSONAL_RECORD

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.challenges.get_client", mock_get_client):
        # Call tool
        result = await app_with_challenges.call_tool(
            "get_personal_record",
            {}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_personal_record.assert_called_once()


@pytest.mark.asyncio
async def test_get_earned_badges_tool(app_with_challenges, mock_garmin_client):
    """Test get_earned_badges tool returns earned badges"""
    # Setup mock
    mock_garmin_client.get_earned_badges.return_value = MOCK_BADGES

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.challenges.get_client", mock_get_client):
        # Call tool
        result = await app_with_challenges.call_tool(
            "get_earned_badges",
            {}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_earned_badges.assert_called_once()


@pytest.mark.asyncio
async def test_get_adhoc_challenges_default(app_with_challenges, mock_garmin_client):
    """Test get_adhoc_challenges tool with default parameters"""
    # Setup mock
    adhoc_challenges = [
        {
            "socialChallengeStatusId": 2,
            "socialChallengeActivityTypeId": 4,
            "adHocChallengeName": "January Step Challenge",
            "adHocChallengeDesc": "Steps Challenge",
            "uuid": "ABC123",
            "startDate": "2024-01-01T00:00:00.0",
            "endDate": "2024-01-31T23:59:59.0",
            "userRanking": 1,
            "playerCount": 5,
        }
    ]
    mock_garmin_client.get_adhoc_challenges.return_value = adhoc_challenges

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.challenges.get_client", mock_get_client):
        # Call tool
        result = await app_with_challenges.call_tool(
            "get_adhoc_challenges",
            {}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_adhoc_challenges.assert_called_once_with(0, 20)


@pytest.mark.asyncio
async def test_get_adhoc_challenges_custom_params(app_with_challenges, mock_garmin_client):
    """Test get_adhoc_challenges tool with custom parameters"""
    # Setup mock
    mock_garmin_client.get_adhoc_challenges.return_value = []

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.challenges.get_client", mock_get_client):
        # Call tool
        result = await app_with_challenges.call_tool(
            "get_adhoc_challenges",
            {"start": 10, "limit": 50}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_adhoc_challenges.assert_called_once_with(10, 50)


@pytest.mark.asyncio
async def test_get_badge_challenges_tool(app_with_challenges, mock_garmin_client):
    """Test get_badge_challenges tool"""
    # Setup mock
    badge_challenges = [MOCK_BADGES[0]]
    mock_garmin_client.get_badge_challenges.return_value = badge_challenges

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.challenges.get_client", mock_get_client):
        # Call tool
        result = await app_with_challenges.call_tool(
            "get_badge_challenges",
            {"start": 1, "limit": 50}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_badge_challenges.assert_called_once_with(1, 50)


@pytest.mark.asyncio
async def test_get_race_predictions_tool(app_with_challenges, mock_garmin_client):
    """Test get_race_predictions tool"""
    # Setup mock
    race_predictions = {
        "calendarDate": "2024-01-15",
        "time5K": 1200,
        "time10K": 2520,
        "timeHalfMarathon": 5400,
        "timeMarathon": 11400,
    }
    mock_garmin_client.get_race_predictions.return_value = race_predictions

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.challenges.get_client", mock_get_client):
        # Call tool
        result = await app_with_challenges.call_tool(
            "get_race_predictions",
            {}
        )

    # Verify
    assert result is not None
    mock_garmin_client.get_race_predictions.assert_called_once()


# Error handling tests
@pytest.mark.asyncio
async def test_get_goals_no_data(app_with_challenges, mock_garmin_client):
    """Test get_goals tool when no goals found"""
    # Setup mock to return None
    mock_garmin_client.get_goals.return_value = None

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.challenges.get_client", mock_get_client):
        # Call tool
        result = await app_with_challenges.call_tool(
            "get_goals",
            {"goal_type": "active"}
        )

    # Verify error message is returned
    assert result is not None
    # Should indicate no goals found


@pytest.mark.asyncio
async def test_get_personal_record_exception(app_with_challenges, mock_garmin_client):
    """Test get_personal_record tool when API raises exception"""
    # Setup mock to raise exception
    mock_garmin_client.get_personal_record.side_effect = Exception("API Error")

    async def mock_get_client(ctx):
        return mock_garmin_client

    with patch("garmin_mcp.challenges.get_client", mock_get_client):
        # Call tool
        result = await app_with_challenges.call_tool(
            "get_personal_record",
            {}
        )

    # Verify error is handled gracefully
    assert result is not None
    # Should return error message, not crash
