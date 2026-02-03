"""
Challenges and badges functions for Garmin Connect MCP Server
"""
import json
import datetime
from typing import Any, Dict, List, Optional, Union


from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all challenges-related tools with the MCP server app"""

    @app.tool()
    def get_goals(goal_type: str = "active") -> str:
        """Get Garmin Connect goals (active, future, or past)

        Args:
            goal_type: Type of goals to retrieve. Options: "active", "future", or "past"
        """
        try:
            client = get_client()
            goals = client.get_goals(goal_type)
            if not goals:
                return f"No {goal_type} goals found."
            return json.dumps(goals, indent=2)
        except Exception as e:
            return f"Error retrieving {goal_type} goals: {str(e)}"

    @app.tool()
    def get_personal_record() -> str:
        """Get personal records for user"""
        try:
            client = get_client()
            records = client.get_personal_record()
            if not records:
                return "No personal records found."
            return json.dumps(records, indent=2)
        except Exception as e:
            return f"Error retrieving personal records: {str(e)}"

    @app.tool()
    def get_earned_badges() -> str:
        """Get earned badges for user"""
        try:
            client = get_client()
            badges = client.get_earned_badges()
            if not badges:
                return "No earned badges found."
            return json.dumps(badges, indent=2)
        except Exception as e:
            return f"Error retrieving earned badges: {str(e)}"

    @app.tool()
    def get_adhoc_challenges(start: int = 0, limit: int = 100) -> str:
        """Get adhoc challenges data

        Args:
            start: Starting index for challenges retrieval
            limit: Maximum number of challenges to retrieve
        """
        try:
            client = get_client()
            challenges = client.get_adhoc_challenges(start, limit)
            if not challenges:
                return "No adhoc challenges found."
            return json.dumps(challenges, indent=2)
        except Exception as e:
            return f"Error retrieving adhoc challenges: {str(e)}"

    @app.tool()
    def get_available_badge_challenges(start: int = 1, limit: int = 100) -> str:
        """Get available badge challenges data

        Args:
            start: Starting index for challenges retrieval (starts at 1)
            limit: Maximum number of challenges to retrieve
        """
        try:
            client = get_client()
            challenges = client.get_available_badge_challenges(start, limit)
            if not challenges:
                return "No available badge challenges found."
            return json.dumps(challenges, indent=2)
        except Exception as e:
            return f"Error retrieving available badge challenges: {str(e)}"

    @app.tool()
    def get_badge_challenges(start: int = 1, limit: int = 100) -> str:
        """Get badge challenges data

        Args:
            start: Starting index for challenges retrieval (starts at 1)
            limit: Maximum number of challenges to retrieve
        """
        try:
            client = get_client()
            challenges = client.get_badge_challenges(start, limit)
            if not challenges:
                return "No badge challenges found."
            return json.dumps(challenges, indent=2)
        except Exception as e:
            return f"Error retrieving badge challenges: {str(e)}"

    @app.tool()
    def get_non_completed_badge_challenges(start: int = 1, limit: int = 100) -> str:
        """Get non-completed badge challenges data

        Args:
            start: Starting index for challenges retrieval (starts at 1)
            limit: Maximum number of challenges to retrieve
        """
        try:
            client = get_client()
            challenges = client.get_non_completed_badge_challenges(start, limit)
            if not challenges:
                return "No non-completed badge challenges found."
            return json.dumps(challenges, indent=2)
        except Exception as e:
            return f"Error retrieving non-completed badge challenges: {str(e)}"

    @app.tool()
    def get_race_predictions() -> str:
        """Get race predictions for user"""
        try:
            client = get_client()
            predictions = client.get_race_predictions()
            if not predictions:
                return "No race predictions found."
            return json.dumps(predictions, indent=2)
        except Exception as e:
            return f"Error retrieving race predictions: {str(e)}"

    @app.tool()
    def get_upcoming_calendar_events(num_days_forward: int = 365, limit: int = 10) -> str:
        """Get upcoming calendar events including scheduled races

        Returns scheduled events from your Garmin Connect calendar, including
        race events, workouts, and other calendar items.

        Args:
            num_days_forward: Number of days forward to look for events (default: 365)
            limit: Maximum number of events to return (default: 10)
        """
        try:
            client = get_client()
            events = client.get_upcoming_calendar_events(
                num_days_forward=num_days_forward,
                limit=limit
            )
            if not events:
                return "No upcoming calendar events found."

            # Curate the events to essential fields
            curated_events = []
            for event in events if isinstance(events, list) else []:
                curated = {
                    "id": event.get("id"),
                    "event_name": event.get("eventName"),
                    "date": event.get("date"),
                    "event_type": event.get("eventType"),
                    "location": event.get("location"),
                    "is_race": event.get("race", False),
                }

                # Add completion target if available
                target = event.get("completionTarget", {})
                if target:
                    curated["target_distance_meters"] = target.get("value")

                # Add event time if available
                event_time = event.get("eventTimeLocal", {})
                if event_time and event_time.get("startTimeHhMm"):
                    curated["start_time"] = event_time.get("startTimeHhMm")
                    curated["timezone"] = event_time.get("timeZoneId")

                # Add customization details
                customization = event.get("eventCustomization", {})
                if customization:
                    if customization.get("isPrimaryEvent"):
                        curated["is_primary_event"] = True
                    custom_goal = customization.get("customGoal", {})
                    if custom_goal and custom_goal.get("value"):
                        curated["custom_goal_seconds"] = custom_goal.get("value")

                # Add URL if available
                if event.get("url"):
                    curated["url"] = event.get("url")

                # Remove None values
                curated = {k: v for k, v in curated.items() if v is not None}
                curated_events.append(curated)

            return json.dumps(curated_events, indent=2)
        except Exception as e:
            return f"Error retrieving upcoming calendar events: {str(e)}"

    @app.tool()
    def get_calendar_events(
        start_date: str,
        
        limit: int = 20,
        page_index: int = 1
    ) -> str:
        """Get calendar events starting from a specific date

        Returns scheduled events from your Garmin Connect calendar, including
        race events, workouts, and other calendar items.

        Args:
            start_date: Start date in YYYY-MM-DD format
            limit: Maximum number of events to return per page (default: 20)
            page_index: Page number for pagination (default: 1)
        """
        try:
            client = get_client()
            events = client.get_calendar_events(
                start_date=start_date,
                limit=limit,
                page_index=page_index
            )
            if not events:
                return f"No calendar events found from {start_date}."

            # Curate the events to essential fields
            curated_events = []
            for event in events if isinstance(events, list) else []:
                curated = {
                    "id": event.get("id"),
                    "event_name": event.get("eventName"),
                    "date": event.get("date"),
                    "event_type": event.get("eventType"),
                    "location": event.get("location"),
                    "is_race": event.get("race", False),
                }

                # Add completion target if available
                target = event.get("completionTarget", {})
                if target:
                    curated["target_distance_meters"] = target.get("value")

                # Add event time if available
                event_time = event.get("eventTimeLocal", {})
                if event_time and event_time.get("startTimeHhMm"):
                    curated["start_time"] = event_time.get("startTimeHhMm")
                    curated["timezone"] = event_time.get("timeZoneId")

                # Add customization details
                customization = event.get("eventCustomization", {})
                if customization:
                    if customization.get("isPrimaryEvent"):
                        curated["is_primary_event"] = True
                    custom_goal = customization.get("customGoal", {})
                    if custom_goal and custom_goal.get("value"):
                        curated["custom_goal_seconds"] = custom_goal.get("value")

                # Add URL if available
                if event.get("url"):
                    curated["url"] = event.get("url")

                # Remove None values
                curated = {k: v for k, v in curated.items() if v is not None}
                curated_events.append(curated)

            return json.dumps(curated_events, indent=2)
        except Exception as e:
            return f"Error retrieving calendar events: {str(e)}"

    @app.tool()
    def get_inprogress_virtual_challenges(start_date: str, end_date: str) -> str:
        """Get in-progress virtual challenges/expeditions between dates

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        try:
            client = get_client()
            challenges = client.get_inprogress_virtual_challenges(
                start_date, end_date
            )
            if not challenges:
                return f"No in-progress virtual challenges found between {start_date} and {end_date}."
            return json.dumps(challenges, indent=2)
        except Exception as e:
            return f"Error retrieving in-progress virtual challenges: {str(e)}"

    return app
