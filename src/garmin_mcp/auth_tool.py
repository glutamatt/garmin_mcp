"""
Authentication tools for Garmin Connect MCP server.

Session-based authentication using FastMCP Context:
- Login stores tokens in session AND returns them to caller
- Caller can persist tokens (cookies, etc.) for session restoration
- set_garmin_session() restores session from persisted tokens
- All data tools use session tokens via get_client(ctx)
"""

from fastmcp import Context

from garmin_mcp.garmin_platform import garmin_login
from garmin_mcp.client_factory import (
    set_session_tokens,
    clear_session_tokens,
    get_client,
)


def register_tools(app):
    """Register authentication tools with the MCP app."""

    @app.tool()
    async def garmin_login_tool(email: str, password: str, ctx: Context) -> dict:
        """
        Login to Garmin Connect.

        On success:
        - Stores tokens in session (subsequent tools work automatically)
        - Returns tokens to you (persist in cookies for session restoration)

        Args:
            email: Your Garmin Connect email address
            password: Your Garmin Connect password

        Returns:
            On success: {success: true, tokens: "...", display_name: "...", full_name: "..."}
            On failure: {success: false, error: "..."}
        """
        result = garmin_login(email, password)
        if result.success and result.tokens:
            set_session_tokens(ctx, result.tokens)
        return result.to_dict()

    @app.tool()
    async def set_garmin_session(garmin_tokens: str, ctx: Context) -> dict:
        """
        Restore Garmin session from stored tokens.

        Call this at the start of a conversation to restore a previously
        authenticated session. After this, all Garmin tools will work.

        Args:
            garmin_tokens: Base64 encoded Garmin OAuth tokens (from login)

        Returns:
            {success: true} or {success: false, error: "..."}
        """
        try:
            set_session_tokens(ctx, garmin_tokens)
            return {"success": True, "message": "Garmin session restored"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.tool()
    async def garmin_logout(ctx: Context) -> dict:
        """
        Clear Garmin session.

        Removes tokens from the current session. Does not invalidate
        the tokens themselves - they can still be used to restore session.

        Returns:
            {success: true}
        """
        clear_session_tokens(ctx)
        return {"success": True, "message": "Garmin session cleared"}

    # Common tools (shared interface with future coros_mcp)

    @app.tool()
    async def get_user_name(ctx: Context) -> dict:
        """
        Get user's display name.

        Common tool across all sport platforms.

        Returns:
            {name: "...", full_name: "..."}
        """
        try:
            client = get_client(ctx)

            # First, try to use cached values from the client if available
            if client.display_name and client.full_name:
                return {
                    "name": client.display_name,
                    "full_name": client.full_name,
                }

            # If not cached, fetch from API and update client attributes
            try:
                profile = client.garth.connectapi(
                    "/userprofile-service/userprofile/profile"
                )
                if profile and isinstance(profile, dict):
                    client.display_name = profile.get("displayName")
                    client.full_name = profile.get("fullName")
                    return {
                        "name": client.display_name,
                        "full_name": client.full_name,
                    }
            except Exception as fetch_error:
                # If API fetch fails, return error details
                return {
                    "name": None,
                    "full_name": None,
                    "error": f"Failed to fetch profile: {str(fetch_error)}"
                }

            # Fallback if profile fetch succeeded but data is missing
            return {
                "name": None,
                "full_name": None,
                "error": "Profile data not available"
            }
        except Exception as e:
            return {"error": str(e)}

    @app.tool()
    async def get_available_features() -> dict:
        """
        Get list of available data domains.

        Common tool across all sport platforms. Returns summary of what
        data types are available from this platform.

        Returns:
            {platform: "garmin", features: [...]}
        """
        return {
            "platform": "garmin",
            "features": [
                {"domain": "health", "tools": ["get_stats", "get_sleep_data", "get_stress_data", "get_hrv_data", "get_body_battery", "get_spo2_data", "get_respiration_data"]},
                {"domain": "activities", "tools": ["get_activities", "get_activities_by_date", "get_activity", "get_activity_splits"]},
                {"domain": "training", "tools": ["get_training_status", "get_training_readiness", "get_endurance_score", "get_fitnessage_data", "get_training_load_balance"]},
                {"domain": "devices", "tools": ["get_devices", "get_device_last_used", "get_device_alarms"]},
                {"domain": "gear", "tools": ["get_gear", "add_gear_to_activity", "remove_gear_from_activity"]},
                {"domain": "weight", "tools": ["get_weigh_ins", "add_weigh_in"]},
                {"domain": "challenges", "tools": ["get_goals", "get_personal_record", "get_earned_badges", "get_race_predictions"]},
                {"domain": "workouts", "tools": ["get_workouts", "get_workout_by_id", "get_scheduled_workouts", "schedule_workout", "upload_workout"]},
            ]
        }

    return app
