"""
Shared utility functions for Garmin MCP server.

Date validation, formatting helpers used across API and tool modules.
"""

import re
from datetime import datetime


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def clean_nones(d):
    """Recursively strip None values from dicts and lists.

    Args:
        d: A dict, list, or scalar value.

    Returns:
        Cleaned structure with all None values removed from dicts.
    """
    if isinstance(d, dict):
        return {k: clean_nones(v) for k, v in d.items() if v is not None}
    if isinstance(d, list):
        return [clean_nones(i) for i in d]
    return d


def validate_date(s: str) -> str:
    """Validate YYYY-MM-DD date string.

    Args:
        s: Date string to validate.

    Returns:
        The validated date string (stripped).

    Raises:
        ValueError: If the format is invalid or date is not real.
    """
    if not isinstance(s, str):
        raise ValueError(f"date must be a string, got {type(s).__name__}")
    s = s.strip()
    if not _DATE_RE.fullmatch(s):
        raise ValueError(f"date must be YYYY-MM-DD, got: {s}")
    # Verify it's a real date
    datetime.strptime(s, "%Y-%m-%d")
    return s


def format_duration(seconds) -> str:
    """Format seconds into human-readable duration.

    Args:
        seconds: Duration in seconds (int or float).

    Returns:
        Formatted string like "1h23m45s" or "25m30s".
    """
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "0s"
    if seconds <= 0:
        return "0s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h{m:02d}m{s:02d}s"
    if m > 0:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def format_distance(meters) -> str:
    """Format distance in meters to human-readable string.

    Args:
        meters: Distance in meters (int or float).

    Returns:
        Formatted string like "10.0 km" or "800 m".
    """
    try:
        meters = float(meters)
    except (TypeError, ValueError):
        return "0 m"
    if meters <= 0:
        return "0 m"
    if meters >= 1000:
        return f"{meters / 1000:.1f} km"
    return f"{int(meters)} m"


def format_pace(meters_per_sec) -> str | None:
    """Convert speed in m/s to pace in M:SS /km format.

    Garmin stores speed as meters per second. This converts to
    running-friendly pace format.

    Args:
        meters_per_sec: Speed in meters per second.

    Returns:
        Formatted string like "5:30 /km", or None if speed is zero/invalid.
    """
    try:
        mps = float(meters_per_sec)
    except (TypeError, ValueError):
        return None
    if mps <= 0:
        return None
    seconds_per_km = 1000.0 / mps
    minutes = int(seconds_per_km) // 60
    secs = int(seconds_per_km) % 60
    return f"{minutes}:{secs:02d} /km"
