"""
Device capabilities — what the athlete's watches can compute.

Garmin's `usageIndicators` answer (`/web-gateway/snapshot/usageIndicators`) has
one flag per feature, for all the devices of the account: `deviceBasedIndicators`
→ `hasTrainingStatusCapableDevice`, `hasTrainingReadinessCapableDevice`…

An answer without data uses it to say why (`missing_reason`):
- `not_supported_by_device`: no device of the account computes the feature;
- `no_data`: a device computes it, Garmin has no value for this day or activity.

The flags are read only for an answer without data: an answer with data makes
no extra call.

Pure functions: (Garmin client) → dict / reason.
"""

import logging

from garminconnect import Garmin

from garmin_mcp.api.contract import (
    NO_DATA,
    NOT_SUPPORTED_BY_DEVICE,
    NotFound,
    Unavailable,
    as_garmin_error,
    has_data,
    unavailable,
)

logger = logging.getLogger(__name__)

# Features whose missing data can come from the device: feature → flag of
# `deviceBasedIndicators`. Each flag is checked against a real answer: on a
# Forerunner 165 the three flags are false, and Garmin has no readiness, no
# training status and no activity training load.
TRAINING_READINESS = "training_readiness"
TRAINING_STATUS = "training_status"
TRAINING_LOAD = "training_load"

FEATURE_FLAGS = {
    TRAINING_READINESS: "hasTrainingReadinessCapableDevice",
    TRAINING_STATUS: "hasTrainingStatusCapableDevice",
    # No flag for the per-activity load (EPOC): the acute load is the sum of these loads.
    TRAINING_LOAD: "hasAcuteTrainingLoadCapableDevice",
}


def missing_reason(client: Garmin, feature: str) -> str:
    """Why `feature` has no data: `not_supported_by_device`, or `no_data`.

    When Garmin does not give the flags (`Unavailable`, `NotFound`), the reason
    is `no_data`: true, only less precise. Any other failure (auth, a bug) is raised.
    """
    try:
        flags = _device_flags(client)
    except Exception as e:
        error = as_garmin_error(e)
        if not isinstance(error, (Unavailable, NotFound)):
            raise error from e
        logger.warning("Device capabilities not read, reason left as no_data: %s", error)
        return NO_DATA
    return NOT_SUPPORTED_BY_DEVICE if flags.get(FEATURE_FLAGS[feature]) is False else NO_DATA


def day_answer(client: Garmin, feature: str, date: str, curated: dict | None) -> dict:
    """A one-day answer of a device feature: the curated data, or why there is none."""
    if has_data(curated):
        return curated
    return unavailable(missing_reason(client, feature), date=date)


def _device_flags(client: Garmin) -> dict:
    flags = (client.get_usage_indicators() or {}).get("deviceBasedIndicators")
    return flags if isinstance(flags, dict) else {}


# ── MCP tool `get_device_capabilities` ───────────────────────────────────────
# Called by the frontend at login. Its `disabled_tools` name MCP tools that the
# frontend does not offer any more (garmin_cli replaces them): kept until these
# tools are removed (audit PR 11).

CAPABILITY_TOOL_MAP = {
    "hasTrainingStatusCapableDevice": ["get_training_status", "get_training_readiness"],
    "hasHrvStatusCapableDevice": ["get_hrv_data"],
    "hasBodyBatteryCapableDevice": ["get_body_battery"],
    "hasVO2MaxRunCapable": ["get_max_metrics"],
    "hasSleepScoreCapableDevice": ["get_sleep"],
    "hasRespirationCapableDevice": ["get_respiration"],
    "hasSpO2CapableDevice": ["get_spo2_data"],
    "hasStressCapableDevice": ["get_stress"],
    "hasFitnessAgeCapableDevice": ["get_max_metrics"],
}


def get_device_capabilities(client: Garmin) -> dict:
    """Capability flags and the MCP tools to disable. Fail-open: {} and [] when the call fails."""
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
