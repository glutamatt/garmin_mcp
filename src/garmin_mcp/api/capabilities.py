"""
Device Capabilities API — dynamic tool filtering based on user's watch.

Uses Garmin's usageIndicators endpoint to determine which features
the user's device actually supports, then maps those to MCP tool names.

Pure functions: (Garmin client) -> dict.
"""

from garminconnect import Garmin

# Maps Garmin capability flag -> list of tools that require it.
# If the flag is False, those tools are disabled for this user.
CAPABILITY_TOOL_MAP = {
    "hasTrainingStatusCapableDevice": [
        "get_training_status",
        "get_training_readiness",
    ],
    "hasHrvStatusCapableDevice": [
        "get_hrv_data",
    ],
    "hasBodyBatteryCapableDevice": [
        "get_body_battery",
    ],
    "hasVO2MaxRunCapable": [
        "get_max_metrics",
    ],
    "hasSleepScoreCapableDevice": [
        "get_sleep",
    ],
    "hasRespirationCapableDevice": [
        "get_respiration",
    ],
    "hasSpO2CapableDevice": [
        "get_spo2_data",
    ],
    "hasStressCapableDevice": [
        "get_stress",
    ],
    "hasFitnessAgeCapableDevice": [
        "get_max_metrics",
    ],
    # Blood pressure and women's health tools removed from tool layer (no coaching value).
    # Capabilities still tracked for reference but no tools to disable.
}


def get_device_capabilities(client: Garmin) -> dict:
    """Return device capabilities and list of tools to disable.

    Calls get_usage_indicators() and maps the boolean flags to
    MCP tool names. Tools whose required capability is False are
    added to the disabled_tools list.

    Returns:
        {
            "capabilities": {"hasHrvStatusCapableDevice": True, ...},
            "disabled_tools": ["get_hrv_data", ...]
        }

    If the indicators call fails, returns empty disabled_tools
    (fail-open: all tools available).
    """
    try:
        indicators = client.get_usage_indicators()
    except Exception:
        return {"capabilities": {}, "disabled_tools": []}

    flags = indicators.get("deviceBasedIndicators", {})
    if not isinstance(flags, dict):
        return {"capabilities": {}, "disabled_tools": []}

    disabled = set()
    capabilities = {}
    for flag, tools in CAPABILITY_TOOL_MAP.items():
        value = flags.get(flag, True)  # default True if flag unknown
        capabilities[flag] = value
        if not value:
            disabled.update(tools)

    return {
        "capabilities": capabilities,
        "disabled_tools": sorted(disabled),
    }
