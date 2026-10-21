"""
Today, in the athlete's time zone.

The server runs in UTC: between midnight and 2 am in Paris, the server's date is
still yesterday's. A command's default day (`health stats` without a date, the
end of a `history` window, `calendar upcoming`) is the athlete's today: the
caller gives the time zone (`/cli` body `timezone`, IANA name).
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from garmin_mcp.api.contract import InvalidInput


def today(timezone: str | None = None) -> date:
    """The athlete's today. Without a time zone: the server's date."""
    if not timezone:
        return date.today()
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise InvalidInput(f"Unknown time zone '{timezone}' (an IANA name: Europe/Paris…)") from e
    return datetime.now(zone).date()
