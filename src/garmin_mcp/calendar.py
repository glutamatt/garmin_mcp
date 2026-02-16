"""
Calendar and race event tools for Garmin Connect MCP Server.

Exposes the athlete's race calendar, competitions, and scheduled events.
Enables the coach to plan training around target race dates.
"""
import json

from fastmcp import Context
from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all calendar/event tools with the MCP server app"""

    @app.tool()
    async def get_upcoming_race_events(
        num_days_forward: int, limit: int, ctx: Context
    ) -> str:
        """Get upcoming race events and competitions from the athlete's Garmin calendar.

        Returns scheduled events like races, marathons, triathlons, etc.
        Use this to understand the athlete's competition calendar and plan training accordingly.

        Args:
            num_days_forward: How many days ahead to look (e.g. 365 for a full year)
            limit: Maximum number of events to return (e.g. 10)
        """
        try:
            client = get_client(ctx)
            events = client.get_upcoming_calendar_events(
                num_days_forward=num_days_forward, limit=limit
            )
            if not events:
                return "No upcoming race events found."

            return json.dumps(_curate_events_response(events), indent=2)
        except Exception as e:
            return f"Error retrieving upcoming race events: {str(e)}"

    @app.tool()
    async def get_race_events(
        start_date: str, end_date: str, limit: int, ctx: Context
    ) -> str:
        """Get race events and competitions within a date range.

        Returns both past and future events depending on the date range.
        Use start_date in the past and end_date=today for past race history.
        Use start_date=today and end_date in the future for upcoming races.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            limit: Maximum number of events to return (e.g. 20)
        """
        try:
            client = get_client(ctx)
            # Use garth.connectapi directly to support endDate param
            url = "/calendar-service/events"
            params = {
                "startDate": start_date,
                "endDate": end_date,
                "limit": limit,
                "pageIndex": 1,
                "sortOrder": "eventDate_asc",
            }
            events = client.garth.connectapi(url, params=params)
            if not events:
                return f"No race events found between {start_date} and {end_date}."

            return json.dumps(_curate_events_response(events), indent=2)
        except Exception as e:
            return f"Error retrieving race events: {str(e)}"

    @app.tool()
    async def get_calendar_month_overview(
        year: int, month: int, ctx: Context
    ) -> str:
        """Get a complete overview of all calendar items for a specific month.

        Returns activities, workouts, training plan items, race events, and rest days.
        Useful for reviewing the athlete's training month at a glance.

        Args:
            year: Year (e.g. 2026)
            month: Month number 1-12 (e.g. 2 for February)
        """
        try:
            client = get_client(ctx)
            month_data = client.get_calendar_month(year, month)
            if not month_data:
                return f"No calendar data found for {year}-{month:02d}."

            curated = {
                "year": year,
                "month": month,
                "items": [],
            }

            for item in month_data.get("calendarItems", []):
                curated_item = {
                    "date": item.get("date"),
                    "type": item.get("itemType"),
                    "title": item.get("title"),
                }

                # Add type-specific fields
                if item.get("activityTypeId"):
                    curated_item["activity_type_id"] = item.get("activityTypeId")
                if item.get("distance"):
                    curated_item["distance_meters"] = item.get("distance")
                if item.get("duration"):
                    curated_item["duration_seconds"] = item.get("duration")
                if item.get("eventType"):
                    curated_item["event_type"] = item.get("eventType")

                # Remove None values
                curated_item = {k: v for k, v in curated_item.items() if v is not None}
                curated["items"].append(curated_item)

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error retrieving calendar month overview: {str(e)}"

    return app


def _curate_events_response(events_data) -> list | dict:
    """Curate events API response to essential fields only."""
    # The API can return a list or a dict with an events key
    events_list = events_data
    if isinstance(events_data, dict):
        events_list = events_data.get("events", events_data.get("items", [events_data]))

    if not isinstance(events_list, list):
        return events_data

    curated = []
    for event in events_list:
        # Prefer uuid (needed for /shareable detail endpoint), fall back to numeric id
        curated_event = {
            "event_id": event.get("uuid") or event.get("id"),
            "name": event.get("eventName") or event.get("name") or event.get("title"),
            "date": event.get("eventDate") or event.get("date"),
            "event_type": event.get("eventType") or event.get("sportType"),
        }

        # Distance/course info
        if event.get("distance"):
            curated_event["distance_meters"] = event.get("distance")
        if event.get("courseName"):
            curated_event["course_name"] = event.get("courseName")
        if event.get("location"):
            curated_event["location"] = event.get("location")

        # Goals
        if event.get("goalTime"):
            curated_event["goal_time_seconds"] = event.get("goalTime")
        if event.get("url"):
            curated_event["url"] = event.get("url")
        if event.get("note"):
            curated_event["note"] = event.get("note")

        # Remove None values
        curated_event = {k: v for k, v in curated_event.items() if v is not None}
        curated.append(curated_event)

    return curated


def _curate_event_detail(event: dict) -> dict:
    """Curate single event detail to essential fields."""
    curated = {
        "event_id": event.get("uuid") or event.get("id"),
        "name": event.get("eventName") or event.get("name") or event.get("title"),
        "date": event.get("eventDate") or event.get("date"),
        "event_type": event.get("eventType") or event.get("sportType"),
    }

    # Detailed fields
    for key in [
        "distance", "courseName", "location", "goalTime",
        "url", "note", "city", "state", "country",
        "completionTarget", "completionTargetType",
    ]:
        val = event.get(key)
        if val is not None:
            # Convert camelCase key to snake_case
            snake_key = "".join(
                f"_{c.lower()}" if c.isupper() else c for c in key
            ).lstrip("_")
            curated[snake_key] = val

    # Remove None values
    return {k: v for k, v in curated.items() if v is not None}
