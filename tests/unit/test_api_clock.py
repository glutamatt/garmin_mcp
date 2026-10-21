"""Today in the athlete's time zone (audit C7: the server runs in UTC)."""

from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from garmin_mcp.api import clock
from garmin_mcp.api.contract import InvalidInput
from garmin_mcp.cli import execute


class _Now(datetime):
    """00:30 in Paris on 2026-10-21 = 22:30 UTC on 2026-10-20."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 20, 22, 30, tzinfo=timezone.utc).astimezone(tz)


def test_paris_after_midnight_is_already_the_next_day():
    with patch.object(clock, "datetime", _Now):
        assert clock.today("Europe/Paris") == date(2026, 10, 21)
        assert clock.today("UTC") == date(2026, 10, 20)


def test_without_a_time_zone_the_server_date():
    assert clock.today(None) == date.today()


def test_unknown_time_zone_is_invalid_input():
    with pytest.raises(InvalidInput):
        clock.today("Mars/Olympus")


def test_cli_default_day_uses_the_time_zone():
    """`health stats` without a date asks Garmin for the athlete's today."""
    from unittest.mock import Mock

    garmin = Mock()
    garmin.get_user_summary.return_value = None
    with patch.object(clock, "datetime", _Now), \
            patch("garmin_mcp.cli.create_client_from_tokens", return_value=garmin):
        execute("health stats", "token", timezone="Europe/Paris")
    garmin.get_user_summary.assert_called_once_with("2026-10-21")


def test_cli_unknown_time_zone_is_exit_2():
    result = execute("health stats", "token", timezone="Mars/Olympus")
    assert result["exit_code"] == 2
    assert "Unknown time zone" in result["stderr"]
