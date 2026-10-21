"""
Calendar API — what is on the athlete's calendar: activities, scheduled workouts, races.

Pure functions: (Garmin client, params) → dict. Empty is `{"count": 0, …}`;
failures are exceptions (see `api/contract.py`). Fields: `api/calendar_fields.py`.
"""

from __future__ import annotations

import calendar as _month_days
from datetime import date, timedelta

from garmin_mcp.api.calendar_fields import CALENDAR_ITEMS, EVENT_ITEMS
from garmin_mcp.api.contract import InvalidInput


def _items(client, start: str, end: str) -> list[dict]:
    """The calendar items between two days, curated, by date.

    The month endpoint also gives the days of the next and previous months shown
    in its grid: the SDK keeps the days asked for, and each item once.
    """
    raw = client.get_calendar_items_for_range(start, end) or []
    return sorted((CALENDAR_ITEMS.curate(item) for item in raw), key=lambda item: item.get("date", ""))


def get_month(client, year: int, month: int) -> dict:
    """The calendar of one month (its days only)."""
    if not 1 <= month <= 12:
        raise InvalidInput(f"Month must be 1-12, got {month}")
    first = date(year, month, 1)
    last = first.replace(day=_month_days.monthrange(year, month)[1])
    items = _items(client, first.isoformat(), last.isoformat())
    return {"year": year, "month": month, "count": len(items), "items": items}


def get_upcoming(client, today: str, days: int) -> dict:
    """The calendar from `today` to `today + days`."""
    if days < 0:
        raise InvalidInput(f"--days must be 0 or more, got {days}")
    start = date.fromisoformat(today)
    end = (start + timedelta(days=days)).isoformat()
    items = _items(client, today, end)
    return {"from": today, "to": end, "count": len(items), "items": items}


def get_events(client, start_date: str, end_date: str, limit: int = 20) -> dict:
    """The races between two days (the first `limit`), with the athlete's goal and the race's activity once run."""
    raw = client.connectapi("/calendar-service/events", params={
        "startDate": start_date,
        "endDate": end_date,
        "limit": limit,
        "pageIndex": 1,
        "sortOrder": "eventDate_asc",
    }) or []
    events = [EVENT_ITEMS.curate(event) for event in raw]
    return {"from": start_date, "to": end_date, "count": len(events), "events": events}
