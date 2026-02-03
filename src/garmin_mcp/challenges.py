"""
Challenges and badges functions for Garmin Connect MCP Server

Uses FastMCP Context for session state.
"""
import json
import datetime

from mcp.server.fastmcp import Context

from garmin_mcp.client_factory import get_client


def _format_time(seconds: float) -> str:
    if seconds is None:
        return None
    total = int(seconds)
    h, m, s = total // 3600, (total % 3600) // 60, total % 60
    return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"


def _format_distance(meters: float) -> str:
    if meters is None:
        return None
    return f"{meters / 1000:.2f} km" if meters >= 1000 else f"{meters:.0f} m"


def register_tools(app):
    """Register all challenges-related tools with the MCP server app"""

    @app.tool()
    async def get_goals(ctx: Context, goal_type: str = "active") -> str:
        """Get Garmin Connect goals

        Args:
            goal_type: Type (active, future, past)
        """
        try:
            client = await get_client(ctx)
            goals = client.get_goals(goal_type)
            if not goals:
                return f"No {goal_type} goals found"
            return json.dumps(goals, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_personal_record(ctx: Context) -> str:
        """Get personal records"""
        try:
            client = await get_client(ctx)
            records = client.get_personal_record()
            if not records:
                return "No personal records"

            PR_TYPES = {
                1: ("Fastest 1K", "time"), 2: ("Fastest Mile", "time"),
                3: ("Fastest 5K", "time"), 4: ("Fastest 10K", "time"),
                5: ("Fastest Half Marathon", "time"), 6: ("Fastest Marathon", "time"),
                7: ("Longest Run", "distance"), 8: ("Longest Ride", "distance"),
                12: ("Most Steps Day", "count"),
            }

            curated = []
            for r in records:
                type_id = r.get("typeId")
                info = PR_TYPES.get(type_id, (f"Record {type_id}", "unknown"))
                value = r.get("value")

                if info[1] == "time":
                    formatted = _format_time(value)
                elif info[1] == "distance":
                    formatted = _format_distance(value)
                else:
                    formatted = f"{int(value):,}" if value else None

                curated.append({
                    "record": info[0],
                    "value": formatted,
                    "raw_value": value,
                    "activity_id": r.get("activityId"),
                })

            return json.dumps(curated, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_earned_badges(ctx: Context) -> str:
        """Get earned badges"""
        try:
            client = await get_client(ctx)
            badges = client.get_earned_badges()
            if not badges:
                return "No badges"

            curated = []
            for b in badges:
                curated.append({
                    "name": b.get("badgeName"),
                    "points": b.get("badgePoints"),
                    "earned_date": b.get("badgeEarnedDate", "").split("T")[0] if b.get("badgeEarnedDate") else None,
                })

            return json.dumps({"count": len(curated), "badges": curated}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_badge_challenges(ctx: Context, start: int = 1, limit: int = 20) -> str:
        """Get badge challenges joined by user

        Args:
            start: Start index (default 1)
            limit: Max results (default 20)
        """
        try:
            client = await get_client(ctx)
            challenges = client.get_badge_challenges(start, min(limit, 100))
            if not challenges:
                return "No badge challenges"

            curated = []
            for c in challenges:
                curated.append({
                    "name": c.get("badgeChallengeName"),
                    "status": c.get("badgeChallengeStatusId"),
                    "points": c.get("badgePoints"),
                    "start_date": c.get("startDate", "").split("T")[0] if c.get("startDate") else None,
                    "end_date": c.get("endDate", "").split("T")[0] if c.get("endDate") else None,
                })

            return json.dumps({"count": len(curated), "challenges": curated}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_race_predictions(ctx: Context) -> str:
        """Get predicted race times based on fitness"""
        try:
            client = await get_client(ctx)
            predictions = client.get_race_predictions()
            if not predictions:
                return "No race predictions"

            curated = {
                "date": predictions.get("calendarDate"),
                "5K": _format_time(predictions.get("time5K")),
                "10K": _format_time(predictions.get("time10K")),
                "half_marathon": _format_time(predictions.get("timeHalfMarathon")),
                "marathon": _format_time(predictions.get("timeMarathon")),
            }
            return json.dumps({k: v for k, v in curated.items() if v is not None}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    @app.tool()
    async def get_adhoc_challenges(ctx: Context, start: int = 0, limit: int = 20) -> str:
        """Get user-created social challenges

        Args:
            start: Start index
            limit: Max results
        """
        try:
            client = await get_client(ctx)
            challenges = client.get_adhoc_challenges(start, min(limit, 100))
            if not challenges:
                return "No adhoc challenges"

            curated = []
            for c in challenges:
                curated.append({
                    "name": c.get("adHocChallengeName"),
                    "your_ranking": c.get("userRanking"),
                    "player_count": c.get("playerCount"),
                    "start_date": c.get("startDate", "").split("T")[0] if c.get("startDate") else None,
                    "end_date": c.get("endDate", "").split("T")[0] if c.get("endDate") else None,
                })

            return json.dumps({"count": len(curated), "challenges": curated}, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

    return app
