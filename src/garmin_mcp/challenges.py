"""
Challenges and badges functions for Garmin Connect MCP Server
"""
import json

from fastmcp import Context
from garmin_mcp.client_factory import get_client


def register_tools(app):
    """Register all challenges-related tools with the MCP server app"""

    @app.tool()
    async def get_goals(ctx: Context, goal_type: str = "active") -> str:
        """Get Garmin Connect goals (active, future, or past)

        Args:
            goal_type: Type of goals to retrieve. Options: "active", "future", or "past"
        """
        try:
            goals = get_client(ctx).get_goals(goal_type)
            if not goals:
                return f"No {goal_type} goals found."
            return json.dumps(goals, indent=2)
        except Exception as e:
            return f"Error retrieving {goal_type} goals: {str(e)}"

    @app.tool()
    async def get_personal_record(ctx: Context) -> str:
        """Get personal records for user"""
        try:
            records = get_client(ctx).get_personal_record()
            if not records:
                return "No personal records found."
            return json.dumps(records, indent=2)
        except Exception as e:
            return f"Error retrieving personal records: {str(e)}"

    @app.tool()
    async def get_earned_badges(ctx: Context) -> str:
        """Get earned badges for user"""
        try:
            badges = get_client(ctx).get_earned_badges()
            if not badges:
                return "No earned badges found."
            return json.dumps(badges, indent=2)
        except Exception as e:
            return f"Error retrieving earned badges: {str(e)}"

    @app.tool()
    async def get_adhoc_challenges(ctx: Context, start: int = 0, limit: int = 100) -> str:
        """Get adhoc challenges data

        Args:
            start: Starting index for challenges retrieval
            limit: Maximum number of challenges to retrieve
        """
        try:
            challenges = get_client(ctx).get_adhoc_challenges(start, limit)
            if not challenges:
                return "No adhoc challenges found."
            return json.dumps(challenges, indent=2)
        except Exception as e:
            return f"Error retrieving adhoc challenges: {str(e)}"

    @app.tool()
    async def get_available_badge_challenges(ctx: Context, start: int = 1, limit: int = 100) -> str:
        """Get available badge challenges data

        Args:
            start: Starting index for challenges retrieval (starts at 1)
            limit: Maximum number of challenges to retrieve
        """
        try:
            challenges = get_client(ctx).get_available_badge_challenges(start, limit)
            if not challenges:
                return "No available badge challenges found."
            return json.dumps(challenges, indent=2)
        except Exception as e:
            return f"Error retrieving available badge challenges: {str(e)}"

    @app.tool()
    async def get_badge_challenges(ctx: Context, start: int = 1, limit: int = 100) -> str:
        """Get badge challenges data

        Args:
            start: Starting index for challenges retrieval (starts at 1)
            limit: Maximum number of challenges to retrieve
        """
        try:
            challenges = get_client(ctx).get_badge_challenges(start, limit)
            if not challenges:
                return "No badge challenges found."
            return json.dumps(challenges, indent=2)
        except Exception as e:
            return f"Error retrieving badge challenges: {str(e)}"

    @app.tool()
    async def get_non_completed_badge_challenges(ctx: Context, start: int = 1, limit: int = 100) -> str:
        """Get non-completed badge challenges data

        Args:
            start: Starting index for challenges retrieval (starts at 1)
            limit: Maximum number of challenges to retrieve
        """
        try:
            challenges = get_client(ctx).get_non_completed_badge_challenges(start, limit)
            if not challenges:
                return "No non-completed badge challenges found."
            return json.dumps(challenges, indent=2)
        except Exception as e:
            return f"Error retrieving non-completed badge challenges: {str(e)}"

    @app.tool()
    async def get_race_predictions(ctx: Context) -> str:
        """Get race predictions for user"""
        try:
            predictions = get_client(ctx).get_race_predictions()
            if not predictions:
                return "No race predictions found."
            return json.dumps(predictions, indent=2)
        except Exception as e:
            return f"Error retrieving race predictions: {str(e)}"

    @app.tool()
    async def get_inprogress_virtual_challenges(start_date: str, end_date: str, ctx: Context) -> str:
        """Get in-progress virtual challenges/expeditions between dates

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        try:
            challenges = get_client(ctx).get_inprogress_virtual_challenges(
                start_date, end_date
            )
            if not challenges:
                return f"No in-progress virtual challenges found between {start_date} and {end_date}."
            return json.dumps(challenges, indent=2)
        except Exception as e:
            return f"Error retrieving in-progress virtual challenges: {str(e)}"

    return app